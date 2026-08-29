# Noviz AI — thin client plugin. This file, together with dispatcher.py,
# is the ENTIRE extent of what this app knows how to do: forward a chat
# message to the central Noviz AI relay, execute whatever generic data
# call it asks for using this site's own already-authenticated session,
# and hand the result back. It has zero knowledge of what any of it
# MEANS — no entity names, no business rules, no prompts. All of that
# stays on the central server (see erp-agent-platform, private) and is
# never shipped here. See README.md for the full architecture and why
# this repo is open source while the central brain is not.
import frappe
import requests

from noviz_ai.dispatcher import execute_call_spec

# A single request/response round trip to the relay can, in principle,
# take a while (the model reasoning, then us executing a real ERPNext
# call, repeated a few times) — generous but bounded, matching the
# central server's own documented turn-time budget.
#
# Real gap found live 2026-08-21: the relay's own OpenAI client
# (openaiProvider.ts) retries up to 5 times on a timeout/429, each
# attempt allowed up to 25s — a legitimate worst case of ~130s before
# the relay itself gives up. At the old 30s value, THIS timeout fired
# first on a slow-but-eventually-successful turn: the person saw a
# "could not reach the relay server" error while the relay kept working
# and marked the turn "completed" server-side, an answer nobody ever
# saw. 150s gives real headroom above that worst case (also comfortably
# under nginx's own proxy_read_timeout on the ERPNext side, bumped to
# match — see sites-available/sunrise.noviz.in).
REQUEST_TIMEOUT_SECONDS = 150
# Real, hard ceiling on how many fetch/continue round trips one chat
# message can trigger — never infinite. A relay bug or a misbehaving
# model asking for tool after tool after tool should fail loudly with a
# clear message, not hang this request (or the user's browser) forever.
# Raised 10 -> 30 (explicit product ask, 2026-08-26): a real multi-part
# question (several groupBy/metrics breakdowns plus a monthly trend in
# one turn) can legitimately need more than 10 real fetches even after
# relayReasoningEngine.ts's own groupByPeriod fix cut per-trend cost down
# to one fetch per metric — this is a genuine ceiling raise, not a
# workaround for that bug. Still bounded, not infinite; REQUEST_TIMEOUT_SECONDS
# above is the other real backstop if round trips are individually slow.
MAX_ROUND_TRIPS = 30


def _settings():
	# 2026-08-21: the standalone "Enabled" checkbox was removed - a real
	# AI Relay Token being present IS "enabled" now, no separate manual
	# toggle to forget to flip. This is the one real gate chat has to
	# clear before it can run at all.
	settings = frappe.get_single("Noviz AI Settings")
	if not settings.relay_base_url or not settings.get_password("api_key"):
		frappe.throw(
			"We don't have a relay token configured yet for this site. Ask your administrator to "
			'<a href="https://noviz.in/pricing.html" target="_blank" rel="noopener">get an AI Relay Token</a> '
			"and enter it under Noviz AI Settings."
		)
	return settings


def _relay_headers(settings):
	return {"Authorization": f"Bearer {settings.get_password('api_key')}", "Content-Type": "application/json"}


def _post(url, json_body, headers, session=None):
	"""One real request/response round trip, with clean, honest error
	messages for the two real failure shapes a site admin can hit —
	never a raw requests.exceptions traceback or an opaque HTTPError
	surfaced through frappe's own generic error dialog.

	A 401 here means the RELAY rejected this site's own configured API
	key — invalid, revoked, or (a real, common case) a trial that has
	expired. This is NOT the same situation as an external party probing
	the relay's public API to fingerprint tenant state (that's
	tenantMiddleware.ts's own deliberately-generic "Invalid API key" on
	the SERVER side, a real, separate decision) — this message is shown
	only to THIS site's own logged-in user, about THEIR OWN site's own
	configuration, so being specific and actionable here is genuinely
	helpful, not a leak.

	`session` (optional): a requests.Session to route this call through,
	so repeated round trips within the SAME turn (see send_message's own
	fetch/continue loop) reuse one already-negotiated TCP+TLS connection
	to the relay instead of paying a fresh handshake on every single
	round trip — a real, measured latency cost on top of the relay's own
	extra network hop (see relayReasoningEngine.ts's own doc comment on
	why the relay architecture is inherently slower than a direct-
	connection engine; this at least stops making it slower than it has
	to be). Falls back to a one-off `requests.post` when no session is
	given (get_status's own pre-flight check, a single call with nothing
	to reuse a connection FOR).
	"""
	poster = session.post if session else requests.post
	try:
		response = poster(url, json=json_body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
	except requests.exceptions.RequestException as e:
		frappe.throw(f"Noviz AI could not reach the relay server ({e}). Check the Relay Base URL in Noviz AI Settings, or try again shortly.")
	if response.status_code == 401:
		# A clear, actionable message instead of a bare 401. Deliberately
		# does not distinguish "unknown key" from "real key, subscription
		# lapsed" — that distinction stays hidden at the relay's own auth
		# layer on purpose (see tenantMiddleware.ts: never let a raw 401
		# response confirm whether a given key string is real). This is
		# just a clearer message for the same underlying case ("chat
		# isn't working right now"), with a link to activate/renew
		# instead of a dead end.
		frappe.throw(
			"Noviz AI's key needs to be activated. Your API key may be invalid, revoked, or your subscription may "
			"have lapsed. Ask your administrator to check Noviz AI Settings, or "
			'<a href="https://noviz.in/pricing.html" target="_blank" rel="noopener">get your API key</a>.'
		)
	if response.status_code == 402:
		# Real, explicit fix (2026-08-27) — the relay's own single access
		# checkpoint (tenantMiddleware.ts's requireTenantAuth) now returns
		# 402 for a genuinely different case than 401: a real, active,
		# validly-keyed tenant that has used up either the monthly OR the
		# weekly token budget (admin-configured incoming/outgoing limits,
		# or the paid plan's own monthly allowance). Without this branch
		# it fell through to raise_for_status() below and surfaced as a
		# raw, unhandled HTTPError — Frappe's own generic error dialog
		# instead of an honest, specific message. The relay's own error
		# text already says exactly which budget (month or week) and the
		# real resume date; shown as-is rather than re-worded here so the
		# two stay in sync automatically instead of drifting apart. The
		# fallback below is a rare backstop (a genuinely missing error
		# field), deliberately generic rather than naming a specific
		# period/date it can't actually know.
		frappe.throw(
			response.json().get(
				"error",
				"Noviz AI's usage budget has been used up. Contact Noviz AI to add capacity, or it resumes automatically at the next reset.",
			)
		)
	response.raise_for_status()
	return response.json()


@frappe.whitelist()
def get_status():
	"""Real pre-flight check the chat page calls BEFORE ever rendering
	the input box — lets it show a clear "not set up yet" screen instead
	of silently offering a chat box that will fail the moment someone
	actually tries to use it (the ONLY way this worked before this
	existed: type a question, get a raw error dialog). Deliberately never
	touches the relay and never throws — purely local Settings state, so
	this is always safe to call even when nothing is configured at all,
	unlike send_message's own _settings() (which throws on purpose, once
	an actual chat attempt is made).
	"""
	settings = frappe.get_single("Noviz AI Settings")
	configured = bool(settings.relay_base_url and settings.get_password("api_key", raise_exception=False))
	return {
		"configured": configured,
		# Only a user who could actually fix the config (write access on
		# the Settings doctype - System Manager by default, see that
		# doctype's own permissions) gets a direct "configure it" link;
		# everyone else gets a plain "ask your administrator" message,
		# never a dead-end link they can't do anything with.
		"can_configure": frappe.has_permission("Noviz AI Settings", "write"),
	}


def sync_module_policies(settings=None):
	"""Pushes this site's own Company Policy table (Noviz AI Settings'
	`module_policies` child table) up to the relay — called from that
	doctype's own on_update hook (noviz_ai_settings.py), never called
	directly from the chat page. Frappe's own child table IS the source
	of truth for what's shown/edited here (real, durable, versioned, no
	separate fetch-to-populate-the-form step needed); this is purely the
	one-way sync so the relay has its own copy to read at every chat
	turn without a live round-trip back into this site (see
	tenantPolicyService.ts's own doc comment for the full "why").

	Deliberately swallows its own failure rather than blocking the
	settings save — a relay hiccup here shouldn't stop an admin from
	saving their own local ERPNext record; the next successful save
	naturally re-syncs the full current state anyway (see relay.routes.ts's
	own POST /policies — always the full set, not a diff).
	"""
	settings = settings or frappe.get_single("Noviz AI Settings")
	if not (settings.relay_base_url and settings.get_password("api_key", raise_exception=False)):
		return
	try:
		base_url = settings.relay_base_url.rstrip("/")
		headers = _relay_headers(settings)
		policies = [
			{"module": row.module, "strict_policy": row.strict_policy or "", "warning_policy": row.warning_policy or ""}
			for row in (settings.module_policies or [])
		]
		requests.post(f"{base_url}/v1/agent/policies", json={"policies": policies}, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
	except requests.exceptions.RequestException as e:
		frappe.log_error(title="Noviz AI: policy sync failed", message=str(e))


def _execute_call_spec_safely(call_spec):
	"""Real ERPNext document calls fail for real, EXPECTED reasons — a
	record deleted since the model last saw it, a permission this
	specific logged-in person genuinely doesn't have, a validation a
	create/update genuinely violates (a duplicate, a missing mandatory
	field). Real bug found live: these used to propagate straight up as
	an unhandled exception out of execute_call_spec, which crashed the
	WHOLE chat request with a raw Frappe error dialog — the person got no
	answer at all, not even an explanation. Catching the real, NAMED
	ERPNext exception types here and handing back the same {"error": ...}
	shape the relay's own rejection paths already use (a bad tool name, a
	failed translation) lets the model see the real failure and explain
	it naturally in the conversation instead — "that record doesn't seem
	to exist anymore" rather than a crashed request. ValidationError's own
	real subclasses (MandatoryError, DuplicateEntryError,
	UniqueValidationError, ...) are all caught by the one ValidationError
	branch, not enumerated separately — that's the actual Frappe exception
	hierarchy, not guessed. A genuinely unexpected failure (not one of
	these three real, named types) still gets logged for real
	investigation (frappe.log_error) — this only ever changes what the
	CHAT sees, never silently hides a bug from the site's own error log.
	"""
	try:
		return execute_call_spec(call_spec)
	except frappe.PermissionError as e:
		return {"error": f"You don't have permission to do that in ERPNext: {e}"}
	except frappe.DoesNotExistError as e:
		return {"error": f"That record doesn't exist in ERPNext (it may have been deleted or renamed): {e}"}
	except frappe.ValidationError as e:
		return {"error": f"ERPNext rejected that: {e}"}
	except Exception as e:
		frappe.log_error(title="Noviz AI: unexpected error executing a call spec", message=frappe.get_traceback())
		return {"error": f"Something unexpected went wrong on the ERPNext side ({type(e).__name__}) — this has been logged for the administrator."}


def _drive_fetch_continue_loop(result, base_url, headers, session):
	"""Shared by send_message and scan_image — both start a turn one
	different way (a typed prompt vs a scanned image), but from here on
	it's the exact same real fetch/continue machine: keep executing
	whatever generic call the relay asks for, using this site's own
	already-authenticated session (dispatcher.py), until it finalizes.
	The browser only ever sees the final {"status": "final", ...} once
	this returns, never the intermediate relay round trips.
	"""
	round_trips = 0
	while result.get("status") == "fetch":
		round_trips += 1
		if round_trips > MAX_ROUND_TRIPS:
			frappe.throw(f"Noviz AI: this turn needed more than {MAX_ROUND_TRIPS} data fetches — stopping rather than looping forever.")

		call_spec = result["request"]
		# The ONLY place this app ever touches real ERPNext data — see
		# dispatcher.py's own doc comment. See _execute_call_spec_safely's
		# own doc comment for why real ERPNext errors are caught here
		# rather than left to crash the whole request.
		data = _execute_call_spec_safely(call_spec)

		result = _post(f"{base_url}/v1/agent/turn/continue", {"turnId": result["turnId"], "result": data}, headers, session)

	return result


@frappe.whitelist()
def send_message(prompt: str, previous_turn_id: str = None):
	"""The one real entry point real users hit from the chat page for a
	typed message. See _drive_fetch_continue_loop's own doc comment for
	what happens after the first request.

	`previous_turn_id` (optional): real conversation memory — pass back
	the LAST final result's own "turnId" so the relay can load that
	conversation's history and continue it, instead of starting a
	completely fresh one every single message. The chat page's own JS
	tracks this across messages within one page load; a reload starts a
	genuinely new conversation, same session boundary Pro's own chat
	memory already uses. A missing/stale/wrong-tenant one fails
	gracefully server-side (relayReasoningEngine.ts's own doc comment) —
	never a hard error here either.
	"""
	if not prompt or not prompt.strip():
		frappe.throw("prompt is required")

	settings = _settings()
	base_url = settings.relay_base_url.rstrip("/")
	headers = _relay_headers(settings)

	# One real TCP+TLS connection to the relay, reused for every round
	# trip THIS turn needs (see _post's own doc comment) — opened once
	# here, closed automatically at the end of this function regardless
	# of how the loop below exits (return or an exception propagating
	# out of execute_call_spec/_post).
	with requests.Session() as session:
		result = _post(
			f"{base_url}/v1/agent/turn",
			{
				"prompt": prompt,
				"previous_turn_id": previous_turn_id,
				# The real logged-in person's own identity/roles — never a
				# credential. Real ERPNext DATA access is governed entirely
				# by dispatcher.py using frappe's own already-authenticated
				# session for whoever is actually logged in — this field
				# never widens or narrows that.
				"frappe_user": frappe.session.user,
				"frappe_roles": frappe.get_roles(frappe.session.user),
			},
			headers,
			session,
		)
		return _drive_fetch_continue_loop(result, base_url, headers, session)


@frappe.whitelist()
def next_page(tool: str, args: str):
	"""Real, explicit product ask (2026-08-22): "u generate next page
	urself too... now it needs to send llm, remove that" — a "Show me
	more"/"Download complete PDF" button click already carries the EXACT
	next query (relayReasoningEngine.ts's own NextStep.query) with zero
	reasoning required. This calls the relay's own /turn/next-page
	instead of /turn — same real fetch/continue machine below for a
	groupBy/metrics query (a genuine ERPNext round trip for the real rows
	is still unavoidable, the full computation has to actually re-run),
	but the relay never calls the LLM for this turn at all. `args`
	arrives as a JSON string (frappe.whitelist() only accepts primitive
	param types) — parsed here, same shape the button's own data-query
	attribute already carries client-side.
	"""
	import json

	if not tool or not tool.strip():
		frappe.throw("tool is required")

	settings = _settings()
	base_url = settings.relay_base_url.rstrip("/")
	headers = _relay_headers(settings)

	with requests.Session() as session:
		result = _post(
			f"{base_url}/v1/agent/turn/next-page",
			{
				"tool": tool,
				"args": json.loads(args) if args else {},
				"frappe_user": frappe.session.user,
				"frappe_roles": frappe.get_roles(frappe.session.user),
			},
			headers,
			session,
		)
		return _drive_fetch_continue_loop(result, base_url, headers, session)


@frappe.whitelist()
def scan_image(note: str = None, previous_turn_id: str = None):
	"""Real port of Pro's own attach/camera scan feature (Composer.tsx's
	📎/📷 buttons -> agent.routes.ts's /scan route -> documentScanner.ts),
	adapted for this thin-plugin architecture: the image itself travels
	to the CENTRAL relay (which does the real OpenAI vision OCR call —
	this plugin has no OpenAI key of its own, by design, same as every
	other LLM call), and everything AFTER that (verifying the named
	party, checking for a real matching record, actually creating
	something) drives through the exact same fetch/continue machine as
	a typed prompt — no shortcut around role-gating, business rules, or
	the "always confirm before creating" behavior a typed "create a
	purchase order for..." prompt already goes through.

	The uploaded file arrives the same way any Frappe file-upload
	whitelisted method receives one — `frappe.request.files`, not a
	regular `frappe.call` arg (browsers can't put binary file content
	into a JSON body) — see noviz_ai_chat.js's own upload code for the
	matching client side.
	"""
	upload = frappe.request.files.get("image") if frappe.request else None
	if not upload:
		frappe.throw("image is required (jpeg/png/webp, max 2MB)")

	settings = _settings()
	base_url = settings.relay_base_url.rstrip("/")
	# multipart/form-data, not JSON — the relay's own scan route uses
	# multer (real file upload middleware), matching agent.routes.ts's
	# own /scan route on the single-tenant product. Auth still travels
	# the same way (the Bearer header), just no "Content-Type: application/json"
	# this one time (requests sets the correct multipart header itself
	# once `files=` is used).
	headers = {"Authorization": f"Bearer {settings.get_password('api_key')}"}

	image_bytes = upload.read()
	mimetype = upload.content_type or "image/jpeg"

	with requests.Session() as session:
		try:
			response = session.post(
				f"{base_url}/v1/agent/scan",
				files={"image": (upload.filename, image_bytes, mimetype)},
				data={
					"frappe_user": frappe.session.user,
					"frappe_roles": frappe.as_json(frappe.get_roles(frappe.session.user)),
					"previous_turn_id": previous_turn_id or "",
					"note": note or "",
					# Real, generic own-company hint the relay uses to tell
					# "we're the recipient, not the customer/supplier" apart
					# — see relay.routes.ts's own /scan route doc comment.
					# frappe.defaults, not a hardcoded value, so this holds
					# for whatever company any given site actually runs as.
					"company_name": frappe.defaults.get_global_default("company") or "",
				},
				headers=headers,
				timeout=REQUEST_TIMEOUT_SECONDS,
			)
		except requests.exceptions.RequestException as e:
			frappe.throw(f"Noviz AI could not reach the relay server ({e}). Check the Relay Base URL in Noviz AI Settings, or try again shortly.")
		if response.status_code == 401:
			frappe.throw(
				"Noviz AI could not authenticate with the relay. Your API key may be invalid, revoked, or your trial may have expired. "
				"Ask your administrator to check Noviz AI Settings, or contact Noviz AI for a new key."
			)
		if response.status_code == 422:
			frappe.throw(response.json().get("error", "Could not read anything from this image — try a clearer, well-lit photo"))
		response.raise_for_status()
		result = response.json()

		json_headers = _relay_headers(settings)
		return _drive_fetch_continue_loop(result, base_url, json_headers, session)


@frappe.whitelist()
def generate_report_pdf(spec: str):
	"""report.generate's real, local half — see relayReasoningEngine.ts's
	own buildReportSpec doc comment for the full architecture ("why zero
	round trip", the real user ask that drove it: "not moving big data
	through traffic and llm"). `spec` is a small, real JSON description
	the relay already built (a doctype/report name, native field names,
	filters, column labels, a title — never a raw row, never SQL) — this
	fetches the REAL rows directly against ERPNext (zero network hop,
	same box) and renders the PDF locally (pdf_report.py), then streams
	it straight back.

	Real, deliberate security note: `spec` is plain, unsigned JSON a
	client could in principle edit before it reaches here — that's fine.
	The actual boundary is ERPNext's own real permission system
	(fetch_entity_rows'/run_named_report's own frappe.has_permission /
	query_report.run checks below), applied to whatever the ALREADY-
	AUTHENTICATED Frappe session calling this endpoint is actually
	allowed to see — exactly the same trust model get_list/get_doc
	already have in dispatcher.py. An edited spec can only ever ask for
	data this real person could already see some other way.
	"""
	import json

	try:
		parsed = json.loads(spec)
	except (TypeError, ValueError):
		frappe.throw("A valid report spec is required.")

	source = parsed.get("source")
	title = parsed.get("title") or "Report"
	columns = parsed.get("columns")

	from noviz_ai.pdf_report import columns_from_rows, fetch_entity_rows, render_table_pdf, run_aggregate_query, run_named_report

	if source == "named_report":
		report_name = parsed.get("reportName")
		if not report_name:
			frappe.throw("A report name is required.")
		rows = run_named_report(report_name, parsed.get("reportFilters"))
		if not columns:
			columns = columns_from_rows(rows)
		else:
			columns = columns_from_rows(rows, [c["key"] for c in columns])
	elif source == "entity_query":
		doctype = parsed.get("doctype")
		if not doctype:
			frappe.throw("A doctype is required.")
		rows = fetch_entity_rows(
			doctype,
			parsed.get("fields"),
			parsed.get("filters"),
			limit=parsed.get("limit"),
			order_by=parsed.get("order_by"),
		)
		if not columns:
			columns = columns_from_rows(rows)
	elif source == "aggregate_query":
		# The complete version of analytics.aggregate/database_engine.
		# execute_query's own groupBy result — see run_aggregate_query's
		# own doc comment for why this uses a real SQL GROUP BY rather
		# than a fetch-then-sum loop.
		doctype = parsed.get("doctype")
		group_by = parsed.get("groupBy")
		metrics = parsed.get("metrics")
		if not doctype or not group_by or not metrics:
			frappe.throw("A doctype, groupBy field, and at least one metric are required.")
		rows = run_aggregate_query(doctype, group_by, metrics, parsed.get("filters"))
		# columns is already the relay's own real, complete spec (group
		# field + each metric's own label) — never re-derived from rows
		# here, unlike named_report/entity_query above, since a group-by
		# result's own shape is already fully known ahead of the fetch.
	else:
		frappe.throw('spec.source must be "named_report", "entity_query", or "aggregate_query"')

	pdf_bytes = render_table_pdf(title, columns, rows)

	# Same real, standard Frappe "binary file download" response shape
	# frappe.utils.print_format.download_pdf itself uses — nothing
	# custom, no new dependency.
	safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:60].strip() or "report"
	frappe.local.response.filename = f"{safe_title}.pdf"
	frappe.local.response.filecontent = pdf_bytes
	frappe.local.response.type = "download"
