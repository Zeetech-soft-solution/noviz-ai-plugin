# The generic call-dispatcher. This is the WHOLE point of a thin plugin:
# it knows how to run a literal {kind, doctype, filters, fields}
# instruction using Frappe's own ORM — nothing about what a "quotation"
# or a "customer" IS, nothing about business rules, nothing that would
# need to change if the central server adds a new entity tomorrow. Every
# call runs as frappe.session.user, whoever is actually logged in right
# now — real, native ERPNext permission enforcement applies exactly as
# if they'd used ERPNext's own UI, no separate credential involved.
import json

import frappe

SUPPORTED_KINDS = {"get_list", "get_doc"}


def _json_safe(value):
	# frappe.get_list/get_doc return real Python date/datetime/Decimal
	# objects for those field types — stdlib json (which `requests`
	# uses under the hood to serialize the body we send back to the
	# relay) can't encode those directly. frappe.as_json already knows
	# how to (it's the same encoder every frappe.whitelist() response
	# goes through), so round-tripping through it here gives back a
	# plain, JSON-safe structure instead of a bespoke encoder.
	return json.loads(frappe.as_json(value))


def execute_call_spec(spec: dict):
	kind = spec.get("kind")
	doctype = spec.get("doctype")
	if not doctype:
		frappe.throw("Noviz AI: the relay sent a call spec with no doctype — cannot execute it.")
	if kind not in SUPPORTED_KINDS:
		frappe.throw(f'Noviz AI: this plugin does not know how to execute call kind "{kind}" (only {sorted(SUPPORTED_KINDS)} are supported).')

	if kind == "get_list":
		rows = frappe.get_list(
			doctype,
			fields=spec.get("fields") or ["name"],
			filters=spec.get("filters"),
			limit_page_length=spec.get("limit") or 20,
			limit_start=spec.get("start") or 0,
		)
		return _json_safe(rows)

	# kind == "get_doc"
	name = spec.get("name")
	if not name:
		frappe.throw('Noviz AI: a "get_doc" call spec requires a "name" — cannot execute it.')
	doc = frappe.get_doc(doctype, name)
	# Real permission check, not implied by get_doc alone succeeding —
	# frappe.get_doc can construct the object before a permission check
	# has actually run in every code path; this is the same explicit
	# check ERPNext's own REST GET-by-name endpoint performs.
	if not doc.has_permission("read"):
		frappe.throw(f'Noviz AI: you do not have permission to read this {doctype} record.', frappe.PermissionError)
	return _json_safe(doc.as_dict())
