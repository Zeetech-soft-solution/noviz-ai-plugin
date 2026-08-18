// Copyright (c) 2026, Zeetech Soft Solution and contributors
// For license information, please see license.txt

// Real UX built per explicit request: editing 11 modules' worth of
// multi-line policy text inside a child-table grid (tiny inline cells)
// was genuinely unusable. The child table (module_policies) is still
// the REAL data — one row per module, what actually gets synced to the
// relay (api.py's sync_module_policies) — this is just a friendlier way
// to edit it: pick a module from the dropdown, two big boxes show/edit
// THAT module's own strict/warning text, switching the dropdown saves
// whatever you typed back into the previously-selected module's real
// row before loading the newly-picked one's.
frappe.ui.form.on("Noviz AI Settings", {
	refresh(frm) {
		// Real, resizable, genuinely tall boxes — "unlimited rows,
		// flexible" per explicit request. Frappe's own "Text" fieldtype
		// textarea is resizable by default (native browser drag handle);
		// this just starts it much taller than the default ~2 rows so a
		// real multi-line policy doesn't start out looking cramped.
		["policy_strict_text", "policy_warning_text"].forEach((fieldname) => {
			const $textarea = frm.fields_dict[fieldname]?.$wrapper?.find("textarea");
			if ($textarea?.length) {
				$textarea.css({ "min-height": "220px", resize: "vertical" });
			}
		});

		// Real bug found live via browser testing: frm.set_value() marks
		// the whole form dirty ("Not Saved") — right, for a genuine edit,
		// but this is purely re-displaying data that's already saved.
		// Confirmed live: simply opening this page for the first time
		// showed "Not Saved" with nothing actually changed. Setting
		// frm.doc directly + refresh_field() shows the same value without
		// flagging a change that was never made.
		if (!frm.doc.policy_module_select && frm.doc.module_policies?.length) {
			frm.doc.policy_module_select = frm.doc.module_policies[0].module;
			frm.refresh_field("policy_module_select");
		}
		_load_selected_module_policy(frm);
	},

	policy_module_select(frm) {
		_load_selected_module_policy(frm);
	},

	// Debounced writes on every keystroke would create a huge number of
	// child-row updates for no reason — writing back on blur (leaving
	// the field) is the real moment the person is "done with this box
	// for now", same moment a switch to another module or an actual
	// form Save would also need the current text captured.
	policy_strict_text(frm) {
		_write_selected_module_policy(frm);
	},
	policy_warning_text(frm) {
		_write_selected_module_policy(frm);
	},
});

function _find_selected_row(frm) {
	const module = frm.doc.policy_module_select;
	if (!module) return null;
	return (frm.doc.module_policies || []).find((row) => row.module === module) || null;
}

/** Same non-dirtying pattern as refresh()'s own default-module-select
 *  fix — this only ever re-displays a row's already-saved text, never a
 *  real edit on its own, so it must never be what makes "Not Saved"
 *  appear. Setting frm.doc directly (not frm.set_value) also means this
 *  doesn't re-trigger the policy_strict_text/policy_warning_text change
 *  handlers below — which would otherwise immediately write the exact
 *  same values right back, a pointless (if harmless) redundant update
 *  on every module switch. */
function _load_selected_module_policy(frm) {
	const row = _find_selected_row(frm);
	frm.doc.policy_strict_text = row?.strict_policy || "";
	frm.doc.policy_warning_text = row?.warning_policy || "";
	frm.refresh_field("policy_strict_text");
	frm.refresh_field("policy_warning_text");
}

function _write_selected_module_policy(frm) {
	const row = _find_selected_row(frm);
	if (!row) return;
	frappe.model.set_value(row.doctype, row.name, "strict_policy", frm.doc.policy_strict_text || "");
	frappe.model.set_value(row.doctype, row.name, "warning_policy", frm.doc.policy_warning_text || "");
}
