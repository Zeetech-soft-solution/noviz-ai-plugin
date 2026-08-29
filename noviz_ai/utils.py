# Small, standalone module for real cross-cutting checks that don't
# belong in api.py (the relay-facing whitelisted entry point) or the
# one-time app-setup hook module — currently just the app-tile permission
# gate. Kept separate so hooks.py's own "has_permission" reference stays
# readable and doesn't pull in requests/dispatcher imports it never uses.
import frappe


def check_app_permission():
	"""The "Noviz AI" tile on the /apps launcher (hooks.py's
	add_to_apps_screen). Shown to every desk user so the app is
	discoverable — "Noviz AI exists, ask your admin for access". Actual
	access is still gated: the chat Workspace/Page need the "Noviz AI
	Agent" role (assigned per user), and "Noviz AI Settings" needs
	System Manager."""
	return bool(frappe.session.user and frappe.session.user != "Guest")
