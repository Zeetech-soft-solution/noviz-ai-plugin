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


def _post(url, json_body, headers):
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
	"""
	try:
		response = requests.post(url, json=json_body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
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


@frappe.whitelist()
def send_message(prompt: str, previous_turn_id: str = None):
	"""The one real entry point real users hit from the chat page. Drives
	the full fetch/continue loop itself — the browser only ever sees the
	final {"status": "final", "reply": "...", "turnId": "..."} once this
	returns, never the intermediate relay round trips.

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

	result = _post(
		f"{base_url}/v1/agent/turn",
		{
			"prompt": prompt,
			"previous_turn_id": previous_turn_id,
			# The real logged-in person's own identity/roles — never a
			# credential. The central relay's own role-gating logic
			# (Phase 4, not yet built) will use this; today it's carried
			# through but not yet enforced beyond what the fixed V1 tool
			# set already allows for every tenant. Real ERPNext DATA
			# access is governed entirely by dispatcher.py using frappe's
			# own already-authenticated session for whoever is actually
			# logged in — this field never widens or narrows that.
			"frappe_user": frappe.session.user,
			"frappe_roles": frappe.get_roles(frappe.session.user),
		},
		headers,
	)

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

		result = _post(f"{base_url}/v1/agent/turn/continue", {"turnId": result["turnId"], "result": data}, headers)

	return result
