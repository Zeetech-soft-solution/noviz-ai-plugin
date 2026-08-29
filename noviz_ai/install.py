import frappe
import requests

# The bundled brand mark (dark rounded square, teal "N"). Same asset the
# /apps launcher tile and app-switcher use (hooks.py app_logo_url).
NOVIZ_LOGO = "/assets/noviz_ai/images/icon-master.svg"


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

	# 3. Point the "ERP Assistant" Desktop Icon at the real brand SVG.
	#    Without a logo_url the desk sidebar header falls back to a plain
	#    lettered tile ("E") — sidebar_header.js only uses the mark when
	#    the Desktop Icon carries a logo_url.
	try:
		for _stale in ("Noviz AI",):
			for _di in frappe.get_all("Desktop Icon", filters={"label": _stale}, pluck="name"):
				frappe.delete_doc("Desktop Icon", _di, force=True, ignore_permissions=True)
		for _di in frappe.get_all("Desktop Icon", filters={"label": "ERP Assistant"}, pluck="name"):
			frappe.db.set_value("Desktop Icon", _di, "logo_url", NOVIZ_LOGO)
	except Exception:
		frappe.log_error(title="Noviz AI: could not set the ERP Assistant desktop-icon logo")

	try:
		frappe.cache.delete_key("desktop_icons")
		frappe.clear_cache()
	except Exception:
		pass


# The sidebar rows we want, keyed by (link_type, link_to). Frappe's own
# auto_generate_icons_and_sidebar() creates the first three with a null
# icon (so they fall back to a generic list glyph) and labels the
# workspace row "Home" — this pass fixes the label + icon on whatever it
# made and appends anything missing. Order matches this list.
_SIDEBAR_ROWS = [
	{"link_type": "Workspace", "link_to": "ERP Assistant", "label": "ERP Assistant", "icon": "bot"},
	{"link_type": "Page", "link_to": "noviz-ai-chat", "label": "Noviz AI Chat", "icon": "message"},
	{"link_type": "DocType", "link_to": "Noviz AI Settings", "label": "Noviz AI Settings", "icon": "settings"},
	{"link_type": "URL", "link_to": None, "url": "mailto:support@noviz.in", "label": "Support", "icon": "help"},
]


def _add_sidebar_links():
	if not frappe.db.exists("Workspace Sidebar", "ERP Assistant"):
		return
	sidebar = frappe.get_doc("Workspace Sidebar", "ERP Assistant")
	changed = False

	# Drop a stray "Email" row an earlier build shipped, and de-dupe rows
	# that point at the same target (auto_generate can re-add the
	# workspace "Home" row on a later migrate).
	seen = set()
	kept = []
	for i in sidebar.items:
		if i.label == "Email":
			continue
		key = (i.link_type, i.link_to or i.url or i.label)
		if key in seen:
			continue
		seen.add(key)
		kept.append(i)
	if len(kept) != len(sidebar.items):
		sidebar.items = kept
		changed = True

	for want in _SIDEBAR_ROWS:
		match = None
		for item in sidebar.items:
			same_link = item.link_type == want["link_type"] and (
				want["link_type"] == "URL" or item.link_to == want["link_to"]
			)
			if same_link or item.label == want["label"]:
				match = item
				break
		if match:
			if match.label != want["label"] or match.icon != want["icon"]:
				match.label = want["label"]
				match.icon = want["icon"]
				changed = True
		else:
			row = {
				"type": "Link",
				"label": want["label"],
				"link_type": want["link_type"],
				"link_to": want["link_to"],
				"icon": want["icon"],
				"indent": 0,
				"collapsible": 1,
				"keep_closed": 0,
				"show_arrow": 0,
				"child": 0,
			}
			if want.get("url"):
				row["url"] = want["url"]
			sidebar.append("items", row)
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
