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

SUPPORTED_KINDS = {"get_list", "get_doc", "create_doc", "update_doc", "reply_communication", "send_communication", "mark_notification_read", "run_report", "list_inbox_emails", "send_reply_email"}


def _json_safe(value):
	# frappe.get_list/get_doc return real Python date/datetime/Decimal
	# objects for those field types — stdlib json (which `requests`
	# uses under the hood to serialize the body we send back to the
	# relay) can't encode those directly. frappe.as_json already knows
	# how to (it's the same encoder every frappe.whitelist() response
	# goes through), so round-tripping through it here gives back a
	# plain, JSON-safe structure instead of a bespoke encoder.
	return json.loads(frappe.as_json(value))


def _normalize_report_result(message: dict):
	# Mirrors erpnextConnector.ts's own normalizeReportResult() exactly —
	# ERPNext's real report output shape varies by report type/version:
	# `result` is sometimes already a list of dicts, sometimes a list of
	# plain row-arrays that need zipping against `columns` (which is
	# itself sometimes a list of plain strings like "customer:Link/
	# Customer:120", sometimes a list of {fieldname, label, ...} dicts).
	# Kept as its own real Python port (not a second HTTP round trip back
	# through the relay) since this runs directly against ERPNext's own
	# in-process report result — no reason to serialize it twice.
	if not message or not isinstance(message.get("result"), list):
		return []
	result = message["result"]
	columns = message.get("columns") or []
	if result and not isinstance(result[0], list):
		return [r for r in result if isinstance(r, dict)]  # dict rows only — ERPNext appends a positional "Total" list-row to AR/AP Summary, GL, Trial Balance, etc.
	keys = []
	for c in columns:
		if isinstance(c, str):
			keys.append(c.split(":")[0])
		elif isinstance(c, dict):
			keys.append(c.get("fieldname") or c.get("label") or "value")
		else:
			keys.append("value")
	rows = []
	for row in result:
		rows.append({keys[i]: row[i] for i in range(min(len(keys), len(row)))})
	return rows


def execute_call_spec(spec: dict):
	kind = spec.get("kind")
	if kind not in SUPPORTED_KINDS:
		frappe.throw(f'Noviz AI: this plugin does not know how to execute call kind "{kind}" (only {sorted(SUPPORTED_KINDS)} are supported).')

	if kind == "run_report":
		# A real ERPNext named report (General Ledger, Profit and Loss,
		# Stock Balance, ...) — report_name is the report's own real
		# ERPNext name (see reportMap.ts's own ERPNEXT_REPORT_MAP,
		# central's real reportKey -> reportName translation), filters is
		# ERPNext's own native filter dict for that specific report, NOT
		# a [field, op, value] triple array like get_list uses (a real,
		# report-specific shape — every ERPNext report defines its own
		# filter fieldnames in its own .py/.js, there is no one generic
		# filter contract for reports the way there is for a plain
		# doctype list). frappe.desk.query_report.run() is the exact same
		# real, whitelisted function ERPNext's own desk Query Report
		# screen calls — it runs the report's real permission checks
		# internally (raises frappe.PermissionError for a report/doctype
		# this session's real role can't access), same as get_doc/
		# get_list's own explicit checks above rely on for everything else.
		report_name = spec.get("reportName")
		if not report_name:
			frappe.throw('Noviz AI: a "run_report" call spec requires a "reportName" — cannot execute it.')
		from frappe.desk.query_report import run as run_query_report

		message = run_query_report(report_name=report_name, filters=spec.get("reportFilters") or {})
		return _normalize_report_result(message)

	if kind == "list_inbox_emails":
		# A live, read-only IMAP fetch (see email_reader.py's own doc
		# comment for the full rationale — this replaced an earlier
		# approach that reused Frappe's own Email Account/POP3 machinery,
		# which turned out to delete messages from the real server as a
		# side effect). No doctype/permission check needed here — this
		# never touches any ERPNext document, it only reads a live
		# mailbox.
		from noviz_ai.email_reader import fetch_recent_emails

		limit = spec.get("limit") or 10
		return _json_safe(fetch_recent_emails(limit=limit))

	if kind == "send_reply_email":
		# The send-side counterpart — a real SMTP send (email_sender.py),
		# addressed directly (to/subject/body), no Communication record
		# lookup required. This is the correct reply path for an email
		# that came from list_inbox_emails above (a live IMAP fetch has
		# no local ERPNext document to reference at all) — reply_communication
		# below still exists for the separate, doctype-linked-thread case.
		values = spec.get("values") or {}
		to_address = values.get("to")
		subject = values.get("subject")
		body = values.get("body")
		if not (to_address and subject and body):
			frappe.throw('Noviz AI: a "send_reply_email" call spec requires values.to, values.subject, and values.body — cannot execute it.')
		from noviz_ai.email_sender import send_reply

		send_reply(to_address, subject, body)
		return {"sent": True, "to": to_address}

	doctype = spec.get("doctype")
	if not doctype:
		frappe.throw("Noviz AI: the relay sent a call spec with no doctype — cannot execute it.")

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
		# Real bug found live 2026-08-20: "order_by" was never read from
		# the call spec at all, even though the relay's own tool schema
		# (sortBy/sortDir) has always advertised real sorting as
		# supported — so "bring me 5 latest quotation" silently got
		# whatever order frappe.get_list()'s own default happens to be
		# (NOT what the model actually asked for), and every "latest N"/
		# "top N"/"oldest N" question on the relay was affected the same
		# way. The local (non-relay) product's own erpnextConnector.ts
		# already builds a real order_by string with this exact tie-break
		# shape — mirrored here so both paths behave identically.
		rows = frappe.get_list(
			doctype,
			fields=spec.get("fields") or ["name"],
			filters=spec.get("filters"),
			order_by=spec.get("order_by"),
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
		# Sends a REAL reply email — 2026-08-22: switched from Frappe's own
		# frappe.core.doctype.communication.email.make() (which sends through
		# whatever Email Account is configured in Frappe) to our own
		# email_sender.py (email_reader.py's send-side counterpart, same
		# dedicated Noviz AI Settings SMTP fields as list_inbox_emails/
		# send_reply_email use) — explicit product decision: this plugin
		# should never depend on Frappe's own email configuration for
		# anything, full stop, regardless of what a given site happens to
		# have set there. Still creates a real local Communication record
		# afterward (a plain insert(), no send_email flag — the actual
		# sending already happened above) so the reply keeps showing up on
		# the linked document's own timeline, same real value the old path
		# had; only the SMTP transport changed. PDF-attachment-by-print-
		# format (make()'s own optional feature) is not carried over here —
		# a real, separate follow-up if ever needed.
		name = spec.get("name")
		if not name:
			frappe.throw('Noviz AI: a "reply_communication" call spec requires a "name" (the original Communication id) — cannot execute it.')
		values = spec.get("values") or {}
		reply_body = values.get("reply_body")
		if not reply_body:
			frappe.throw('Noviz AI: a "reply_communication" call spec requires "values.reply_body" — cannot execute it.')

		original = frappe.get_doc("Communication", name)
		# Real permission check on the ORIGINAL email — this plugin's own
		# gate now that the send no longer routes through make()'s own
		# internal permission check.
		if not original.has_permission("read"):
			frappe.throw("Noviz AI: you do not have permission to read this email.", frappe.PermissionError)

		from noviz_ai.email_sender import send_reply

		subject = original.subject or ""
		if not subject.lower().startswith("re:"):
			subject = f"Re: {subject}"

		send_reply(original.sender, subject, reply_body)

		settings = frappe.get_single("Noviz AI Settings")
		reply_doc = frappe.get_doc({
			"doctype": "Communication",
			"communication_type": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Sent",
			"reference_doctype": original.reference_doctype or None,
			"reference_name": original.reference_name or None,
			"subject": subject,
			"content": reply_body,
			"sender": settings.email_username,
			"recipients": original.sender,
			"in_reply_to": original.name,
		})
		reply_doc.insert()
		# The reply email already left the building via our own SMTP by this
		# point — an irreversible external action. Committing explicitly
		# makes sure the local Communication record survives even if
		# something later in this same request throws; without it, Frappe's
		# own error-path rollback would silently erase the only local record
		# of a real email that already sent.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		return _json_safe(reply_doc.as_dict())

	if kind == "send_communication":
		# A genuinely FRESH outbound email — no existing Communication
		# thread to reply to (that's reply_communication's own job above).
		# Same 2026-08-22 switch to our own SMTP (email_sender.py) instead
		# of Frappe's configured Email Account, same reasoning. No linked-
		# document/PDF-attachment support — a real, separate follow-up.
		values = spec.get("values") or {}
		recipients = values.get("recipients")
		subject = values.get("subject")
		content = values.get("content")
		if not recipients or not subject or not content:
			frappe.throw('Noviz AI: a "send_communication" call spec requires values.recipients, values.subject, and values.content — cannot execute it.')

		from noviz_ai.email_sender import send_reply

		send_reply(recipients, subject, content)

		settings = frappe.get_single("Noviz AI Settings")
		sent_doc = frappe.get_doc({
			"doctype": "Communication",
			"communication_type": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Sent",
			"subject": subject,
			"content": content,
			"sender": settings.email_username,
			"recipients": recipients,
		})
		sent_doc.insert()
		# Same real reason as reply_communication above: the send already
		# happened, so the local record of it must not be at the mercy of
		# whatever runs next in this same request.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		return _json_safe(sent_doc.as_dict())

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
		# Real user-facing state (an unread badge count) — committing
		# immediately means it can't get silently undone by an unrelated
		# later failure in this same request, same reasoning as the write
		# path below, just for a smaller, purely-local mutation.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
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
		# The document genuinely exists in ERPNext the moment insert()
		# returns (real hooks/side effects may already have fired off of
		# it). Committing here decouples "the write happened" from "the
		# response serialized cleanly" — a failure in _json_safe() below
		# must never silently roll back a document the person was just
		# told, or is about to be told, was created.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
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
	# Same reasoning as create_doc above — the update already landed once
	# save() returns; committing here keeps that fact independent of
	# whatever the response-serialization step below does afterward.
	frappe.db.commit()  # nosemgrep: frappe-manual-commit
	return _json_safe(doc.as_dict())
