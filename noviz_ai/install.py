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
	_ensure_noviz_workspace()
	_set_default_relay_url()
	_seed_module_policy_rows()
	_report_install_to_platform()


def after_migrate():
	"""Runs on every `bench migrate` — the reliable trigger on managed
	hosts (Frappe Cloud installs/updates go through migrate). Re-asserts
	the role/permission grants and re-syncs the single "Noviz AI"
	workspace (pruning the legacy "ERP Assistant" artefacts) so an
	upgraded site self-heals. Every step is idempotent."""
	_create_agent_role()
	_grant_page_doctype_permission()
	_grant_settings_doctype_permission()
	_grant_agent_role_to_system_managers()
	_ensure_noviz_workspace()


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


# The ONE desk entry: a single public "Noviz AI" Workspace (synced from
# workspace/noviz_ai) that shows in the desk workspace grid / left nav.
# Its landing page is just a header + one big "Open Noviz AI Chat"
# shortcut. There is deliberately NO /apps launcher tile (hooks.py's
# add_to_apps_screen is disabled) — the workspace IS the single entry
# point, so nothing doubles up ("two icons after install").
_CHAT_PAGE = "noviz-ai-chat"
# Everything an OLDER build of this app created that must be removed on
# upgrade so only the one "Noviz AI" workspace remains.
_LEGACY_LABELS = ("ERP Assistant",)


def _ensure_noviz_workspace():
	"""Sync the single 'Noviz AI' workspace from its fixture and tear down
	every legacy desk artefact ('ERP Assistant' workspace + Workspace
	Sidebar + Desktop Icon, and any stale per-user private copies of the
	Noviz workspaces). Idempotent — safe on install AND every migrate."""
	# 1. drop the legacy 'ERP Assistant' records + any PRIVATE per-user
	#    copies of either name (Frappe clones a public workspace per user
	#    the first time they personalise the desk; a stale clone keeps the
	#    old content and shows as a duplicate).
	try:
		for w in frappe.get_all(
			"Workspace",
			filters=[["label", "in", (*_LEGACY_LABELS, "Noviz AI")]],
			fields=["name", "label", "for_user", "public"],
		):
			is_keeper = w["label"] == "Noviz AI" and w["public"] and not w["for_user"]
			if is_keeper:
				continue
			try:
				frappe.delete_doc("Workspace", w["name"], force=True, ignore_permissions=True, delete_permanently=True)
			except Exception:
				frappe.log_error(title=f"Noviz AI: could not drop Workspace '{w['name']}'")
	except Exception:
		frappe.log_error(title="Noviz AI: could not enumerate legacy workspaces")

	for label in _LEGACY_LABELS:
		if frappe.db.exists("Workspace Sidebar", label):
			try:
				frappe.delete_doc("Workspace Sidebar", label, force=True, ignore_permissions=True)
			except Exception:
				pass
	for label in (*_LEGACY_LABELS, "Noviz AI"):
		for di in frappe.get_all("Desktop Icon", filters={"label": label}, pluck="name"):
			try:
				frappe.delete_doc("Desktop Icon", di, force=True, ignore_permissions=True)
			except Exception:
				pass

	# 2. (re)sync the 'Noviz AI' workspace from the app's own fixture —
	#    on a managed host the JSON sometimes doesn't sync on install.
	try:
		frappe.reload_doc("noviz_ai", "workspace", "noviz_ai", force=True)
	except Exception:
		frappe.log_error(title="Noviz AI: could not sync the Noviz AI workspace")

	# 3. give the workspace a real left-nav sub-sidebar (Chat + Settings).
	try:
		from frappe.utils.install import auto_generate_icons_and_sidebar

		try:
			auto_generate_icons_and_sidebar(app_name="noviz_ai")
		except TypeError:
			auto_generate_icons_and_sidebar("noviz_ai")
	except Exception:
		pass
	_sync_sidebar_links()

	try:
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")
		frappe.clear_cache()
	except Exception:
		pass


# The left-nav rows under the "Noviz AI" workspace — just the two real
# destinations. auto_generate_icons_and_sidebar seeds a bare workspace
# row with a null icon; this fixes the labels/icons and appends the rest.
_SIDEBAR_ROWS = [
	{"link_type": "Page", "link_to": _CHAT_PAGE, "label": "Noviz AI Chat", "icon": "message"},
	{"link_type": "DocType", "link_to": "Noviz AI Settings", "label": "Noviz AI Settings", "icon": "settings"},
]


def _sync_sidebar_links():
	if not frappe.db.exists("Workspace Sidebar", "Noviz AI"):
		return
	sidebar = frappe.get_doc("Workspace Sidebar", "Noviz AI")
	changed = False

	seen = set()
	kept = []
	for i in sidebar.items:
		key = (i.link_type, i.link_to or i.url or i.label)
		if key in seen:
			continue
		seen.add(key)
		kept.append(i)
	if len(kept) != len(sidebar.items):
		sidebar.items = kept
		changed = True

	for want in _SIDEBAR_ROWS:
		match = next(
			(it for it in sidebar.items
			 if (it.link_type == want["link_type"] and it.link_to == want["link_to"]) or it.label == want["label"]),
			None,
		)
		if match:
			if match.label != want["label"] or match.icon != want["icon"]:
				match.label, match.icon = want["label"], want["icon"]
				changed = True
		else:
			sidebar.append("items", {
				"type": "Link", "label": want["label"], "link_type": want["link_type"],
				"link_to": want["link_to"], "icon": want["icon"],
				"indent": 0, "collapsible": 1, "keep_closed": 0, "show_arrow": 0, "child": 0,
			})
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
