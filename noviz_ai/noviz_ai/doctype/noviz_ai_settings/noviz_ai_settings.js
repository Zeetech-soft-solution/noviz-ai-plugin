// Copyright (c) 2026, Zeetech Soft Solution and contributors
// For license information, please see license.txt

frappe.ui.form.on("Noviz AI Settings", {
	refresh(frm) {
		_widen_policy_columns(frm);
		_lock_module_policies_rows(frm);
	},
});

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
