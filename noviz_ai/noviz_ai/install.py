# Runs once, automatically, whenever this app is installed on a site
# (hooks.py's after_install) — a real customer installing this plugin
# should never need to manually patch permissions by hand the way this
# was first found and fixed while building it.
import frappe


def after_install():
	_create_agent_role()
	_grant_page_doctype_permission()
	_grant_settings_doctype_permission()
	_add_desktop_icon()
	_add_sidebar_links()
	_seed_module_policy_rows()


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


def _grant_settings_doctype_permission():
	# Real bug found live: Frappe's own module-visibility check
	# (desk/desktop.py's Workspace.__init__ -> User.build_permissions)
	# only adds a module to a user's "allow_modules" list if they can
	# read AT LEAST ONE doctype belonging to that module - it is NOT
	# driven by the Workspace's own `roles` child table at all (that
	# only gates the workspace's CONTENT once you're already inside it).
	# The "Noviz AI Agent" role was deliberately built with ZERO doctype
	# permissions of its own (see _create_agent_role's own doc comment -
	# real data access must come from the user's own real functional
	# roles, never this marker role). Without this grant, that correct
	# design choice has a real side effect: the "Noviz AI" module never
	# enters allow_modules, Workspace.__init__ raises PermissionError,
	# get_workspaces() silently swallows it (`except PermissionError:
	# pass`), and the whole workspace - sidebar entry AND desktop icon -
	# invisibly vanishes for every real non-System-Manager user, with no
	# error shown anywhere. Confirmed live: present in the DB, permitted
	# by is_permitted()'s own role check, still never appeared for a real
	# Sales User until this grant was added.
	#
	# Granting READ on "Noviz AI Settings" (a Single) is safe to give
	# this broad, low-privilege role: its one sensitive field (api_key)
	# is a Password field, which Frappe masks on every ordinary read
	# regardless of doctype-level permission - only get_password() (a
	# separate, System-Manager/owner-gated call this role never makes)
	# ever returns the real value.
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
	# Real gap found live, same investigation as _grant_settings_doctype_
	# permission above: even with the module now visible, a genuinely
	# NEW Workspace never gets a home-screen tile on its own — that grid
	# (desk/page/desktop, the same one showing Selling/Accounting/etc.)
	# is driven by real "Desktop Icon" + "Workspace Sidebar" DocType
	# records, which every core module gets from its own shipped fixture
	# files, generated once at that module's own creation time. A
	# Workspace created after the fact (ours) has no such fixture.
	#
	# frappe.utils.install.auto_generate_icons_and_sidebar() is the EXACT
	# real function frappe's own "after_app_install" hook calls for every
	# single app on every fresh install (frappe/hooks.py's own
	# after_app_install) — not a hand-rolled equivalent. It builds BOTH
	# the real Workspace Sidebar for our "Noviz AI" workspace AND every
	# Desktop Icon this app's hooks.py declares — including the
	# add_to_apps_screen-driven "App"-type tile (see hooks.py's own doc
	# comment) that goes straight to the chat page, one click, matching
	# hrms's own "Frappe HR" tile design. Its own dedup logic
	# automatically hides the redundant Workspace-based tile once the App
	# one exists, since our one Workspace shares its name with app_title.
	# Idempotent — safe to call again on a reinstall/migrate.
	from frappe.utils.install import auto_generate_icons_and_sidebar

	auto_generate_icons_and_sidebar(app_name="noviz_ai")

	# Per-user desktop-icon caching (get_desktop_icons()) would otherwise
	# keep showing a stale (missing) grid until each user's own cache
	# naturally expires - clear it site-wide so this takes effect
	# immediately for every existing user, not just new logins.
	frappe.cache.delete_key("desktop_icons")


def _add_sidebar_links():
	# Real gap found live: the auto-generated Workspace Sidebar
	# (auto_generate_icons_and_sidebar above) creates exactly ONE item -
	# a bare "Noviz AI" link back to the workspace itself, nothing else.
	# Confirmed live against a REAL module's own sidebar (Selling's own
	# workspace_sidebar/selling.json, checked directly): a real module
	# gives its sidebar actual navigation - Home, then real links to the
	# doctypes/pages/settings that module actually has, not just a
	# single self-referencing entry. Left as the bare auto-generated
	# version, the whole left sidebar for this app was functionally
	# empty - no way to find "Noviz AI Settings" at all except already
	# knowing the exact URL, "how do we even know where settings is"
	# being the real, live question this answers. Adds the SAME two
	# real destinations already on the workspace's own body (the "Noviz
	# AI Chat"/"Noviz AI Settings" shortcut cards) as real sidebar
	# links too - matching how Selling's own sidebar ALSO duplicates
	# what's on its workspace body, not a new pattern invented here.
	# Idempotent - checks each item's own label before appending.
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

	# Real "Email" destination — NOT a Noviz AI feature of our own,
	# points straight at Frappe's own real, standard "Email Account"
	# doctype (confirmed live it exists; a real "Email" Workspace does
	# NOT exist on this site despite one real Desktop Icon record
	# referencing it — a dangling reference, same class of gap as the
	# "Frappe HR" tile investigated earlier this session, not something
	# to chase further here). Setting up a real inbox (POP3/SMTP)
	# happens on Frappe's own genuine "Email Account" form once someone
	# navigates here — this plugin (and this assistant) never touches
	# or stores that credential itself; entering it is a real, separate,
	# manual step the site's own admin does directly in ERPNext's own UI.
	if "Email" not in existing_labels:
		sidebar.append(
			"items",
			{
				"type": "Link",
				"label": "Email",
				"link_type": "DocType",
				"link_to": "Email Account",
				"icon": "mail",
				"indent": 0,
				"collapsible": 1,
				"keep_closed": 0,
				"show_arrow": 0,
				"child": 0,
			},
		)
		changed = True

	# Real support contact, not built as a business feature of this
	# plugin (deliberately zero business logic here per this repo's own
	# README) - a plain mailto: link, the SAME real support address
	# already used throughout Noviz AI's own account/password flows
	# (platform-admin's own password-reset emails, etc.). "Email" (a
	# real integrated inbox) is explicitly deferred, not built here -
	# the user's own words: "let that set when i give my smtp and
	# relays" - a real SMTP config they'll provide later, not something
	# to guess/stub now.
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


def _seed_module_policy_rows():
	# Real, explicit product ask: "each module we have including hrms" -
	# a real admin opening Settings for the first time should see every
	# real module already listed with two blank boxes to fill in, not an
	# empty child table they'd have to know to add ten rows to
	# themselves one at a time. Idempotent - only seeds when the table
	# is genuinely empty (a site that already has real rows, from a
	# reinstall or an admin who already started filling this in, is
	# never touched).
	settings = frappe.get_single("Noviz AI Settings")
	if settings.module_policies:
		return
	for module in ["Selling", "Buying", "Accounting", "HR / HRMS", "Stock / Inventory",
			"Manufacturing", "Projects", "Quality", "Support", "Assets", "CRM"]:
		settings.append("module_policies", {"module": module, "strict_policy": "", "warning_policy": ""})
	settings.save(ignore_permissions=True)
