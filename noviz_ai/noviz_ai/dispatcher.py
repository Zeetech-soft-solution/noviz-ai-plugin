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

SUPPORTED_KINDS = {"get_list", "get_doc", "create_doc", "update_doc"}


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

	if kind == "get_doc":
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
		full = _json_safe(doc.as_dict())
		# Real bug found live 2026-08-18: doc.as_dict() alone returns
		# EVERY field on the real ERPNext doctype — 90+ internal/technical
		# fields (docstatus, naming_series, base_*, ...) plus raw nested
		# child-table arrays (items, payment_schedule) — none of which a
		# real person asked to see. When the relay's own call spec names the
		# specific fields it actually wants (the normal case — see
		# relayCallTranslator.ts's own doc comment), narrow to exactly
		# those. No fields specified -> full dict, same as before, so this
		# stays backward compatible with any caller that genuinely wants
		# everything.
		fields = spec.get("fields")
		if not fields:
			return full
		return {f: full.get(f) for f in fields}

	# kind == "create_doc" / "update_doc" — the plugin's own real write
	# path. This app still has zero opinion on WHAT a Quotation or a
	# Journal Entry is (that stays central, in relayCallTranslator.ts's
	# toNativeData() field mapping); it only ever runs the literal
	# {doctype, values} instruction it's handed, through frappe's own ORM,
	# as whoever is actually logged in — the exact same permission model
	# ERPNext's own UI would apply to the same action, nothing bypassed
	# and nothing impersonated. `ignore_permissions` is deliberately never
	# passed (defaults to False on both insert() and save()) — a write
	# this session's real ERPNext role doesn't grant must fail with a
	# real frappe.PermissionError, exactly like using the UI directly
	# would, not silently succeed because it arrived through chat instead.
	values = spec.get("values")
	if not isinstance(values, dict):
		frappe.throw(f'Noviz AI: a "{kind}" call spec requires "values" — cannot execute it.')

	if kind == "create_doc":
		doc = frappe.get_doc({"doctype": doctype, **values})
		doc.insert()
		frappe.db.commit()
		return _json_safe(doc.as_dict())

	# kind == "update_doc"
	name = spec.get("name")
	if not name:
		frappe.throw('Noviz AI: an "update_doc" call spec requires a "name" — cannot execute it.')
	doc = frappe.get_doc(doctype, name)
	if not doc.has_permission("write"):
		frappe.throw(f'Noviz AI: you do not have permission to update this {doctype} record.', frappe.PermissionError)
	doc.update(values)
	doc.save()
	frappe.db.commit()
	return _json_safe(doc.as_dict())
