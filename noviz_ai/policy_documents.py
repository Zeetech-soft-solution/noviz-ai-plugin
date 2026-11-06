# Policy documents: the company's Word (.docx) or PDF documents, each for one
# module or for every module (common), several per module. They are sent to
# the Noviz AI relay, which splits them into passages and searches them when a
# task needs the company's policy or procedure (knowledge.search). Nothing is
# kept on this site: the uploaded file is removed once the relay has it. The
# same file name in the same module replaces the earlier version.
import os

import frappe
import requests

from noviz_ai.api import _settings

REQUEST_TIMEOUT_SECONDS = 300


def _relay(path):
	settings = _settings()
	return settings.relay_base_url.rstrip("/") + path, {"Authorization": f"Bearer {settings.get_password('api_key')}"}


def _relay_error(response):
	try:
		return response.json().get("error") or response.text[:250]
	except ValueError:
		return response.text[:250]


@frappe.whitelist()
def list_policy_documents():
	frappe.only_for("System Manager")
	url, headers = _relay("/v1/agent/knowledge/documents")
	try:
		response = requests.get(url, headers=headers, timeout=30)
	except requests.exceptions.RequestException as e:
		frappe.throw(f"Could not reach Noviz AI: {e}")
	if not response.ok:
		frappe.throw(_relay_error(response))
	return response.json()


@frappe.whitelist()
def upload_policy_document(file_url: str, module: str):
	"""Sends an uploaded File (Word or PDF) to the relay for `module` ("common"
	for every module), then removes the File from this site."""
	frappe.only_for("System Manager")
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	filename = file_doc.file_name or os.path.basename(file_url)
	content = file_doc.get_content()
	if isinstance(content, str):
		content = content.encode()
	url, headers = _relay("/v1/agent/knowledge/documents")
	try:
		response = requests.post(
			url,
			headers=headers,
			data={"module": module or "common", "erp_user": frappe.session.user},
			files={"file": (filename, content, "application/octet-stream")},
			timeout=REQUEST_TIMEOUT_SECONDS,
		)
	except requests.exceptions.RequestException as e:
		frappe.throw(f"Could not reach Noviz AI: {e}")
	finally:
		# The document now lives with Noviz AI; no copy stays on this site.
		frappe.delete_doc("File", file_doc.name, ignore_permissions=True, force=True)
	if not response.ok:
		frappe.throw(f"{filename} could not be uploaded: {_relay_error(response)}")
	return response.json()


@frappe.whitelist()
def remove_policy_document(document_id: str):
	frappe.only_for("System Manager")
	url, headers = _relay(f"/v1/agent/knowledge/documents/{document_id}")
	try:
		response = requests.delete(url, headers=headers, timeout=30)
	except requests.exceptions.RequestException as e:
		frappe.throw(f"Could not reach Noviz AI: {e}")
	if not response.ok:
		frappe.throw(_relay_error(response))
	return {"ok": True}
