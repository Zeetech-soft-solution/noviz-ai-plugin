# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for reports Frappe has marked as prepared (noviz_ai.dispatcher, noviz_ai.pdf_report).

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_prepared_report`.

Frappe marks a report that once took over 15 s as a prepared report; a plain
run of it answers with no rows and only queues it, which read as "no data".
"""
import json
import sys
import unittest
from unittest import mock

from noviz_ai import dispatcher, pdf_report


class TestPreparedReports(unittest.TestCase):
	def setUp(self):
		self.run = mock.Mock(return_value={"result": [{"party": "C1"}], "columns": []})
		modules = {"frappe.desk": mock.MagicMock(), "frappe.desk.query_report": mock.MagicMock(run=self.run)}
		frappe = mock.MagicMock()
		frappe.as_json.side_effect = json.dumps
		for patcher in (mock.patch.dict(sys.modules, modules), mock.patch.object(dispatcher, "frappe", frappe), mock.patch.object(pdf_report, "frappe", frappe)):
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_an_answer_runs_the_report(self):
		out = dispatcher.execute_call_spec({"kind": "run_report", "reportName": "Accounts Receivable Summary", "reportFilters": {}})
		self.assertEqual(out, [{"party": "C1"}])
		self.assertTrue(self.run.call_args.kwargs["ignore_prepared_report"])

	def test_a_pdf_runs_the_report(self):
		rows, _ = pdf_report.run_named_report("Accounts Receivable Summary", {})
		self.assertEqual(rows, [{"party": "C1"}])
		self.assertTrue(self.run.call_args.kwargs["ignore_prepared_report"])


if __name__ == "__main__":
	unittest.main()
