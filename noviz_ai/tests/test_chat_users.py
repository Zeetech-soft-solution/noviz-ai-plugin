# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for Noviz AI Users (noviz_ai.chat_users): the list in Noviz AI Settings.

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_chat_users`.

The list goes to the relay when it changes, and the save stops with the
relay's message when the relay refuses it (more users than the subscription
allows). Listed users get the Noviz AI Agent role; a user taken off the list
loses it; users never on the list keep their roles.
"""
import unittest
from types import SimpleNamespace
from unittest import mock

from noviz_ai import chat_users


def _settings(users, before=None, key="tnt_test", url="https://relay.example/platform-api"):
	doc = SimpleNamespace(
		relay_base_url=url,
		chat_users=[SimpleNamespace(user=u) for u in users],
	)
	doc.get = lambda field, default=None: getattr(doc, field, default)
	doc.get_password = lambda field, raise_exception=True: key
	previous = None
	if before is not None:
		previous = SimpleNamespace(chat_users=[SimpleNamespace(user=u) for u in before])
		previous.get = lambda field, default=None: getattr(previous, field, default)
	doc.get_doc_before_save = lambda: previous
	return doc


def _response(status, body=None):
	return SimpleNamespace(status_code=status, ok=200 <= status < 300, json=lambda: body or {})


class TestSendChatUsers(unittest.TestCase):
	def test_an_unchanged_list_sends_nothing(self):
		with mock.patch.object(chat_users.requests, "post") as post:
			chat_users.send_chat_users(_settings([], before=[]))
			chat_users.send_chat_users(_settings(["a@x.com"], before=["a@x.com"]))
		post.assert_not_called()

	def test_a_changed_list_goes_to_the_relay_with_the_administrator(self):
		with mock.patch.object(chat_users.requests, "post", return_value=_response(200, {"ok": True})) as post, mock.patch.object(
			chat_users.frappe, "session", SimpleNamespace(user="admin@x.com")
		):
			chat_users.send_chat_users(_settings(["a@x.com", "b@x.com", "a@x.com"], before=["a@x.com"]))
		url = post.call_args.args[0]
		self.assertEqual(url, "https://relay.example/platform-api/v1/agent/users")
		self.assertEqual(post.call_args.kwargs["json"], {"users": ["a@x.com", "b@x.com"], "admin_user": "admin@x.com"})
		self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer tnt_test")

	def test_a_list_the_relay_refuses_stops_the_save_with_its_message(self):
		refusal = "Your Noviz AI subscription allows 2 users; the list has 3."
		with mock.patch.object(chat_users.requests, "post", return_value=_response(400, {"error": refusal})), mock.patch.object(
			chat_users.frappe, "session", SimpleNamespace(user="admin@x.com")
		), mock.patch.object(chat_users.frappe, "throw", side_effect=Exception) as throw:
			with self.assertRaises(Exception):
				chat_users.send_chat_users(_settings(["a", "b", "c"], before=[]))
		throw.assert_called_once_with(refusal)

	def test_without_a_key_the_list_cannot_be_saved(self):
		with mock.patch.object(chat_users.requests, "post") as post, mock.patch.object(chat_users.frappe, "throw", side_effect=Exception):
			with self.assertRaises(Exception):
				chat_users.send_chat_users(_settings(["a@x.com"], before=[], key=None))
		post.assert_not_called()


class TestChatUserRoles(unittest.TestCase):
	def test_listed_users_get_the_role_and_removed_users_lose_it(self):
		roles = {"new@x.com": ["Sales User"], "kept@x.com": ["Noviz AI Agent"], "gone@x.com": ["Noviz AI Agent", "Sales User"]}
		users = {name: mock.Mock() for name in roles}
		with mock.patch.object(chat_users.frappe, "get_roles", side_effect=lambda u: roles[u]), mock.patch.object(
			chat_users.frappe, "get_doc", side_effect=lambda doctype, name: users[name]
		):
			chat_users.apply_chat_user_roles(_settings(["new@x.com", "kept@x.com", "Administrator"], before=["kept@x.com", "gone@x.com"]))
		users["new@x.com"].add_roles.assert_called_once_with("Noviz AI Agent")
		users["kept@x.com"].add_roles.assert_not_called()
		users["gone@x.com"].remove_roles.assert_called_once_with("Noviz AI Agent")

	def test_users_never_on_the_list_keep_their_roles(self):
		with mock.patch.object(chat_users.frappe, "get_roles", return_value=["Noviz AI Agent"]), mock.patch.object(chat_users.frappe, "get_doc") as get_doc:
			chat_users.apply_chat_user_roles(_settings([], before=[]))
		get_doc.assert_not_called()
