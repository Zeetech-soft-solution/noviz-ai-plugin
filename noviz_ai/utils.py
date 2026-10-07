# Small, standalone module for real cross-cutting checks that don't
# belong in api.py (the relay-facing whitelisted entry point) or the
# one-time app-setup hook module — currently just the app-tile permission
# gate. Kept separate so hooks.py's own "has_permission" reference stays
# readable and doesn't pull in requests/dispatcher imports it never uses.
import frappe


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
