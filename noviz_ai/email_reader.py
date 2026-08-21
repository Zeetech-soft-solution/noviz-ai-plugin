# A live incident (Frappe's own core POP3 receive code calls dele() on
# every fetched message, permanently removing it from the server) showed
# that reusing Frappe's own Email Account.receive()/pull() machinery for
# an "agent reads the inbox" feature is not safe by default. This module
# is a separate, purpose-built, READ-ONLY path: IMAP only (never POP3),
# the mailbox is opened in IMAP's own server-enforced read-only mode
# (SELECT ... readonly=True — the server itself rejects any flag/delete
# command over that connection, not just a client-side promise), and
# every fetch uses BODY.PEEK[] specifically so messages are never even
# marked \Seen as a side effect. Nothing here ever calls STORE, EXPUNGE,
# or DELE. Deliberately narrow in scope: this module only reads; sending
# a reply is a separate concern (see email_sender.py).
#
# Credentials come from Noviz AI Settings' own dedicated fields
# (email_host/email_port/email_username/email_password), the same
# encrypted-Password-field convention api_key already uses — a separate
# credential from whatever Frappe's own Email Account doctype has stored,
# not read from or written back to that doctype at all.
import email as email_lib
import imaplib
from email.header import decode_header
from email.utils import parseaddr

import frappe


def _decode_header_value(raw):
	if not raw:
		return ""
	parts = decode_header(raw)
	decoded = ""
	for text, charset in parts:
		if isinstance(text, bytes):
			decoded += text.decode(charset or "utf-8", errors="replace")
		else:
			decoded += text
	return decoded


def _plain_text_body(msg):
	if msg.is_multipart():
		for part in msg.walk():
			if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
				charset = part.get_content_charset() or "utf-8"
				payload = part.get_payload(decode=True)
				if payload:
					return payload.decode(charset, errors="replace")
		return ""
	charset = msg.get_content_charset() or "utf-8"
	payload = msg.get_payload(decode=True)
	return payload.decode(charset, errors="replace") if payload else ""


def fetch_recent_emails(limit: int = 10):
	"""Real, live, READ-ONLY fetch of the most recent messages in this
	site's own configured inbox. Returns a plain list of dicts (subject,
	sender, sender_name, date, body) — never touches or creates any
	ERPNext Communication record, and never mutates the mailbox itself.
	"""
	settings = frappe.get_single("Noviz AI Settings")
	host = settings.email_host
	port = settings.email_port or 993
	username = settings.email_username
	password = settings.get_password("email_password", raise_exception=False)
	if not (host and username and password):
		return []

	conn = imaplib.IMAP4_SSL(host, port)
	try:
		conn.login(username, password)
		# readonly=True — the IMAP server itself refuses any command that
		# would change a flag or delete a message over this connection,
		# not merely a client-side intention. This is the real guarantee
		# against a repeat of the POP3 incident, enforced server-side.
		conn.select("INBOX", readonly=True)
		status, data = conn.search(None, "ALL")
		if status != "OK" or not data or not data[0]:
			return []
		ids = data[0].split()
		recent_ids = ids[-limit:] if len(ids) > limit else ids

		results = []
		for msg_id in reversed(recent_ids):
			# BODY.PEEK[] (not BODY[]/RFC822) — the one real difference
			# that keeps this from marking a message \Seen just by
			# reading it, same non-mutating guarantee as readonly=True
			# above but for the read-marker specifically.
			status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[])")
			if status != "OK" or not msg_data or not msg_data[0]:
				continue
			raw = msg_data[0][1]
			msg = email_lib.message_from_bytes(raw)
			sender_name, sender_email = parseaddr(_decode_header_value(msg.get("From")))
			results.append(
				{
					"subject": _decode_header_value(msg.get("Subject")),
					"sender": sender_email,
					"sender_name": sender_name or sender_email,
					"date": msg.get("Date"),
					"body": _plain_text_body(msg).strip(),
				}
			)
		return results
	finally:
		try:
			conn.close()
		except Exception:
			pass
		try:
			conn.logout()
		except Exception:
			pass
