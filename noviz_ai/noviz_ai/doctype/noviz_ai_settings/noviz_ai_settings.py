# Copyright (c) 2026, Zeetech Soft Solution and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class NovizAISettings(Document):
	def validate(self):
		# Noviz AI Users: the list goes to the relay before it is saved here, so
		# a list the relay refuses (more users than the subscription allows)
		# is never saved. See chat_users.py.
		from noviz_ai.chat_users import send_chat_users

		send_chat_users(self)

	def on_update(self):
		# Each listed user gets the Noviz AI Agent role; one taken off the list
		# loses it.
		from noviz_ai.chat_users import apply_chat_user_roles

		apply_chat_user_roles(self)

		# A tenant's own Company Policy (module_policies child table) must
		# reach the relay so it can actually be used at chat time — this
		# is the one-way sync point. See api.py's sync_module_policies()
		# for why this happens here rather than on every chat turn.
		from noviz_ai.api import sync_module_policies

		sync_module_policies(self)
