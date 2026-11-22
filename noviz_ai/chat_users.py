# Noviz AI Users: which ERPNext users may use Noviz AI. The administrator keeps
# the list in Noviz AI Settings (child table "Noviz AI User"); on save it goes
# to the relay (POST /v1/agent/users), which from then on refuses a question
# from anyone not on it, and each listed user gets the "Noviz AI Agent" role
# that opens the chat page. What a user may read or change is still decided by
# their own ERPNext roles and permissions; the list only says who may ask.
#
# The relay also checks the list against the users the subscription allows: a
# longer list is refused there, and the save fails with its message.
import frappe
import requests

AGENT_ROLE = "Noviz AI Agent"
# Users ERPNext gives every role already, or that cannot sign in.
_BUILT_IN_USERS = ("Administrator", "Guest")
REQUEST_TIMEOUT_SECONDS = 30


def listed_users(settings):
	"""The users on the settings' list, each once, in the order shown."""
	users = []
	for row in (settings.get("chat_users") or []) if settings else []:
		if row.user and row.user not in users:
			users.append(row.user)
	return users


def _users_before_save(settings):
	before = settings.get_doc_before_save() if settings else None
	return listed_users(before) if before else []


def send_chat_users(settings):
	"""Settings validate: sends the list to the relay when it changed. A refusal
	(more users than the subscription allows, a key that is not valid) stops
	the save with the relay's own message, so nothing is saved that the relay
	did not accept. A save that does not touch the list sends nothing, so a
	site that never keeps a list goes on as before."""
	users = listed_users(settings)
	if users == _users_before_save(settings):
		return
	api_key = settings.get_password("api_key", raise_exception=False)
	if not settings.relay_base_url or not api_key:
		frappe.throw("Save the AI Relay Token API Key first, then add the Noviz AI users.")
	try:
		response = requests.post(
			f"{settings.relay_base_url.rstrip('/')}/v1/agent/users",
			json={"users": users, "admin_user": frappe.session.user},
			headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
			timeout=REQUEST_TIMEOUT_SECONDS,
		)
	except requests.exceptions.RequestException as e:
		frappe.throw(f"The Noviz AI users could not be saved: Noviz AI could not be reached ({e}). Try again shortly.")
	if response.status_code == 401:
		frappe.throw("The Noviz AI users could not be saved: Noviz AI did not accept the AI Relay Token API Key.")
	if not response.ok:
		try:
			message = response.json().get("error")
		except ValueError:
			message = None
		frappe.throw(message or f"The Noviz AI users could not be saved (Noviz AI answered {response.status_code}).")


def apply_chat_user_roles(settings):
	"""Settings on_update: each listed user gets the Noviz AI Agent role; a user
	taken off the list loses it. Users who were never on the list keep the
	roles they have."""
	users = listed_users(settings)
	before = _users_before_save(settings)
	for user in users:
		if user not in _BUILT_IN_USERS and AGENT_ROLE not in frappe.get_roles(user):
			frappe.get_doc("User", user).add_roles(AGENT_ROLE)
	for user in before:
		if user not in users and user not in _BUILT_IN_USERS and AGENT_ROLE in frappe.get_roles(user):
			frappe.get_doc("User", user).remove_roles(AGENT_ROLE)


def has_chat_user_list():
	"""Whether this site keeps a Noviz AI Users list: the Noviz AI Agent role then follows the list."""
	return bool(frappe.db.exists("Noviz AI User", {"parent": "Noviz AI Settings"}))
