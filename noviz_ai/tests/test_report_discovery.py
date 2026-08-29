# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for the report-discovery helpers (noviz_ai.api).

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_report_discovery`.

_normalize_report_filter is the only piece with real logic worth unit
testing (turning a Report Filter child row into a clean descriptor). The
whitelisted endpoints (discover_reports / get_report_filters) are thin
wrappers over frappe.get_list / frappe.get_doc whose real behaviour IS
ERPNext's own permission layer — exercised end to end from the relay,
not mocked here.
"""
import unittest

from noviz_ai.api import _normalize_report_filter


class _Row:
	"""Stands in for a Frappe child doc (attribute access)."""

	def __init__(self, **kw):
		for k, v in kw.items():
			setattr(self, k, v)

	def get(self, key, default=None):  # some call sites use .get on child docs
		return getattr(self, key, default)


class TestNormalizeReportFilter(unittest.TestCase):
	def test_plain_dict_row(self):
		out = _normalize_report_filter({"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"})
		self.assertEqual(out, {"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"})

	def test_object_row(self):
		out = _normalize_report_filter(_Row(fieldname="company", label="Company", fieldtype="Link", options="Company"))
		self.assertEqual(out["fieldname"], "company")
		self.assertEqual(out["options"], "Company")

	def test_missing_fieldname_is_dropped(self):
		self.assertEqual(_normalize_report_filter({"label": "orphan"}), {})
		self.assertEqual(_normalize_report_filter(_Row(label="orphan")), {})

	def test_label_defaults_from_fieldname(self):
		out = _normalize_report_filter({"fieldname": "cost_center"})
		self.assertEqual(out["label"], "Cost Center")
		self.assertEqual(out["fieldtype"], "Data")  # default when none given

	def test_mandatory_from_either_flag(self):
		self.assertTrue(_normalize_report_filter({"fieldname": "x", "mandatory": 1}).get("mandatory"))
		self.assertTrue(_normalize_report_filter({"fieldname": "x", "reqd": 1}).get("mandatory"))
		self.assertNotIn("mandatory", _normalize_report_filter({"fieldname": "x"}))

	def test_default_only_when_meaningful(self):
		self.assertEqual(_normalize_report_filter({"fieldname": "x", "default": "Today"}).get("default"), "Today")
		self.assertNotIn("default", _normalize_report_filter({"fieldname": "x", "default": ""}))
		self.assertNotIn("default", _normalize_report_filter({"fieldname": "x", "default": None}))

	def test_empty_options_not_carried(self):
		self.assertNotIn("options", _normalize_report_filter({"fieldname": "x", "options": ""}))


if __name__ == "__main__":
	unittest.main()
