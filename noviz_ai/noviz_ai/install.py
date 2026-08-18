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
