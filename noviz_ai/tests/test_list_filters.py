# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for plain lists on Frappe 15 (noviz_ai.dispatcher, noviz_ai.pdf_report).

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_list_filters`.

Frappe 15 reads neither the date word "today" nor a linked record's field in
a filter, for a plain list or its PDF as for grouped totals.
"""
import json
import unittest
from unittest import mock

from noviz_ai import dispatcher, pdf_report, utils


def _patch():
	frappe = mock.MagicMock()
	frappe.as_json.side_effect = json.dumps
	frappe.has_permission.return_value = True
	frappe.is_table.return_value = False
	frappe.utils.today.return_value = "2026-11-09"
	frappe.get_meta.return_value.get_field.return_value.options = "Customer"
	frappe.get_list.side_effect = lambda doctype, **kw: ["C1", "C2"] if doctype == "Customer" else []
	patches = mock.patch.multiple(dispatcher, frappe=frappe), mock.patch.multiple(pdf_report, frappe=frappe), mock.patch.multiple(utils, frappe=frappe)
	return patches, frappe


FILTERS = [["due_date", "<", "today"], ["customer.customer_group", "=", "Retail"], ["status", "=", "Overdue"]]
READ_AS_V15 = [["due_date", "<", "2026-11-09"], ["customer", "in", ["C1", "C2"]], ["status", "=", "Overdue"]]


class TestPlainListFilters(unittest.TestCase):
	def test_a_list_reads_today_and_linked_fields_as_frappe_15_does(self):
		patches, frappe = _patch()
		with patches[0], patches[1], patches[2]:
			dispatcher.execute_call_spec({"kind": "get_list", "doctype": "Sales Invoice", "filters": FILTERS})
		self.assertEqual(frappe.get_list.call_args.kwargs["filters"], READ_AS_V15)

	def test_a_list_pdf_reads_them_the_same_way(self):
		patches, frappe = _patch()
		with patches[0], patches[1], patches[2]:
			pdf_report.fetch_entity_rows("Sales Invoice", ["name"], FILTERS)
		self.assertEqual(frappe.get_list.call_args.kwargs["filters"], READ_AS_V15)

	def test_a_pdf_grouped_by_a_linked_field_uses_its_alias_and_keeps_the_fields_name(self):
		patches, frappe = _patch()
		frappe.get_list.side_effect = lambda doctype, **kw: [{"_group_key": "Retail", "sum_grand_total": 5}]
		metrics = [{"op": "sum", "field": "grand_total"}]
		with patches[0], patches[1], patches[2]:
			rows = pdf_report.run_aggregate_query("Sales Invoice", "customer.customer_group", metrics, None)
		kwargs = frappe.get_list.call_args.kwargs
		self.assertEqual(kwargs["fields"][0], "customer.customer_group as _group_key")
		self.assertEqual(kwargs["group_by"], "_group_key")
		self.assertEqual(rows, [{"sum_grand_total": 5, "customer_group": "Retail"}])

	def test_a_pdf_grouped_by_the_documents_own_field_is_unchanged(self):
		patches, frappe = _patch()
		frappe.get_list.side_effect = lambda doctype, **kw: [{"customer": "C1", "sum_grand_total": 5}]
		metrics = [{"op": "sum", "field": "grand_total"}]
		with patches[0], patches[1], patches[2]:
			rows = pdf_report.run_aggregate_query("Sales Invoice", "customer", metrics, None)
		kwargs = frappe.get_list.call_args.kwargs
		self.assertEqual((kwargs["fields"][0], kwargs["group_by"]), ("customer", "customer"))
		self.assertEqual(rows, [{"customer": "C1", "sum_grand_total": 5}])

	def test_a_list_without_filters_is_unchanged(self):
		patches, frappe = _patch()
		with patches[0], patches[1], patches[2]:
			dispatcher.execute_call_spec({"kind": "get_list", "doctype": "Sales Invoice"})
		self.assertIsNone(frappe.get_list.call_args.kwargs["filters"])

	def test_a_list_asks_only_for_the_columns_this_sites_doctype_has(self):
		# Lead.utm_source exists on Frappe 16 only; asking for it failed the
		# whole list on a Frappe 15 site (2026-11-11).
		patches, frappe = _patch()
		frappe.get_meta.return_value.fields = [mock.Mock(fieldname="lead_name"), mock.Mock(fieldname="status")]
		with patches[0], patches[1], patches[2]:
			dispatcher.execute_call_spec({"kind": "get_list", "doctype": "Lead", "fields": ["name", "lead_name", "utm_source", "status"]})
			pdf_report.fetch_entity_rows("Lead", ["name", "lead_name", "utm_source"], None)
		calls = [c.kwargs["fields"] for c in frappe.get_list.call_args_list if c.args and c.args[0] == "Lead"]
		self.assertEqual(calls, [["name", "lead_name", "status"], ["name", "lead_name"]])

	def test_columns_are_asked_for_as_before_when_the_definition_cannot_be_read(self):
		patches, frappe = _patch()
		frappe.get_meta.side_effect = Exception("no meta")
		with patches[0], patches[1], patches[2]:
			dispatcher.execute_call_spec({"kind": "get_list", "doctype": "Lead", "fields": ["name", "utm_source"]})
		self.assertEqual(frappe.get_list.call_args.kwargs["fields"], ["name", "utm_source"])


if __name__ == "__main__":
	unittest.main()
