# Copyright (c) 2026, Zeetech Soft Solution and Contributors
# See license.txt
"""Tests for the fetch/continue loop (noviz_ai.api._drive_fetch_continue_loop).

Run with `bench --site <site> run-tests --module noviz_ai.tests.test_turn_loop`.

A long turn must pause after WORK_SECONDS_PER_REQUEST and resume through
continue_turn with its round-trip count intact; a short turn must finish in
one request exactly as before.
"""
import unittest
from unittest import mock

from noviz_ai import api


class _Cache:
	def __init__(self):
		self.store = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.store[key] = value

	def get_value(self, key):
		return self.store.get(key)

	def delete_value(self, key):
		self.store.pop(key, None)


def _fetch(n):
	return {"status": "fetch", "turnId": "t1", "request": {"kind": "get_list", "n": n}}


class TestTurnLoop(unittest.TestCase):
	def setUp(self):
		self.cache = _Cache()
		self.clock = [0.0]
		self.patches = [
			mock.patch.object(api.frappe, "cache", return_value=self.cache),
			mock.patch.object(api.time, "monotonic", side_effect=lambda: self.clock[0]),
			mock.patch.object(api, "_execute_call_spec_safely", side_effect=self._execute),
		]
		for p in self.patches:
			p.start()
		self.executed = []

	def tearDown(self):
		for p in self.patches:
			p.stop()

	def _execute(self, call_spec):
		self.executed.append(call_spec["n"])
		self.clock[0] += 15  # every fetch + relay step takes 15s
		return [{"name": "X"}]

	def test_short_turn_finishes_in_one_request(self):
		replies = iter([{"status": "final", "reply": "done", "turnId": "t1"}])
		with mock.patch.object(api, "_post", side_effect=lambda *a, **k: next(replies)):
			result = api._drive_fetch_continue_loop(_fetch(1), "https://relay", {}, None)
		self.assertEqual(result["status"], "final")
		self.assertEqual(self.executed, [1])
		self.assertEqual(self.cache.store, {})

	def test_long_turn_pauses_and_resumes(self):
		replies = iter([_fetch(2), _fetch(3), _fetch(4), {"status": "final", "reply": "done", "turnId": "t1"}])
		with mock.patch.object(api, "_post", side_effect=lambda *a, **k: next(replies)), \
			mock.patch.object(api.frappe, "session", mock.Mock(user="a@b.c")):
			first = api._drive_fetch_continue_loop(_fetch(1), "https://relay", {}, None)
			# 3 fetches x 15s passes the 40s budget: paused before fetch 4.
			self.assertEqual(first, {"status": "working", "turnId": "t1"})
			self.assertEqual(self.executed, [1, 2, 3])
			key = api._paused_turn_key("t1")
			self.assertEqual(self.cache.store[key]["round_trips"], 3)

			with mock.patch.object(api, "_settings", return_value=mock.Mock(relay_base_url="https://relay")), \
				mock.patch.object(api, "_relay_headers", return_value={}):
				final = api.continue_turn("t1")
		self.assertEqual(final["status"], "final")
		self.assertEqual(self.executed, [1, 2, 3, 4])
		self.assertNotIn(key, self.cache.store)

	def test_round_trip_ceiling_counts_across_requests(self):
		with mock.patch.object(api, "_post", side_effect=lambda *a, **k: _fetch(9)), \
			mock.patch.object(api.frappe, "throw", side_effect=RuntimeError("stopped")):
			with self.assertRaises(RuntimeError):
				api._drive_fetch_continue_loop(_fetch(1), "https://relay", {}, None, api.MAX_ROUND_TRIPS)
		self.assertEqual(self.executed, [])
