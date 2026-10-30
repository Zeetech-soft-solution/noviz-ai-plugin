"""Native aggregation for the relay's grouped answers (2026-10-12).

The relay used to pull raw rows from ERPNext page by page and group, join
and sum them in memory. That moved data that never needed to leave
ERPNext, capped what it read, and kept a second copy of the filter logic
that drifted from ERPNext's own. Here ERPNext computes the result itself
with frappe.get_list (GROUP BY, aggregate functions, linked-record fields),
under the logged-in person's own permissions, and only the requested page
of grouped rows goes back to the relay.

One frappe.get_list call per metric — each with its own filters — merged
by group key here. Frappe 16 does not allow SQL functions as strings or
conditional aggregates in get_list, so a per-metric filter is its own
grouped query, and the relay expresses a month as a date-range filter.
"""

import frappe

from noviz_ai.pdf_report import _AGGREGATE_SQL
from noviz_ai.utils import child_parent_doctype

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
		merged = _merge_filters(filters, m.get("filters"))

		# The figure over everything (correct for avg / min / max too).
		total_rows = frappe.get_list(
			doctype, fields=[{fn: field, "as": "_v"}], filters=merged, limit_page_length=0, parent_doctype=parent_doctype
		)
		overall[name] = total_rows[0].get("_v") if total_rows else None

		if not group_by:
			continue
		# Carried fields ride on every metric's query: a group missing from
		# the first metric's rows still gets them from a later one.
		fields = [f"{group_by} as _key", *[f"{c} as {_alias(c)}" for c in carry], {fn: field, "as": "_v"}]
		rows = frappe.get_list(
			doctype, fields=fields, filters=merged, group_by=group_by, limit_page_length=0, parent_doctype=parent_doctype
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
