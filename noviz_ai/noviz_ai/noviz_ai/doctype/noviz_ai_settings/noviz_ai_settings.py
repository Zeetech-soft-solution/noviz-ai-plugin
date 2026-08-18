# Copyright (c) 2026, Zeetech Soft Solution and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class NovizAISettings(Document):
	def on_update(self):
		# Real, explicit product ask: a tenant's own Company Policy
		# (module_policies child table) must reach the relay so it can
		# actually be used at chat time — this is the one-way sync point.
		# See api.py's sync_module_policies() for the full "why" this
		# doesn't happen on every chat turn instead.
		from noviz_ai.api import sync_module_policies

		sync_module_policies(self)
