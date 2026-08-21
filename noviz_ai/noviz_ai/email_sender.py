# Send-side counterpart to email_reader.py: our own code, our own
# credentials (Noviz AI Settings' own smtp_host/smtp_port, reusing the
# same account username/password email_reader.py already reads for IMAP —
# one mailbox, one login, two protocols), independent of Frappe's own
# Email Account/Communication machinery. Deliberately does not create a
# Communication record as a side effect (Frappe's own
# frappe.core.doctype.communication.email.make() does that, but this
# module's whole point is not depending on Frappe's Communication table
# as the source of truth for email) — a genuinely sent message is the
# outcome that matters here, not a local record of having sent it.
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

import frappe


def send_reply(to_address: str, subject: str, body: str):
	"""Real, live SMTP send — the whole point is that this actually
	delivers, not that it queues into Frappe's own outgoing mail flow.
	Raises a plain, real exception on failure (caller's own job to
	surface that honestly, same as any other real send failure) rather
	than swallowing it here."""
	settings = frappe.get_single("Noviz AI Settings")
	host = settings.smtp_host
	port = settings.smtp_port or 465
	username = settings.email_username
	password = settings.get_password("email_password", raise_exception=False)
	if not (host and username and password):
		frappe.throw("Noviz AI: SMTP is not configured (Host/Username/Password missing under Noviz AI Settings).")

	msg = MIMEText(body, "plain", "utf-8")
	msg["Subject"] = subject
	msg["From"] = username
	msg["To"] = to_address
	msg["Date"] = formatdate(localtime=True)
	msg["Message-ID"] = make_msgid()

	# Port 465 is always implicit-TLS (SMTP_SSL from the first byte);
	# anything else (587, 25, ...) is plaintext-then-STARTTLS — the two
	# real, standard SMTP submission shapes, not something the caller
	# should have to choose between by hand.
	if port == 465:
		with smtplib.SMTP_SSL(host, port, timeout=30) as server:
			server.login(username, password)
			server.sendmail(username, [to_address], msg.as_string())
	else:
		with smtplib.SMTP(host, port, timeout=30) as server:
			server.starttls()
			server.login(username, password)
			server.sendmail(username, [to_address], msg.as_string())
