# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for the kept connection to the relay (noviz_ai.api._relay_session).

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_relay_session`.

One session per worker thread, kept between messages; a call is retried only
when the connection fails before anything was sent.
"""
import threading
import unittest

from noviz_ai import api


class TestRelaySession(unittest.TestCase):
	def test_one_session_per_thread_kept_between_messages(self):
		with api._relay_session() as first:
			pass
		with api._relay_session() as second:
			pass
		self.assertIs(first, second)

		other = {}

		def in_other_thread():
			with api._relay_session() as session:
				other["session"] = session

		t = threading.Thread(target=in_other_thread)
		t.start()
		t.join()
		self.assertIsNot(other["session"], first)

	def test_retried_only_when_nothing_was_sent(self):
		with api._relay_session() as session:
			retry = session.get_adapter("https://relay.example").max_retries
		self.assertEqual((retry.total, retry.connect, retry.read, retry.status), (1, 1, 0, 0))


if __name__ == "__main__":
	unittest.main()
