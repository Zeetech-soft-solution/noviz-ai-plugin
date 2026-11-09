# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for the chat's + menu (noviz_ai.api.chat_menu).

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_chat_menu`.

The menu's items come from the relay's /v1/agent/chat-menu; each carries the
question it sends, or its empty answer.
"""
import unittest
from unittest import mock

from noviz_ai import api


class TestChatMenu(unittest.TestCase):
	def test_asks_the_relay_at_its_agent_path(self):
		settings = mock.Mock(relay_base_url="https://relay.test/platform-api/")
		items = [{"id": "approvals", "label": "Approvals", "prompt": "What is waiting for my approval?"}]
		response = mock.Mock(ok=True)
		response.json.return_value = {"items": items}
		with mock.patch.object(api, "_settings", return_value=settings), mock.patch.object(api, "_relay_headers", return_value={}), mock.patch.object(api.requests, "get", return_value=response) as get:
			self.assertEqual(api.chat_menu(), items)
		self.assertEqual(get.call_args.args[0], "https://relay.test/platform-api/v1/agent/chat-menu")


if __name__ == "__main__":
	unittest.main()
