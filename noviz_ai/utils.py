# Small, standalone module for real cross-cutting checks that don't
# belong in api.py (the relay-facing whitelisted entry point) or the
# one-time app-setup hook module — currently just the app-tile permission
# gate. Kept separate so hooks.py's own "has_permission" reference stays
# readable and doesn't pull in requests/dispatcher imports it never uses.
import re

import frappe

# Columns every DocType table has, though its definition does not list them.
STANDARD_COLUMNS = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "parent", "parentfield", "parenttype"}


def columns_on_this_site(doctype: str, fields):
	"""The requested columns this site's own DocType has.

	The relay's column lists are shared by every ERPNext version, and a field
	one version lacks fails the whole list on the other ("Field not permitted
	in query": Lead.utm_source on a Frappe 15 site, 2026-11-11), so ERPNext's
	definition decides. Columns written as expressions (a linked field, an
	alias, a figure) are left as they are; when the definition cannot be
	read, every column is asked for as before."""
	if not fields:
		return fields
	try:
		known = STANDARD_COLUMNS | {df.fieldname for df in frappe.get_meta(doctype).fields if df.fieldname}
	except Exception:
		return fields
	kept = [f for f in fields if not re.fullmatch(r"\w+", str(f)) or f in known]
	return kept or ["name"]


def figure_column(fn: str, doctype: str, field: str, alias: str) -> str:
	"""A SUM/COUNT/AVG/MIN/MAX column for get_list, as Frappe 15 reads it.
	SUM/COUNT/AVG name the field with its table: when the query also reads a
	linked record's field, Frappe joins that table and a bare "name" is
	ambiguous. Frappe 15 reads MIN/MAX only with a bare field (and not at all
	next to a linked record's field)."""
	qualify = fn.upper() in ("SUM", "COUNT", "AVG") and "." not in field
	column = f"`tab{doctype}`.`{field}`" if qualify else field
	return f"{fn.lower()}({column}) as {alias}"


def frappe15_filters(doctype: str, filters):
	"""Filters in the form Frappe 15 reads:
	- a linked record's field ("customer.customer_group") cannot be filtered
	  on, so it becomes the names of the matching linked records, read with
	  get_list under the same user's permissions;
	- the date word "today" is not read, so it becomes today's date."""
	if not filters:
		return filters
	triples = (
		[[k, *v] if isinstance(v, (list, tuple)) else [k, "=", v] for k, v in filters.items()]
		if isinstance(filters, dict)
		else [list(f) for f in filters]
	)
	out = []
	for field, op, value in triples:
		if value == "today":
			value = frappe.utils.today()
		if "." not in field:
			out.append([field, op, value])
			continue
		link, linked_field = field.split(".", 1)
		target = frappe.get_meta(doctype).get_field(link).options
		names = frappe.get_list(target, filters=[[linked_field, op, value]], pluck="name", limit_page_length=0)
		out.append([link, "in", names or [""]])
	return out


def check_app_permission():
	"""The "Noviz AI" tile on the /apps launcher (hooks.py's
	add_to_apps_screen). Shown to every desk user so the app is
	discoverable — "Noviz AI exists, ask your admin for access". Actual
	access is still gated: the chat Workspace/Page need the "Noviz AI
	Agent" role (assigned per user), and "Noviz AI Settings" needs
	System Manager."""
	return bool(frappe.session.user and frappe.session.user != "Guest")


def child_parent_doctype(doctype: str, filters=None):
	"""The parent DocType Frappe needs to authorise a read on a child table.

	A child table (Sales Invoice Item, Stock Entry Detail, ...) has no
	permissions of its own: Frappe checks read on its parent, and only when
	told which parent (`parent_doctype`). Without it frappe.has_permission
	returns False for everyone, System Manager included, so every child-table
	read was refused ("no permission to read Sales Invoice Item", live
	2026-10-07). ERPNext still decides: this only names the parent, the
	permission check itself is Frappe's.

	Taken from a `parenttype` filter when the caller sent one, otherwise the
	single DocType that holds this child table. None for a normal DocType, or
	when the parent is ambiguous (several parents and no filter), in which
	case Frappe keeps refusing as before."""
	if not frappe.is_table(doctype):
		return None
	parenttype = _filter_value(filters, "parenttype")
	if parenttype:
		return parenttype
	parents = set(frappe.get_all(
		"DocField",
		filters={"fieldtype": ["in", ["Table", "Table MultiSelect"]], "options": doctype},
		pluck="parent",
	))
	parents |= set(frappe.get_all(
		"Custom Field",
		filters={"fieldtype": ["in", ["Table", "Table MultiSelect"]], "options": doctype},
		pluck="dt",
	))
	parents = {p for p in parents if not frappe.is_table(p)}
	return parents.pop() if len(parents) == 1 else None


def _filter_value(filters, fieldname: str):
	"""The value of an `=` filter on `fieldname`, from either filter shape
	Frappe accepts: a dict ({"parenttype": "Sales Invoice"}) or a list of
	[field, op, value] / [doctype, field, op, value] entries."""
	if isinstance(filters, dict):
		value = filters.get(fieldname)
		if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == "=":
			value = value[1]
		return value if isinstance(value, str) else None
	for f in filters or []:
		if not isinstance(f, (list, tuple)):
			continue
		if len(f) == 3 and f[0] == fieldname and f[1] == "=" and isinstance(f[2], str):
			return f[2]
		if len(f) == 4 and f[1] == fieldname and f[2] == "=" and isinstance(f[3], str):
			return f[3]
	return None
