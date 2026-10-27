# Document actions (call kinds "get_actions" and "run_action"): what can
# happen next to one document and running it. ERPNext owns the process:
# the workflow transitions this user may take, submit and cancel come from
# Frappe itself, and every action runs as frappe.session.user through
# Frappe's own functions, so permissions, workflow conditions and ERPNext's
# own refusal messages apply exactly as in the Desk. The relay only declares
# the "make" and "server" actions it may offer (method names), as data.
import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name


def _read_doc(spec: dict):
	doctype = spec.get("doctype")
	name = spec.get("name")
	if not doctype or not name:
		frappe.throw('Noviz AI: document actions need "doctype" and "name".')
	doc = frappe.get_doc(doctype, name)
	if not doc.has_permission("read"):
		frappe.throw(f"Noviz AI: you do not have permission to read this {doctype} record.", frappe.PermissionError)
	return doc


def _whitelisted(method: str):
	# Only a method the user could call through the API with their own
	# session anyway: frappe.is_whitelisted raises for anything else.
	if not method or not isinstance(method, str):
		frappe.throw("Noviz AI: this action has no method.")
	fn = frappe.get_attr(method)
	frappe.is_whitelisted(fn)
	return fn


def get_actions(spec: dict) -> dict:
	doc = _read_doc(spec)
	actions = []
	workflow = get_workflow_name(doc.doctype)
	state = None
	if workflow:
		state_field = frappe.get_cached_value("Workflow", workflow, "workflow_state_field") or "workflow_state"
		state = doc.get(state_field)
		for t in get_transitions(doc):
			actions.append({"kind": "workflow", "action": t.get("action"), "next_state": t.get("next_state")})
	else:
		# With a workflow, submit and cancel happen through its transitions.
		if frappe.get_meta(doc.doctype).is_submittable:
			if doc.docstatus == 0 and doc.has_permission("submit"):
				actions.append({"kind": "submit"})
			if doc.docstatus == 1 and doc.has_permission("cancel"):
				actions.append({"kind": "cancel"})
	for offer in spec.get("offer") or []:
		kind = offer.get("kind")
		if kind == "make":
			target = offer.get("targetDoctype")
			if target and not frappe.has_permission(target, "create"):
				continue
		elif kind != "server":
			continue
		actions.append({"kind": kind, "action": offer.get("name"), "label": offer.get("label")})
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"docstatus": doc.docstatus,
		"status": doc.get("status"),
		"workflow": workflow,
		"workflow_state": state,
		"actions": actions,
	}


def run_action(spec: dict) -> dict:
	doc = _read_doc(spec)
	action = spec.get("action") or {}
	kind = action.get("kind")
	values = action.get("values") or {}

	if kind == "workflow":
		doc = apply_workflow(doc, action.get("action"))
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		return {"ok": True, "doctype": doc.doctype, "name": doc.name, "docstatus": doc.docstatus, "workflow_state": doc.get("workflow_state"), "status": doc.get("status")}

	if kind in ("submit", "cancel"):
		if get_workflow_name(doc.doctype):
			frappe.throw(f"Noviz AI: {doc.doctype} follows a workflow; use its workflow actions instead of {kind}.")
		doc.submit() if kind == "submit" else doc.cancel()
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		return {"ok": True, "doctype": doc.doctype, "name": doc.name, "docstatus": doc.docstatus, "status": doc.get("status")}

	if kind == "make":
		# ERPNext's own mapper builds the next document; it is saved as a
		# draft, as the Desk does when the user saves the mapped form.
		new_doc = _whitelisted(action.get("method"))(source_name=doc.name)
		if isinstance(new_doc, dict):
			new_doc = frappe.get_doc(new_doc)
		if values:
			new_doc.update(values)
		new_doc.insert()
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		return {"ok": True, "doctype": new_doc.doctype, "name": new_doc.name, "docstatus": new_doc.docstatus, "status": new_doc.get("status")}

	if kind == "server":
		result = _whitelisted(action.get("method"))(doctype=doc.doctype, name=doc.name, **values)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		return {"ok": True, "doctype": doc.doctype, "name": doc.name, "result": result}

	frappe.throw(f'Noviz AI: unknown document action kind "{kind}".')
