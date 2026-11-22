# My work (call kind "my_work"): what is waiting for this user in ERPNext,
# read in one call as frappe.session.user with ERPNext's own rules:
# - counts: the Desk's own open counts (frappe.desk.notifications), and the
#   unread notifications;
# - approvals: open Workflow Actions this user's roles may take (Frappe's own
#   permission query), on documents whose workflow state is still undecided
#   (the state's Doc Status is Draft in the workflow); for each document, its
#   list-view details and the steps this user may take now (get_transitions);
# - to do: the user's own open ToDos (assigned to them);
# - notifications: the user's unread Notification Log entries.
# Nothing here writes; approving runs through run_action as before.
import frappe
from frappe.desk.notifications import get_notifications
from frappe.model.workflow import get_transitions, get_workflow_name
from frappe.utils import cstr, get_fullname, strip_html

MAX_ROWS = 20
MAX_DETAILS = 4
SKIP_FIELDTYPES = {"Table", "Table MultiSelect", "Section Break", "Column Break", "Tab Break", "HTML", "Button", "Attach Image", "Image", "Text Editor", "HTML Editor", "Code", "JSON"}


def _text(value, limit=140):
	text = " ".join(strip_html(cstr(value)).split())
	return text if len(text) <= limit else text[: limit - 1] + "…"


def _limit(spec, key):
	try:
		return max(0, min(int(spec.get(key) or 0), MAX_ROWS))
	except (TypeError, ValueError):
		return 0


def _undecided_states(doctype: str) -> set:
	"""The states of the doctype's workflow in which the document is still a draft (not yet decided)."""
	name = get_workflow_name(doctype)
	if not name:
		return set()
	workflow = frappe.get_cached_doc("Workflow", name)
	return {s.state for s in workflow.states if cstr(s.doc_status) == "0"}


def _details(doctype: str, names: list) -> dict:
	"""Each document's title and the fields ERPNext shows in its list view, formatted, read as this user."""
	meta = frappe.get_meta(doctype)
	fields = [df for df in meta.fields if df.in_list_view and df.fieldtype not in SKIP_FIELDTYPES][:MAX_DETAILS]
	wanted = ["name"] + ([meta.title_field] if meta.title_field and meta.title_field != "name" else []) + [df.fieldname for df in fields]
	if any(df.fieldtype == "Currency" for df in fields) and meta.has_field("currency"):
		wanted.append("currency")
	out = {}
	for row in frappe.get_list(doctype, filters={"name": ["in", names]}, fields=list(dict.fromkeys(wanted))):
		details = []
		for df in fields:
			if row.get(df.fieldname) in (None, ""):
				continue
			details.append({"label": _(df.label), "value": _text(frappe.format(row.get(df.fieldname), df, doc=row), 80)})
		title = row.get(meta.title_field) if meta.title_field else None
		out[row.name] = {"title": _text(title, 80) if title and title != row.name else None, "details": details}
	return out


def _(text):
	return frappe._(text) if text else text


def _approvals(limit: int, offset: int):
	# Frappe's own permission query limits Workflow Action to this user's roles.
	groups = frappe.get_list(
		"Workflow Action",
		filters={"status": "Open"},
		fields=["reference_doctype", "workflow_state", {"COUNT": "*", "as": "count"}],
		group_by="reference_doctype, workflow_state",
		order_by="reference_doctype asc",
	)
	undecided = {}
	for g in groups:
		states = undecided.setdefault(g.reference_doctype, _undecided_states(g.reference_doctype))
		if g.workflow_state not in states:
			g.skip = True
	waiting = [g for g in groups if not g.get("skip")]
	total = sum(g.count for g in waiting)
	if not waiting or not limit:
		return total, []
	pairs = {(g.reference_doctype, g.workflow_state) for g in waiting}
	rows = frappe.get_list(
		"Workflow Action",
		filters={
			"status": "Open",
			"reference_doctype": ["in", sorted({p[0] for p in pairs})],
			"workflow_state": ["in", sorted({p[1] for p in pairs})],
		},
		fields=["name", "reference_doctype", "reference_name", "workflow_state", "owner", "creation"],
		order_by="creation desc",
		start=offset,
		page_length=limit * 2,
	)
	rows = [r for r in rows if (r.reference_doctype, r.workflow_state) in pairs][:limit]
	by_doctype = {}
	for r in rows:
		by_doctype.setdefault(r.reference_doctype, []).append(r.reference_name)
	details = {}
	for doctype, names in by_doctype.items():
		try:
			details[doctype] = _details(doctype, names)
		except frappe.PermissionError:
			details[doctype] = {}
	out = []
	for r in rows:
		info = details.get(r.reference_doctype, {}).get(r.reference_name)
		if info is None:
			continue  # this user may not read the document itself
		actions = []
		try:
			doc = frappe.get_doc(r.reference_doctype, r.reference_name)
			actions = [{"action": t.get("action"), "next_state": t.get("next_state")} for t in get_transitions(doc)]
		except (frappe.PermissionError, frappe.DoesNotExistError):
			continue
		except frappe.ValidationError:
			frappe.clear_messages()
		out.append(
			{
				"doctype": r.reference_doctype,
				"name": r.reference_name,
				"state": r.workflow_state,
				"title": info["title"],
				"details": info["details"],
				"from": get_fullname(r.owner),
				"date": cstr(r.creation),
				"actions": actions,
			}
		)
	return total, out


def _todos(limit: int, offset: int):
	user = frappe.session.user
	filters = {"status": "Open", "allocated_to": user}
	total = frappe.db.count("ToDo", filters)
	if not limit:
		return total, []
	rows = frappe.get_list(
		"ToDo",
		filters=filters,
		fields=["name", "reference_type", "reference_name", "description", "date", "priority", "assigned_by", "creation"],
		order_by="date asc, creation desc",
		start=offset,
		page_length=limit,
	)
	return total, [
		{
			"id": r.name,
			"doctype": r.reference_type,
			"name": r.reference_name,
			"note": _text(r.description),
			"due": cstr(r.date) or None,
			"priority": r.priority,
			"from": get_fullname(r.assigned_by) if r.assigned_by else None,
			"date": cstr(r.creation),
		}
		for r in rows
	]


def _notifications(limit: int, offset: int):
	filters = {"for_user": frappe.session.user, "read": 0}
	total = frappe.db.count("Notification Log", filters)
	if not limit:
		return total, []
	rows = frappe.get_list(
		"Notification Log",
		filters=filters,
		fields=["name", "type", "subject", "document_type", "document_name", "from_user", "creation"],
		order_by="creation desc",
		start=offset,
		page_length=limit,
	)
	return total, [
		{
			"id": r.name,
			"type": r.type,
			"subject": _text(r.subject),
			"doctype": r.document_type,
			"name": r.document_name,
			"from": get_fullname(r.from_user) if r.from_user else None,
			"date": cstr(r.creation),
		}
		for r in rows
	]


def get_my_work(spec: dict) -> dict:
	"""Counts and the requested rows of each part; spec: {approvals: n, todos: n, notifications: n, offset: {part: n}}."""
	offset = spec.get("offset") or {}
	open_counts = (get_notifications() or {}).get("open_count_doctype") or {}
	approvals_total, approvals = _approvals(_limit(spec, "approvals"), int(offset.get("approvals") or 0))
	todos_total, todos = _todos(_limit(spec, "todos"), int(offset.get("todos") or 0))
	notes_total, notes = _notifications(_limit(spec, "notifications"), int(offset.get("notifications") or 0))
	return {
		"counts": {
			"approvals": approvals_total,
			"open_workflow_actions": open_counts.get("Workflow Action"),
			"todos": todos_total,
			"notifications": notes_total,
		},
		"approvals": approvals,
		"todos": todos,
		"notifications": notes,
	}
