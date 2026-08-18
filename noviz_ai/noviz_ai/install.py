# Runs once, automatically, whenever this app is installed on a site
# (hooks.py's after_install) — a real customer installing this plugin
# should never need to manually create the scoped role the way this was
# first set up by hand while building it.
import frappe


def after_install():
	_create_agent_role()


def _create_agent_role():
	if frappe.db.exists("Role", "Noviz AI Agent"):
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": "Noviz AI Agent",
			"desk_access": 1,
			"description": (
				"Grants access to the Noviz AI chat page. Does NOT grant any ERPNext document "
				"permission by itself - data access is governed entirely by whatever OTHER roles "
				"this same user already has (real per-user permissions apply exactly as if they "
				"used ERPNext's own UI directly)."
			),
		}
	).insert(ignore_permissions=True)
