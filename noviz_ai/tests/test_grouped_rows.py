# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for grouped rows (noviz_ai.aggregate.run_grouped_rows).

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_grouped_rows`.

ERPNext sums the rows itself under the person's permissions: everything
before the period's first day into one row per group dated the day before,
the period into months, the month holding the first day dated that day. The
relay names plain fields only. Frappe 15 forms: sums named with their
table, filters through frappe15_filters.
"""
import datetime
import unittest
from unittest import mock

from noviz_ai import aggregate


class _Throw(Exception):
	pass


def _throw(message, exc=None):
	raise _Throw(message)


SPEC = {
	"doctype": "GL Entry",
	"filters": [["posting_date", "<=", "2025-06-30"], ["is_cancelled", "=", 0]],
	"date_field": "posting_date",
	"split_at": "2025-04-15",
	"group_fields": ["account"],
	"sums": ["debit", "credit"],
}

BEFORE = [{"account": "Cash", "debit": 100.0, "credit": 40.0}, {"account": "Sales", "debit": 0.0, "credit": 0.0}]
DAYS = [
	{"posting_date": datetime.date(2025, 4, 15), "account": "Cash", "debit": 5.0, "credit": 0.0},
	{"posting_date": datetime.date(2025, 4, 30), "account": "Cash", "debit": 7.0, "credit": 1.0},
	{"posting_date": datetime.date(2025, 5, 2), "account": "Cash", "debit": 3.0, "credit": 0.0},
	{"posting_date": datetime.date(2025, 5, 20), "account": "Sales", "debit": 0.0, "credit": 9.0},
	{"posting_date": datetime.date(2025, 6, 30), "account": "Cash", "debit": 2.0, "credit": 2.0},
]


def _get_list(doctype, fields=None, filters=None, group_by=None, **kwargs):
	op = filters[-1][1]
	return BEFORE if op == "<" else DAYS


class TestGroupedRows(unittest.TestCase):
	def setUp(self):
		self.patches = [
			mock.patch.object(aggregate.frappe, "throw", side_effect=_throw),
			mock.patch.object(aggregate.frappe, "has_permission", return_value=True),
			mock.patch.object(aggregate.frappe, "get_list", side_effect=_get_list),
			mock.patch.object(aggregate, "child_parent_doctype", return_value=None),
			mock.patch.object(aggregate, "frappe15_filters", side_effect=lambda doctype, filters: filters),
		]
		for p in self.patches:
			p.start()

	def tearDown(self):
		for p in self.patches:
			p.stop()

	def test_months_with_the_cut_at_the_first_day(self):
		rows = aggregate.run_grouped_rows(SPEC)
		self.assertEqual(
			rows,
			[
				{"posting_date": "2025-04-14", "account": "Cash", "debit": 100.0, "credit": 40.0},
				{"posting_date": "2025-04-15", "account": "Cash", "debit": 12.0, "credit": 1.0},
				{"posting_date": "2025-05-01", "account": "Cash", "debit": 3.0, "credit": 0.0},
				{"posting_date": "2025-05-01", "account": "Sales", "debit": 0.0, "credit": 9.0},
				{"posting_date": "2025-06-01", "account": "Cash", "debit": 2.0, "credit": 2.0},
			],
		)

	def test_same_totals_as_the_rows(self):
		rows = aggregate.run_grouped_rows(SPEC)
		for f in ("debit", "credit"):
			self.assertEqual(sum(r[f] for r in rows), sum(r[f] for r in BEFORE + DAYS))

	def test_erpnext_groups_and_sums(self):
		aggregate.run_grouped_rows(SPEC)
		before, days = aggregate.frappe.get_list.call_args_list
		self.assertEqual(before.kwargs["fields"], ["account", "sum(`tabGL Entry`.`debit`) as debit", "sum(`tabGL Entry`.`credit`) as credit"])
		self.assertEqual(before.kwargs["group_by"], "account")
		self.assertEqual(before.kwargs["filters"][-1][:2], ["posting_date", "<"])
		self.assertEqual(days.kwargs["group_by"], "posting_date, account")
		self.assertEqual(days.kwargs["filters"][-1][:2], ["posting_date", ">="])
		self.assertEqual(days.kwargs["filters"][:2], SPEC["filters"])
		aggregate.frappe15_filters.assert_called()

	def test_only_plain_field_names(self):
		for bad in (["account; drop table x"], ["SUM(debit)"], ["party.customer_group"]):
			with self.assertRaises(_Throw):
				aggregate.run_grouped_rows({**SPEC, "group_fields": bad})
		aggregate.frappe.get_list.assert_not_called()

	def test_needs_date_field_split_and_sums(self):
		for missing in ("date_field", "split_at", "sums"):
			with self.assertRaises(_Throw):
				aggregate.run_grouped_rows({**SPEC, missing: None})

	def test_permission_is_frappe_s(self):
		aggregate.frappe.has_permission.return_value = False
		with self.assertRaises(_Throw):
			aggregate.run_grouped_rows(SPEC)
		aggregate.frappe.get_list.assert_not_called()


if __name__ == "__main__":
	unittest.main()
