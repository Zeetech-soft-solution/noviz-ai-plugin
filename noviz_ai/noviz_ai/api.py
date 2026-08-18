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
REQUEST_TIMEOUT_SECONDS = 30
# Real, hard ceiling on how many fetch/continue round trips one chat
# message can trigger — never infinite. A relay bug or a misbehaving
# model asking for tool after tool after tool should fail loudly with a
# clear message, not hang this request (or the user's browser) forever.
MAX_ROUND_TRIPS = 10


def _settings():
	settings = frappe.get_single("Noviz AI Settings")
	if not settings.enabled:
		frappe.throw("Noviz AI is not enabled for this site. Ask your ERPNext administrator to configure it under Noviz AI Settings.")
	if not settings.relay_base_url or not settings.get_password("api_key"):
		frappe.throw("Noviz AI Settings is missing its Relay Base URL or API Key — ask your administrator to finish setup.")
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
		frappe.throw(
			"Noviz AI could not authenticate with the relay. Your API key may be invalid, revoked, or your trial may have expired. "
			"Ask your administrator to check Noviz AI Settings, or contact Noviz AI for a new key."
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
	configured = bool(settings.enabled and settings.relay_base_url and settings.get_password("api_key", raise_exception=False))
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
	if not (settings.enabled and settings.relay_base_url and settings.get_password("api_key", raise_exception=False)):
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
		# dispatcher.py's own doc comment. Whatever error it raises
		# (a bad doctype, a permission the current user genuinely
		# doesn't have) propagates straight up as a real frappe error,
		# same as any other whitelisted method — no swallowing.
		data = execute_call_spec(call_spec)

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
