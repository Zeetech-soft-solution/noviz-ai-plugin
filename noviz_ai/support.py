"""Support tickets for Noviz support, raised from the chat's Support view.

The relay's /v1/support passes them on to Noviz support: the same calls as
the chat gateway's. This app sends the site's key, the signed-in ERPNext user
(X-ERP-User) and their full name (X-ERP-User-Name); the relay files the ticket
under the company the key belongs to. A refusal is shown in the relay's own
words. Nothing is kept on this site.
"""
from urllib.parse import quote

import frappe
import requests

from noviz_ai.api import _relay_session, _settings

PICTURE_TYPES = ("image/png", "image/jpeg", "image/webp")
PICTURE_MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 30


def _headers(settings):
	user = frappe.session.user
	full_name = frappe.utils.get_fullname(user) or user
	return {
		"Authorization": f"Bearer {settings.get_password('api_key')}",
		"X-ERP-User": user,
		"X-ERP-User-Name": quote(full_name, safe=" @.-_"),
	}


def _call(method, path, json_body=None, data=None, content_type=None, raw=False):
	settings = _settings()
	headers = _headers(settings)
	if content_type:
		headers["Content-Type"] = content_type
	url = settings.relay_base_url.rstrip("/") + "/v1/support" + path
	try:
		with _relay_session() as session:
			response = session.request(method, url, json=json_body, data=data, headers=headers, timeout=TIMEOUT_SECONDS)
	except requests.exceptions.RequestException:
		frappe.throw("Noviz support could not be reached just now. Please try again.")
	if response.status_code >= 400:
		message = None
		try:
			error = response.json().get("error")
			message = error.get("message") if isinstance(error, dict) else error
		except ValueError:
			pass
		frappe.throw(message or "Noviz support could not take this request.")
	return response if raw else response.json()


def _id(value, what="ticket"):
	value = (value or "").strip()
	if len(value) != 36 or value.count("-") != 4:
		frappe.throw(f"No such {what}.")
	return value


@frappe.whitelist()
def tickets():
	"""The signed-in user's tickets, newest first."""
	return _call("GET", "/tickets").get("tickets", [])


@frappe.whitelist(methods=["POST"])
def raise_ticket(subject: str, description: str):
	"""A new ticket; pictures are added one by one with add_picture."""
	return _call("POST", "/tickets", json_body={"subject": subject or "", "description": description or ""}).get("ticket")


@frappe.whitelist()
def ticket(ticket_id: str):
	"""One ticket with its pictures, status and Noviz support's solution."""
	return _call("GET", f"/tickets/{_id(ticket_id)}").get("ticket")


@frappe.whitelist(methods=["POST"])
def add_picture(ticket_id: str):
	"""One picture (PNG, JPEG or WebP, 5 MB at most), uploaded as the form field "picture"."""
	upload = frappe.request.files.get("picture") if frappe.request else None
	if not upload:
		frappe.throw("Attach one picture (PNG, JPEG or WebP).")
	content = upload.read()
	content_type = (upload.content_type or "").split(";")[0].strip()
	if content_type not in PICTURE_TYPES:
		frappe.throw("Only pictures can be attached (PNG, JPEG or WebP).")
	if not content or len(content) > PICTURE_MAX_BYTES:
		frappe.throw("The picture is empty or too large (5 MB at most).")
	return _call("POST", f"/tickets/{_id(ticket_id)}/attachments", data=content, content_type=content_type).get("attachment")


@frappe.whitelist()
def picture(ticket_id: str, attachment_id: str):
	"""One picture of the user's ticket, shown in the Support view."""
	response = _call("GET", f"/tickets/{_id(ticket_id)}/attachments/{_id(attachment_id, 'picture')}", raw=True)
	content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
	if content_type not in PICTURE_TYPES:
		frappe.throw("No such picture.")
	frappe.local.response.filename = f"{attachment_id}.{content_type.split('/')[1]}"
	frappe.local.response.filecontent = response.content
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"
