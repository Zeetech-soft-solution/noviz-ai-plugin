import frappe
import requests


def after_setup():
	_create_agent_role()
	_grant_page_doctype_permission()
	_grant_settings_doctype_permission()
	_add_desktop_icon()
	_add_sidebar_links()
	_set_default_relay_url()
	_seed_module_policy_rows()
	_report_setup_to_platform()


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


def _add_desktop_icon():
	try:
		from frappe.utils.install import auto_generate_icons_and_sidebar
	except ImportError:
		frappe.log_error(title="Noviz AI: auto_generate_icons_and_sidebar not available on this Frappe version")
		return

	auto_generate_icons_and_sidebar(app_name="noviz_ai")
	frappe.cache.delete_key("desktop_icons")


def _add_sidebar_links():
	if not frappe.db.exists("Workspace Sidebar", "Noviz AI"):
		return
	sidebar = frappe.get_doc("Workspace Sidebar", "Noviz AI")
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
				"icon": "chat",
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


def _report_setup_to_platform():
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
