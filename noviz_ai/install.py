import frappe
import requests


def after_install():
	_create_agent_role()
	_grant_page_doctype_permission()
	_grant_settings_doctype_permission()
	_grant_agent_role_to_system_managers()
	_add_desktop_icon()
	_add_sidebar_links()
	_set_default_relay_url()
	_seed_module_policy_rows()
	_report_install_to_platform()


def after_migrate():
	"""Runs on every `bench migrate` — the reliable trigger on managed
	hosts (Frappe Cloud installs/updates go through migrate). Re-does the
	desk-visibility setup so a site where the "Noviz AI" icon never showed
	after install self-heals. Every step is idempotent."""
	_create_agent_role()
	_grant_page_doctype_permission()
	_grant_settings_doctype_permission()
	_grant_agent_role_to_system_managers()
	_add_desktop_icon()
	_add_sidebar_links()


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


def _grant_settings_doctype_permission():
	if frappe.db.exists("Custom DocPerm", {"parent": "Noviz AI Settings", "role": "Noviz AI Agent"}):
		return
	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": "Noviz AI Settings",
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": "Noviz AI Agent",
			"read": 1,
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(doctype="Noviz AI Settings")


def _grant_agent_role_to_system_managers():
	"""Give every existing System Manager the "Noviz AI Agent" role on
	install/migrate, so whoever set the site up can use the chat straight
	away instead of assigning the role to themselves first. Idempotent —
	skips users who already have it, and Administrator/Guest."""
	try:
		users = frappe.get_all(
			"Has Role",
			filters={"role": "System Manager", "parenttype": "User"},
			pluck="parent",
		)
	except Exception:
		return
	for user in set(users):
		if user in ("Administrator", "Guest"):
			continue
		if frappe.db.exists("Has Role", {"parent": user, "role": "Noviz AI Agent", "parenttype": "User"}):
			continue
		try:
			doc = frappe.get_doc("User", user)
			doc.append("roles", {"role": "Noviz AI Agent"})
			doc.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"Noviz AI: could not grant agent role to {user}")


def _add_desktop_icon():
	# 1. Make sure the "ERP Assistant" Workspace doc is in the DB.
	#    On a managed host the workspace JSON sometimes doesn't get synced
	#    on install; without the Workspace record NOTHING shows on the
	#    desk, not even for Administrator. Reloading it from the app's own
	#    fixture is idempotent and cheap.
	#    The workspace used to be called "Noviz AI" — same name as the app
	#    title — which made the desk sidebar header print "Noviz AI" twice
	#    (workspace name on top, app title beneath). Renamed to
	#    "ERP Assistant"; drop the old record on upgrade.
	try:
		for _stale in ("Noviz AI",):
			if frappe.db.exists("Workspace", _stale):
				frappe.delete_doc("Workspace", _stale, force=True, ignore_permissions=True)
			if frappe.db.exists("Workspace Sidebar", _stale):
				frappe.delete_doc("Workspace Sidebar", _stale, force=True, ignore_permissions=True)
		frappe.reload_doc("noviz_ai", "workspace", "erp_assistant", force=True)
	except Exception:
		frappe.log_error(title="Noviz AI: could not sync the ERP Assistant workspace")

	# 2. Generate the app's sidebar icon + "Workspace Sidebar" record.
	#    The helper's name/signature has moved around across Frappe
	#    versions — try what we know, never let a failure here abort the
	#    whole install/migrate.
	try:
		from frappe.utils.install import auto_generate_icons_and_sidebar

		try:
			auto_generate_icons_and_sidebar(app_name="noviz_ai")
		except TypeError:
			auto_generate_icons_and_sidebar("noviz_ai")
	except Exception:
		frappe.log_error(title="Noviz AI: auto_generate_icons_and_sidebar unavailable/failed on this Frappe version")

	try:
		frappe.cache.delete_key("desktop_icons")
		frappe.clear_cache()
	except Exception:
		pass


def _add_sidebar_links():
	if not frappe.db.exists("Workspace Sidebar", "ERP Assistant"):
		return
	sidebar = frappe.get_doc("Workspace Sidebar", "ERP Assistant")
	existing_labels = {item.label for item in sidebar.items}
	changed = False

	if "Noviz AI Chat" not in existing_labels:
		sidebar.append(
			"items",
			{
				"type": "Link",
				"label": "Noviz AI Chat",
				"link_type": "Page",
				"link_to": "noviz-ai-chat",
				"icon": "message",
				"indent": 0,
				"collapsible": 1,
				"keep_closed": 0,
				"show_arrow": 0,
				"child": 0,
			},
		)
		changed = True

	if "Noviz AI Settings" not in existing_labels:
		sidebar.append(
			"items",
			{
				"type": "Link",
				"label": "Noviz AI Settings",
				"link_type": "DocType",
				"link_to": "Noviz AI Settings",
				"icon": "settings",
				"indent": 0,
				"collapsible": 1,
				"keep_closed": 0,
				"show_arrow": 0,
				"child": 0,
			},
		)
		changed = True

	if "Email" in existing_labels:
		sidebar.items = [item for item in sidebar.items if item.label != "Email"]
		changed = True

	if "Support" not in existing_labels:
		sidebar.append(
			"items",
			{
				"type": "Link",
				"label": "Support",
				"link_type": "URL",
				"url": "mailto:support@noviz.in",
				"icon": "help",
				"indent": 0,
				"collapsible": 1,
				"keep_closed": 0,
				"show_arrow": 0,
				"child": 0,
			},
		)
		changed = True

	if changed:
		sidebar.save(ignore_permissions=True)
		frappe.clear_cache()


def _set_default_relay_url():
	settings = frappe.get_single("Noviz AI Settings")
	if settings.relay_base_url:
		return
	settings.relay_base_url = "https://noviz.in/platform-api"
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)


def _seed_module_policy_rows():
	settings = frappe.get_single("Noviz AI Settings")
	if settings.module_policies:
		return
	for module in ["Common (applies to every module)",
			"Selling", "Buying", "Accounting", "HR / HRMS", "Stock / Inventory",
			"Manufacturing", "Projects", "Quality", "Support", "Assets", "CRM",
			"Utilities (calculator, charts, email, notifications)"]:
		settings.append("module_policies", {"module": module, "strict_policy": "", "warning_policy": ""})
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)


def _report_install_to_platform():
	try:
		company_name = frappe.db.get_default("company") or frappe.db.get_value("Company", {}, "name")
		company = frappe.get_doc("Company", company_name) if company_name else None
		requests.post(
			"https://noviz.in/platform-api/install-lead",
			json={
				"siteUrl": frappe.utils.get_url(),
				"companyName": company.company_name if company else None,
				"phone": company.phone_no if company else None,
				"email": company.email if company else None,
				"country": company.country if company else None,
			},
			timeout=10,
		)
	except Exception:
		frappe.log_error(title="Noviz AI install-lead report failed (non-blocking)")
