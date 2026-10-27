# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for document actions (noviz_ai.document_actions).

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_document_actions`.

ERPNext decides: workflow transitions come from Frappe for this user, submit
and cancel only without a workflow and with permission, a "make" action is
offered only with create permission on its target and runs ERPNext's own
whitelisted mapper, and every refusal is Frappe's own.
"""
import unittest
from unittest import mock

from noviz_ai import document_actions as da


class _Doc(dict):
	def __init__(self, doctype="Purchase Order", name="PO-0012", docstatus=0, perms=("read", "submit", "cancel"), **fields):
		super().__init__(fields)
		self.doctype = doctype
		self.name = name
		self.docstatus = docstatus
		self._perms = set(perms)
		self.calls = []

	def get(self, key, default=None):
		return dict.get(self, key, default)

	def has_permission(self, ptype):
		return ptype in self._perms

	def submit(self):
		self.calls.append("submit")
		self.docstatus = 1

	def cancel(self):
		self.calls.append("cancel")
		self.docstatus = 2

	def insert(self):
		self.calls.append("insert")

	def update(self, values):
		self.calls.append(("update", values))
		dict.update(self, values)


class _Throw(Exception):
	pass


def _patch(doc, workflow=None, transitions=(), submittable=True, create_ok=True, mapper=None):
	frappe = mock.MagicMock()
	frappe.get_doc.side_effect = lambda *a: doc if len(a) == 2 else a[0]
	frappe.throw.side_effect = lambda msg, *a: (_ for _ in ()).throw(_Throw(msg))
	frappe.PermissionError = PermissionError
	frappe.get_cached_value.return_value = "workflow_state"
	frappe.get_meta.return_value = mock.Mock(is_submittable=submittable)
	frappe.has_permission.side_effect = lambda doctype, ptype: create_ok
	frappe.get_attr.return_value = mapper
	return mock.patch.multiple(
		da,
		frappe=frappe,
		get_workflow_name=mock.Mock(return_value=workflow),
		get_transitions=mock.Mock(return_value=[{"action": a, "next_state": s} for a, s in transitions]),
		apply_workflow=mock.Mock(side_effect=lambda d, action: (d.__setitem__("workflow_state", "Approved"), d)[1]),
	), frappe


class TestGetActions(unittest.TestCase):
	def test_workflow_document_lists_only_its_allowed_transitions(self):
		doc = _Doc(workflow_state="Pending Approval")
		patcher, _ = _patch(doc, workflow="PO Approval", transitions=[("Approve", "Approved"), ("Reject", "Rejected")])
		with patcher:
			out = da.get_actions({"doctype": "Purchase Order", "name": "PO-0012"})
		self.assertEqual(out["workflow_state"], "Pending Approval")
		self.assertEqual([a["action"] for a in out["actions"]], ["Approve", "Reject"])
		self.assertNotIn("submit", [a["kind"] for a in out["actions"]])

	def test_without_workflow_submit_needs_permission(self):
		patcher, _ = _patch(_Doc(docstatus=0))
		with patcher:
			self.assertEqual(da.get_actions({"doctype": "Purchase Order", "name": "PO-0012"})["actions"], [{"kind": "submit"}])
		patcher, _ = _patch(_Doc(docstatus=0, perms=("read",)))
		with patcher:
			self.assertEqual(da.get_actions({"doctype": "Purchase Order", "name": "PO-0012"})["actions"], [])

	def test_make_offered_only_with_create_permission_on_target(self):
		offer = [{"kind": "make", "name": "make_purchase_receipt", "label": "Create Purchase Receipt", "method": "m", "targetDoctype": "Purchase Receipt"}]
		patcher, _ = _patch(_Doc(docstatus=1, perms=("read",)), create_ok=True)
		with patcher:
			self.assertEqual(da.get_actions({"doctype": "Purchase Order", "name": "PO-0012", "offer": offer})["actions"][0]["action"], "make_purchase_receipt")
		patcher, _ = _patch(_Doc(docstatus=1, perms=("read",)), create_ok=False)
		with patcher:
			self.assertEqual(da.get_actions({"doctype": "Purchase Order", "name": "PO-0012", "offer": offer})["actions"], [])

	def test_no_read_permission_is_refused(self):
		patcher, _ = _patch(_Doc(perms=()))
		with patcher, self.assertRaises(_Throw):
			da.get_actions({"doctype": "Purchase Order", "name": "PO-0012"})


class TestRunAction(unittest.TestCase):
	def test_workflow_action_goes_through_frappe(self):
		doc = _Doc(workflow_state="Pending Approval")
		patcher, frappe = _patch(doc, workflow="PO Approval")
		with patcher:
			out = da.run_action({"doctype": "Purchase Order", "name": "PO-0012", "action": {"kind": "workflow", "action": "Approve"}})
			da.apply_workflow.assert_called_once_with(doc, "Approve")
		self.assertEqual(out["workflow_state"], "Approved")
		frappe.db.commit.assert_called_once()

	def test_submit_is_refused_when_a_workflow_governs_the_document(self):
		doc = _Doc()
		patcher, _ = _patch(doc, workflow="PO Approval")
		with patcher, self.assertRaises(_Throw):
			da.run_action({"doctype": "Purchase Order", "name": "PO-0012", "action": {"kind": "submit"}})
		self.assertEqual(doc.calls, [])

	def test_make_runs_the_whitelisted_mapper_and_saves_a_draft(self):
		new_doc = _Doc(doctype="Purchase Receipt", name="PR-0001")
		mapper = mock.Mock(return_value=new_doc)
		patcher, frappe = _patch(_Doc(docstatus=1), mapper=mapper)
		with patcher:
			out = da.run_action({"doctype": "Purchase Order", "name": "PO-0012", "action": {"kind": "make", "method": "erpnext.x.make_purchase_receipt", "values": {"posting_date": "2026-10-28"}}})
			frappe.is_whitelisted.assert_called_once_with(mapper)
		mapper.assert_called_once_with(source_name="PO-0012")
		self.assertEqual(new_doc.calls, [("update", {"posting_date": "2026-10-28"}), "insert"])
		self.assertEqual(out["name"], "PR-0001")


if __name__ == "__main__":
	unittest.main()
