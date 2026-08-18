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


@frappe.whitelist()
def send_message(prompt: str):
	"""The one real entry point real users hit from the chat page. Drives
	the full fetch/continue loop itself — the browser only ever sees the
	final {"status": "final", "reply": "..."} once this returns, never
	the intermediate relay round trips."""
	if not prompt or not prompt.strip():
		frappe.throw("prompt is required")

	settings = _settings()
	base_url = settings.relay_base_url.rstrip("/")
	headers = _relay_headers(settings)

	response = requests.post(
		f"{base_url}/v1/agent/turn",
		json={
			"prompt": prompt,
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
		headers=headers,
		timeout=REQUEST_TIMEOUT_SECONDS,
	)
	response.raise_for_status()
	result = response.json()

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

		response = requests.post(
			f"{base_url}/v1/agent/turn/continue",
			json={"turnId": result["turnId"], "result": data},
			headers=headers,
			timeout=REQUEST_TIMEOUT_SECONDS,
		)
		response.raise_for_status()
		result = response.json()

	return result
