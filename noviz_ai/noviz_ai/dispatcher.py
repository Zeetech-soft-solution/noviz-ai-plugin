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

SUPPORTED_KINDS = {"get_list", "get_doc", "create_doc", "update_doc", "reply_communication", "mark_notification_read"}


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
		# Real permission check, not implied by frappe.get_list() alone —
		# same explicit discipline as get_doc's own check below, added for
		# the same real reason: real bug found live 2026-08-19, a user with
		# genuinely ZERO read permission on a doctype (Sales Order, for a
		# System-Manager-only account with no functional role) got a real
		# frappe.PermissionError from a plain .list call — correctly
		# surfaced by api.py's own error-catching — but the SAME
		# permission gap, reached through analytics.aggregate's own
		# multi-page get_list calls, silently came back as an empty page
		# (count 0) instead, because frappe.get_list() doesn't reliably
		# throw for every real permission shape (some doctypes/roles
		# resolve to a filtered-empty result instead of an outright deny).
		# The model then reported "there are no accounts receivable" — a
		# false claim about the DATA when the real problem was access, the
		# exact failure SYSTEM_PROMPT's own "STATUS/ENUM FIELDS" section
		# already warns against for a different cause. A real, explicit
		# check here makes both paths behave identically and correctly.
		if not frappe.has_permission(doctype, "read"):
			frappe.throw(f"Noviz AI: you do not have permission to read {doctype} records.", frappe.PermissionError)
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

	if kind == "reply_communication":
		# Sends a REAL reply email — reuses Frappe's own real, whitelisted
		# frappe.core.doctype.communication.email.make(), the exact function
		# ERPNext's own desk "Reply" button calls. Deliberately NOT a raw
		# Communication insert() (would leave a record that LOOKS like an
		# email but was never actually sent through SMTP) and NOT a
		# hand-assembled frappe.sendmail() (make() already handles real
		# threading via in_reply_to, and optional PDF-attachment-by-
		# print-format, correctly).
		name = spec.get("name")
		if not name:
			frappe.throw('Noviz AI: a "reply_communication" call spec requires a "name" (the original Communication id) — cannot execute it.')
		values = spec.get("values") or {}
		reply_body = values.get("reply_body")
		if not reply_body:
			frappe.throw('Noviz AI: a "reply_communication" call spec requires "values.reply_body" — cannot execute it.')

		original = frappe.get_doc("Communication", name)
		# Real permission check on the ORIGINAL email — separate from, and
		# in addition to, the permission check make() itself runs below
		# against whatever document the thread is linked to (a different,
		# real "email" ptype check, not implied by construction alone).
		if not original.has_permission("read"):
			frappe.throw("Noviz AI: you do not have permission to read this email.", frappe.PermissionError)

		from frappe.core.doctype.communication.email import make as make_communication

		subject = original.subject or ""
		if not subject.lower().startswith("re:"):
			subject = f"Re: {subject}"

		kwargs = dict(
			doctype=original.reference_doctype or None,
			name=original.reference_name or None,
			content=reply_body,
			subject=subject,
			recipients=original.sender,
			communication_medium="Email",
			send_email=1,
			in_reply_to=original.name,
		)
		print_format = values.get("attach_print_format")
		if print_format and original.reference_doctype and original.reference_name:
			kwargs["print_format"] = print_format
		result = make_communication(**kwargs)
		frappe.db.commit()
		return _json_safe(result)

	if kind == "mark_notification_read":
		# Reuses Frappe's own real, privileged mark_as_read() — Notification
		# Log's own real DocPerm grants "All" read/share but no write at
		# all (Frappe routes this specific mutation through a whitelisted
		# function scoped to the CALLING user's own for_user rows instead),
		# so a generic doc.save() here would 403 for a real, ordinary user.
		name = spec.get("name")
		if not name:
			frappe.throw('Noviz AI: a "mark_notification_read" call spec requires a "name" — cannot execute it.')

		from frappe.desk.doctype.notification_log.notification_log import mark_as_read

		mark_as_read(name)
		frappe.db.commit()
		return {"ok": True, "id": name}

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
