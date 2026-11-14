# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for the chat's company selection (noviz_ai.api.companies and the
company sent with every request).

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_company_selection`.

The user works in one company at a time: the one selected in the chat when
ERPNext lets the user see it, else the user's default company. The relay makes
every call of the question for that company.
"""
import unittest
from unittest import mock

from noviz_ai import api


def _site(allowed, user_default=None, global_default=None, denied=False):
	"""Patches for a site: the companies ERPNext returns for the user, and the defaults."""
	get_list = mock.Mock(side_effect=api.frappe.PermissionError) if denied else mock.Mock(return_value=list(allowed))
	return [
		mock.patch.object(api.frappe, "get_list", get_list),
		mock.patch.object(api.frappe.defaults, "get_user_default", return_value=user_default),
		mock.patch.object(api.frappe.defaults, "get_global_default", return_value=global_default),
	]


class TestCompanySelection(unittest.TestCase):
	def _with(self, patches, fn):
		for p in patches:
			p.start()
		try:
			return fn()
		finally:
			for p in patches:
				p.stop()

	def test_lists_the_companies_erpnext_lets_the_user_see(self):
		patches = _site(["Alpha Ltd", "Beta Ltd"], user_default="Beta Ltd")
		result = self._with(patches, api.companies)
		self.assertEqual(result, {"companies": ["Alpha Ltd", "Beta Ltd"], "selected": "Beta Ltd"})
		# ERPNext's own permission-checked list, by name.
		get_list = patches[0].new
		self.assertEqual(get_list.call_args.args[0], "Company")
		self.assertEqual(get_list.call_args.kwargs.get("pluck"), "name")

	def test_the_selected_company_is_used_when_the_user_may_see_it(self):
		self.assertEqual(self._with(_site(["Alpha Ltd", "Beta Ltd"], user_default="Alpha Ltd"), lambda: api._working_company("Beta Ltd")), "Beta Ltd")

	def test_a_company_the_user_may_not_see_falls_back_to_the_default(self):
		self.assertEqual(self._with(_site(["Alpha Ltd"], user_default="Alpha Ltd"), lambda: api._working_company("Secret Ltd")), "Alpha Ltd")

	def test_no_selection_starts_on_the_users_default_then_the_sites(self):
		self.assertEqual(self._with(_site(["Alpha Ltd", "Beta Ltd"], user_default="Beta Ltd", global_default="Alpha Ltd"), api._working_company), "Beta Ltd")
		self.assertEqual(self._with(_site(["Alpha Ltd", "Beta Ltd"], global_default="Alpha Ltd"), api._working_company), "Alpha Ltd")

	def test_a_default_the_user_may_not_see_gives_the_first_allowed_company(self):
		self.assertEqual(self._with(_site(["Beta Ltd", "Gamma Ltd"], user_default="Alpha Ltd"), api._working_company), "Beta Ltd")

	def test_a_user_who_may_not_read_company_keeps_the_default_as_before(self):
		patches = _site([], global_default="Alpha Ltd", denied=True)
		self.assertEqual(self._with(patches, api.companies), {"companies": [], "selected": "Alpha Ltd"})

	def test_a_question_goes_to_the_relay_with_the_selected_company(self):
		settings = mock.Mock(relay_base_url="https://relay.test/platform-api/")
		post = mock.Mock(return_value={"status": "final", "reply": "ok"})
		patches = _site(["Alpha Ltd", "Beta Ltd"], user_default="Alpha Ltd") + [
			mock.patch.object(api, "_settings", return_value=settings),
			mock.patch.object(api, "_relay_headers", return_value={}),
			mock.patch.object(api, "_relay_session"),
			mock.patch.object(api, "_post", post),
			mock.patch.object(api, "_drive_fetch_continue_loop", side_effect=lambda result, *a, **k: result),
			mock.patch.object(api.frappe, "get_roles", return_value=["Accounts User"]),
			mock.patch.object(api.frappe, "session", mock.Mock(user="accounts@example.com")),
		]
		self._with(patches, lambda: api.send_message("overdue invoices", company="Beta Ltd"))
		self.assertEqual(post.call_args.args[0], "https://relay.test/platform-api/v1/agent/turn")
		self.assertEqual(post.call_args.args[1]["company_name"], "Beta Ltd")

	def test_a_next_page_goes_with_the_selected_company_too(self):
		settings = mock.Mock(relay_base_url="https://relay.test/platform-api/")
		post = mock.Mock(return_value={"status": "final", "reply": "ok"})
		patches = _site(["Alpha Ltd", "Beta Ltd"], user_default="Alpha Ltd") + [
			mock.patch.object(api, "_settings", return_value=settings),
			mock.patch.object(api, "_relay_headers", return_value={}),
			mock.patch.object(api, "_relay_session"),
			mock.patch.object(api, "_post", post),
			mock.patch.object(api, "_drive_fetch_continue_loop", side_effect=lambda result, *a, **k: result),
			mock.patch.object(api.frappe, "get_roles", return_value=["Accounts User"]),
			mock.patch.object(api.frappe, "session", mock.Mock(user="accounts@example.com")),
		]
		self._with(patches, lambda: api.next_page("sales_invoice.list", "{}", company="Beta Ltd"))
		self.assertEqual(post.call_args.args[0], "https://relay.test/platform-api/v1/agent/turn/next-page")
		self.assertEqual(post.call_args.args[1]["company_name"], "Beta Ltd")


if __name__ == "__main__":
	unittest.main()
