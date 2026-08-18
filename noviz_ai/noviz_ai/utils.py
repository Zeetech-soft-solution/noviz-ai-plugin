# Small, standalone module for real cross-cutting checks that don't
# belong in api.py (the relay-facing whitelisted entry point) or
# install.py (one-time setup) — currently just the app-tile permission
# gate. Kept separate so hooks.py's own "has_permission" reference stays
# readable and doesn't pull in requests/dispatcher imports it never uses.
import frappe


def check_app_permission():
	"""Gates the "Noviz AI" home-screen app tile (hooks.py's own
	add_to_apps_screen) — the SAME real pattern hrms.hr.utils.
	check_app_permission uses for its own "Frappe HR" tile. Administrator
	always sees it; everyone else needs the real "Noviz AI Agent" role —
	the SAME role that already gates the chat page itself (Page.roles),
	so this tile never shows for someone who couldn't actually use the
	chat page it links to anyway."""
	if frappe.session.user == "Administrator":
		return True
	return "Noviz AI Agent" in frappe.get_roles(frappe.session.user)
