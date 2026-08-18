app_name = "noviz_ai"
app_title = "Noviz AI"
app_publisher = "Zeetech Soft Solution"
app_description = "Thin client plugin for Noviz AI - talks only to the Noviz relay API, no business logic"
app_email = "tajdink@gmail.com"
app_license = "mit"

# Real destination for the app's own top-level Desktop Icon tile — see
# add_to_apps_screen below. Matches Frappe's own /desk/<page-name> route
# convention (the exact same one hrms's own hooks.py "app_home" uses for
# its "Frappe HR" tile).
app_home = "/desk/noviz-ai-chat"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
#
# Real gap found live 2026-08-18: without this, the plugin's home-screen
# tile could only ever go through an intermediate Workspace landing page
# (Desktop Icon -> Workspace Sidebar -> workspace's own "Noviz AI Chat"
# shortcut card) — an extra click for a genuinely single-feature app.
# This is the SAME real mechanism hrms uses for its own "Frappe HR" tile
# (icon_type "App", link_type "External") to land directly on its own
# home route with zero intermediate hop — ported here, not guessed.
# frappe.utils.install.create_desktop_icons_from_installed_apps() reads
# this hook and creates the real Desktop Icon record automatically
# (frappe's own after_app_install hook calls it on every fresh install —
# see frappe/hooks.py's own "after_app_install"), and its own dedup
# logic (create_desktop_icons_from_workspace()) automatically hides the
# redundant Workspace-based tile once this one exists, since our single
# Workspace happens to share its exact name with app_title ("Noviz AI").
# No "logo" key: real, live-confirmed infra issue found on this deploy
# — the frontend (nginx) container only has frappe/erpnext baked into
# its own image; hrms and noviz_ai were installed live into the
# backend container only, so ANY /assets/noviz_ai/... (or /assets/
# hrms/...) file path 404s from nginx's side, confirmed even for
# HRMS's own official logo (pre-existing, unrelated to this app).
# Omitting "logo" isn't a workaround-hack — it's Frappe's own real,
# intended fallback path (desktop_icon.html's final {% else %} branch
# -> frappe.utils.desktop_icon()), the SAME colored-initial-letter
# avatar already used for the Workspace's own sidebar entry — clean on
# any deployment, not dependent on this one server's asset-serving
# quirk being fixed.
add_to_apps_screen = [
	{
		"name": "noviz_ai",
		"title": "Noviz AI",
		"route": app_home,
		"has_permission": "noviz_ai.utils.check_app_permission",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/noviz_ai/css/noviz_ai.css"
# app_include_js = "/assets/noviz_ai/js/noviz_ai.js"

# include js, css files in header of web template
# web_include_css = "/assets/noviz_ai/css/noviz_ai.css"
# web_include_js = "/assets/noviz_ai/js/noviz_ai.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "noviz_ai/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "noviz_ai/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "noviz_ai.utils.jinja_methods",
# 	"filters": "noviz_ai.utils.jinja_filters"
# }

# Installation
# ------------

after_install = "noviz_ai.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "noviz_ai.uninstall.before_uninstall"
# after_uninstall = "noviz_ai.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "noviz_ai.utils.before_app_install"
# after_app_install = "noviz_ai.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "noviz_ai.utils.before_app_uninstall"
# after_app_uninstall = "noviz_ai.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "noviz_ai.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "noviz_ai.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"noviz_ai.tasks.all"
# 	],
# 	"daily": [
# 		"noviz_ai.tasks.daily"
# 	],
# 	"hourly": [
# 		"noviz_ai.tasks.hourly"
# 	],
# 	"weekly": [
# 		"noviz_ai.tasks.weekly"
# 	],
# 	"monthly": [
# 		"noviz_ai.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "noviz_ai.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "noviz_ai.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "noviz_ai.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "noviz_ai.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["noviz_ai.utils.before_request"]
# after_request = ["noviz_ai.utils.after_request"]

# Job Events
# ----------
# before_job = ["noviz_ai.utils.before_job"]
# after_job = ["noviz_ai.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"noviz_ai.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

