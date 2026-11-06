// Copyright (c) 2026, Zeetech Soft Solution and contributors
// For license information, please see license.txt

frappe.ui.form.on("Noviz AI Settings", {
	refresh(frm) {
		_widen_policy_columns(frm);
		_lock_module_policies_rows(frm);
		_render_policy_documents(frm);
	},
});

// Policy documents: Word / PDF per module or for every module (Common), kept
// by Noviz AI (noviz_ai/policy_documents.py), searched when a task needs them.
const POLICY_DOCUMENT_MODULES = {
	common: __("Common"),
	selling: __("Selling"),
	buying: __("Buying"),
	accounting: __("Accounting"),
	hr: __("HR / HRMS"),
	stock: __("Stock / Inventory"),
	manufacturing: __("Manufacturing"),
	projects: __("Projects"),
	quality: __("Quality"),
	support: __("Support"),
	assets: __("Assets"),
	crm: __("CRM"),
};

function _render_policy_documents(frm) {
	const field = frm.fields_dict.policy_documents_html;
	if (!field) return;
	const $wrap = $(field.wrapper).empty();
	if (!frm.doc.api_key) {
		$wrap.html(`<p class="text-muted">${__("Save the AI Relay Token first.")}</p>`);
		return;
	}
	$wrap.html(`<p class="text-muted">${__("Loading documents...")}</p>`);
	frappe
		.xcall("noviz_ai.policy_documents.list_policy_documents")
		.then((r) => _draw_policy_documents(frm, $wrap, r.documents || []))
		.catch(() => $wrap.html(`<p class="text-muted">${__("Policy documents are not available right now.")}</p>`));
}

function _draw_policy_documents(frm, $wrap, documents) {
	const label = (m) => POLICY_DOCUMENT_MODULES[m] || m;
	const rows = documents
		.sort((a, b) => (label(a.module) + a.filename).localeCompare(label(b.module) + b.filename))
		.map(
			(d) => `<tr>
				<td>${frappe.utils.escape_html(label(d.module))}</td>
				<td>${frappe.utils.escape_html(d.filename)}</td>
				<td class="text-right">${cint(d.passages)}</td>
				<td>${frappe.utils.escape_html((d.updated_at || "").replace("T", " ").slice(0, 16))}</td>
				<td class="text-right"><button class="btn btn-xs btn-default" data-remove="${frappe.utils.escape_html(d.id)}" data-name="${frappe.utils.escape_html(d.filename)}">${__("Remove")}</button></td>
			</tr>`
		)
		.join("");
	$wrap.html(`
		<div class="mb-3"><button class="btn btn-sm btn-primary" data-upload>${__("Upload Document")}</button></div>
		${
			documents.length
				? `<table class="table table-bordered table-sm">
					<thead><tr><th>${__("Module")}</th><th>${__("Document")}</th><th class="text-right">${__("Passages")}</th><th>${__("Updated")}</th><th></th></tr></thead>
					<tbody>${rows}</tbody></table>`
				: `<p class="text-muted">${__("No policy documents yet.")}</p>`
		}`);
	$wrap.find("[data-upload]").on("click", () => _upload_policy_document(frm));
	$wrap.find("[data-remove]").on("click", function () {
		const id = $(this).attr("data-remove");
		const name = $(this).attr("data-name");
		frappe.confirm(__("Remove {0}? Noviz AI will no longer use it.", [name]), () =>
			frappe
				.xcall("noviz_ai.policy_documents.remove_policy_document", { document_id: id })
				.then(() => _render_policy_documents(frm))
		);
	});
}

function _upload_policy_document(frm) {
	new frappe.ui.FileUploader({
		allow_multiple: false,
		make_attachments_public: false,
		restrictions: { allowed_file_types: [".pdf", ".docx"] },
		on_success(file_doc) {
			const dialog = new frappe.ui.Dialog({
				title: __("Which module is {0} for?", [file_doc.file_name]),
				fields: [
					{
						fieldname: "module",
						fieldtype: "Select",
						label: __("Module"),
						reqd: 1,
						default: "common",
						options: Object.entries(POLICY_DOCUMENT_MODULES).map(([value, label]) => ({ value, label })),
					},
				],
				primary_action_label: __("Upload"),
				primary_action({ module }) {
					dialog.hide();
					frappe.show_alert({ message: __("Uploading {0}...", [file_doc.file_name]), indicator: "blue" });
					frappe
						.xcall("noviz_ai.policy_documents.upload_policy_document", { file_url: file_doc.file_url, module })
						.then((r) => {
							frappe.show_alert({ message: __("{0} uploaded ({1} passages).", [r.filename, r.passages]), indicator: "green" });
							_render_policy_documents(frm);
						});
				},
			});
			dialog.show();
		},
	});
}

function _lock_module_policies_rows(frm) {
	const grid = frm.fields_dict.module_policies?.grid;
	if (!grid) return;
	grid.cannot_add_rows = true;
	grid.cannot_delete_rows = true;
	grid.refresh();
}

function _widen_policy_columns(frm) {
	if (document.getElementById("noviz-ai-policy-grid-style")) return;
	const style = document.createElement("style");
	style.id = "noviz-ai-policy-grid-style";
	style.textContent = `
		.frappe-control[data-fieldname="module_policies"] .static-area.ellipsis {
			white-space: normal !important;
			text-overflow: unset !important;
			overflow: visible !important;
			line-height: 1.4;
			max-height: 6em;
			overflow-y: auto !important;
		}
		.frappe-control[data-fieldname="module_policies"] .grid-row {
			min-height: 2.6em;
		}
	`;
	document.head.appendChild(style);
}
