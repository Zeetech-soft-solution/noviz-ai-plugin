"""Native aggregation for the relay's grouped answers (2026-10-12).

The relay used to pull raw rows from ERPNext page by page and group, join
and sum them in memory. That moved data that never needed to leave
ERPNext, capped what it read, and kept a second copy of the filter logic
that drifted from ERPNext's own. Here ERPNext computes the result itself
with frappe.get_list (GROUP BY, aggregate functions, linked-record fields),
under the logged-in person's own permissions, and only the requested page
of grouped rows goes back to the relay.

One frappe.get_list call per metric — each with its own filters — merged
by group key here. A per-metric filter is its own grouped query, and the
relay expresses a month as a date-range filter.

This is the Frappe 15 branch: figure columns are written "sum(field) as
alias", the group is the alias, and a filter on a linked record's field
becomes the matching records' names (utils.frappe15_filters).
"""

import re

import frappe
from frappe.utils import add_days, getdate

from noviz_ai.pdf_report import _AGGREGATE_SQL
from noviz_ai.utils import child_parent_doctype, figure_column, frappe15_filters

# Bounds what one request can ask ERPNext to run.
MAX_METRICS = 24
MAX_PAGE = 20


def _merge_filters(base, own):
	"""A metric's own filters win over the shared filters on the same field."""
	base_list = _as_list(base)
	own_list = _as_list(own)
	own_fields = {f[0] for f in own_list}
	return [f for f in base_list if f[0] not in own_fields] + own_list


def _as_list(filters):
	if not filters:
		return []
	if isinstance(filters, dict):
		return [[field, "=", value] if not isinstance(value, (list, tuple)) else [field, *value] for field, value in filters.items()]
	return [list(f) for f in filters]


def _alias(field):
	return field.replace(".", "_")


def _sort_value(value):
	# Empty values last; numbers with numbers, dates (text) with text.
	return (value is not None, value if value is not None else 0)


def run_aggregate(spec: dict) -> dict:
	"""spec:
	doctype: native DocType
	filters: native filters for every metric (list of [field, op, value] or a dict)
	group_by: native field, a linked record's field ("customer.customer_group"), or empty for overall only
	metrics: [{"name", "op": sum|avg|count|min|max, "field" (not needed for count), "filters" (optional)}]
	carry_fields: fields shown next to each group, functionally tied to it ("customer.mobile_no")
	sort: "metric" (first metric, highest first; default) or "key"
	page_index (1-based), page_count (at most MAX_PAGE)

	Returns {"groups": [{"key", <metric names>, <carried fields>}], "totalGroups",
	"pageIndex", "pageCount", "hasMore", "overall": {<metric name>: value}}.
	"""
	doctype = spec.get("doctype")
	metrics = spec.get("metrics") or []
	if not doctype or not metrics:
		frappe.throw("Noviz AI: an aggregate call needs a doctype and at least one metric.")
	if len(metrics) > MAX_METRICS:
		frappe.throw(f"Noviz AI: at most {MAX_METRICS} metrics in one aggregate call.")

	filters = spec.get("filters")
	parent_doctype = child_parent_doctype(doctype, filters)
	if not frappe.has_permission(doctype, "read", parent_doctype=parent_doctype):
		frappe.throw(f"Noviz AI: you do not have permission to read {doctype} records.", frappe.PermissionError)

	group_by = spec.get("group_by") or None
	carry = [c for c in (spec.get("carry_fields") or []) if isinstance(c, str) and c]
	groups: dict = {}
	overall: dict = {}

	for index, m in enumerate(metrics):
		fn = _AGGREGATE_SQL.get(m.get("op"))
		if not fn:
			frappe.throw(f'Noviz AI: unsupported aggregate op "{m.get("op")}".')
		name = m.get("name") or f'{m.get("op")}_{m.get("field") or "name"}'
		field = m.get("field") or "name"
		merged = frappe15_filters(doctype, _merge_filters(filters, m.get("filters")))

		# The figure over everything (correct for avg / min / max too).
		total_rows = frappe.get_list(
			doctype, fields=[figure_column(fn, doctype, field, "_v")], filters=merged, limit_page_length=0, parent_doctype=parent_doctype
		)
		overall[name] = total_rows[0].get("_v") if total_rows else None

		if not group_by:
			continue
		# Carried fields ride on every metric's query: a group missing from
		# the first metric's rows still gets them from a later one. Frappe 15
		# cannot read MIN/MAX next to a linked record's field, so those
		# queries leave linked carried fields to the other metrics.
		carried = [c for c in carry if fn not in ("MIN", "MAX") or "." not in c]
		fields = [f"{group_by} as _key", *[f"{c} as {_alias(c)}" for c in carried], figure_column(fn, doctype, field, "_v")]
		rows = frappe.get_list(
			doctype, fields=fields, filters=merged, group_by="_key", limit_page_length=0, parent_doctype=parent_doctype
		)
		for r in rows:
			key = r.get("_key")
			key = "(none)" if key in (None, "") else key
			entry = groups.setdefault(key, {"key": key})
			entry[name] = r.get("_v")
			for c in carry:
				if entry.get(_alias(c)) is None:
					entry[_alias(c)] = r.get(_alias(c))

	names = [m.get("name") or f'{m.get("op")}_{m.get("field") or "name"}' for m in metrics]
	zero_when_missing = {n for n, m in zip(names, metrics) if m.get("op") in ("sum", "count")}
	for entry in groups.values():
		for n in names:
			if n not in entry:
				entry[n] = 0 if n in zero_when_missing else None

	# Equal figures keep a fixed order (by key), so paging never repeats or
	# skips a group.
	ordered = sorted(groups.values(), key=lambda g: str(g["key"]))
	if spec.get("sort") != "key":
		ordered.sort(key=lambda g: _sort_value(g.get(names[0])), reverse=True)

	page_count = max(1, min(int(spec.get("page_count") or MAX_PAGE), MAX_PAGE))
	page_index = max(1, int(spec.get("page_index") or 1))
	start = (page_index - 1) * page_count
	return {
		"groups": ordered[start : start + page_count],
		"totalGroups": len(ordered),
		"pageIndex": page_index,
		"pageCount": page_count,
		"hasMore": start + page_count < len(ordered),
		"overall": overall,
	}


# Bounds the rows one grouped_rows call returns.
MAX_GROUPED_ROWS = 60000


def run_grouped_rows(spec: dict) -> list:
	"""Rows summed by ERPNext itself into months, for the relay's standard
	analyses: the same totals per month and account the raw rows give, in a
	fraction of the rows and one call.

	spec:
	doctype: native DocType
	filters: native filters (the relay's period, company and base filters)
	date_field: the date the rows are bucketed on
	split_at: the period's first day (YYYY-MM-DD)
	group_fields: other native fields to group on
	sums: native numeric fields, each summed under its own name

	Rows before split_at are summed into one row per group, dated the day
	before it. From split_at on, rows are summed per month, dated the 1st of
	the month, and the month holding split_at is dated split_at. So every
	date comparison with the period's start and every month, quarter or year
	bucket reads exactly as it does on the raw rows.

	Returns [{<date_field>, <group fields>, <sums>}]. Sums are written as
	Frappe 15 reads them (figure_column), filters go through frappe15_filters.
	"""
	doctype = spec.get("doctype")
	date_field = spec.get("date_field")
	group_by = spec.get("group_fields") or []
	sums = spec.get("sums") or []
	split_at = getdate(spec.get("split_at")) if spec.get("split_at") else None
	if not doctype or not date_field or not split_at or not sums:
		frappe.throw("Noviz AI: a grouped_rows call needs a doctype, date_field, split_at and sums.")
	for field in [date_field, *group_by, *sums]:
		if not isinstance(field, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", field):
			frappe.throw(f'Noviz AI: "{field}" is not a plain field name.')

	filters = frappe15_filters(doctype, _merge_filters(spec.get("filters"), [])) or []
	line_table = spec.get("line_table")
	parent_doctype = None if line_table else child_parent_doctype(doctype, filters)
	if not frappe.has_permission(doctype, "read", parent_doctype=parent_doctype):
		frappe.throw(f"Noviz AI: you do not have permission to read {doctype} records.", frappe.PermissionError)

	sum_fields = [figure_column("SUM", line_table or doctype, f, f) for f in sums]
	buckets: dict = {}

	def add(date, row):
		key = (date, *(row.get(g) for g in group_by))
		entry = buckets.get(key)
		if entry is None:
			entry = buckets[key] = {date_field: str(date), **{g: row.get(g) for g in group_by}, **{f: 0.0 for f in sums}}
		for f in sums:
			entry[f] += float(row.get(f) or 0)

	if line_table:
		# A document's lines (line_table), summed by month on the document's
		# date: the documents of the period as the user, then their lines
		# summed per document, both standard reads.
		if not isinstance(line_table, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]*", line_table):
			frappe.throw(f'Noviz AI: "{line_table}" is not a DocType name.')
		date_of = {d.name: getdate(d.get(date_field)) for d in frappe.get_list(doctype, fields=["name", date_field], filters=filters, limit_page_length=0)}
		names = list(date_of)
		day_before = add_days(split_at, -1)
		for i in range(0, len(names), 1000):
			for row in frappe.get_list(
				line_table,
				fields=["parent", *group_by, *sum_fields],
				filters=[["parent", "in", names[i : i + 1000]], ["parenttype", "=", doctype]],
				group_by=", ".join(["parent", *group_by]),
				limit_page_length=0,
				parent_doctype=doctype,
			):
				day = date_of.get(row.get("parent"))
				if day is None:
					continue
				if day < split_at:
					add(day_before, row)
				else:
					month = day.replace(day=1)
					add(split_at if month <= split_at else month, row)
		if len(buckets) > MAX_GROUPED_ROWS:
			frappe.throw(f"Noviz AI: more than {MAX_GROUPED_ROWS} grouped rows; narrow the period.")
		return sorted(buckets.values(), key=lambda r: (r[date_field], *(str(r.get(g) or "") for g in group_by)))

	if group_by:
		before = frappe.get_list(
			doctype,
			fields=[*group_by, *sum_fields],
			filters=[*filters, [date_field, "<", split_at]],
			group_by=", ".join(group_by),
			limit_page_length=0,
			parent_doctype=parent_doctype,
		)
	else:
		before = frappe.get_list(
			doctype, fields=sum_fields, filters=[*filters, [date_field, "<", split_at]], limit_page_length=0, parent_doctype=parent_doctype
		)
	day_before = add_days(split_at, -1)
	for row in before:
		if any(row.get(f) for f in sums):
			add(day_before, row)

	keys = ", ".join([date_field, *group_by])
	for row in frappe.get_list(
		doctype,
		fields=[date_field, *group_by, *sum_fields],
		filters=[*filters, [date_field, ">=", split_at]],
		group_by=keys,
		limit_page_length=0,
		parent_doctype=parent_doctype,
	):
		day = getdate(row.get(date_field))
		month = day.replace(day=1)
		add(split_at if month <= split_at else month, row)

	if len(buckets) > MAX_GROUPED_ROWS:
		frappe.throw(f"Noviz AI: more than {MAX_GROUPED_ROWS} grouped rows; narrow the period.")
	return sorted(buckets.values(), key=lambda r: (r[date_field], *(str(r.get(g) or "") for g in group_by)))
