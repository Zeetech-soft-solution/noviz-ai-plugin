# Runs once, automatically, whenever this app is installed on a site
# (hooks.py's after_install) — a real customer installing this plugin
# should never need to manually patch permissions by hand the way this
# was first found and fixed while building it.
import frappe


def after_install():
	_create_agent_role()
	_grant_page_doctype_permission()


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


def _grant_page_doctype_permission():
	# Real bug found live: ERPNext's standard Page DocPerm only grants
	# read to System Manager/Administrator, by default, on every real
	# install we tested against. The Noviz AI workspace's shortcut is
	# type "Page" - opening the workspace (not just the chat page
	# itself, which has its own separate Page.is_permitted() role check)
	# resolves against this doctype-level permission too, so without
	# this grant a real Sales/Purchase/etc. user sees "Not permitted...
	# no doctype access... for document Page" the moment they open the
	# workspace, even though they genuinely have the Noviz AI Agent role.
	# This grants READ only - it does not let this role see/open any
	# OTHER Page's content beyond what that Page's own role list
	# (Page.roles) separately allows, same real permission boundary the
	# chat page itself is gated by.
	if frappe.db.exists("Custom DocPerm", {"parent": "Page", "role": "Noviz AI Agent"}):
		return
	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": "Page",
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": "Noviz AI Agent",
			"read": 1,
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(doctype="Page")
