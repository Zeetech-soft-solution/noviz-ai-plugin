// Copyright (c) 2026, Zeetech Soft Solution and contributors
// For license information, please see license.txt

// Real UX simplification, per explicit request: the earlier design (a
// separate module dropdown + two big boxes duplicating the grid's own
// data) was reworked back down to ONE editing surface — the grid itself
// (module_policies), edited inline, cell by cell. All 11 real modules are
// pre-seeded on install (install.py's own _seed_module_policy_rows) and
// the field is locked to that fixed set (_lock_module_policies_rows
// below), so there is nothing to insert or delete — only ever editing an
// already-existing row's own text.
//
// The one real gap plain Frappe grid styling leaves: a Small Text
// column's STATIC (not-currently-being-edited) cell is Frappe's own
// real ".static-area.ellipsis" — single line, truncated with "..." —
// which would hide most of a real multi-line policy at a glance. This
// overrides just that class, scoped to this one grid, so the real text
// is readable without having to click into the cell first — a pure CSS
// change, no data/behavior difference. (Also affects the Module column's
// own static cell, harmlessly — those values are always a single short
// word and never wrap regardless.)
frappe.ui.form.on("Noviz AI Settings", {
	refresh(frm) {
		_widen_policy_columns(frm);
		_lock_module_policies_rows(frm);
	},
});

// Real bug found live: "cannot_add_rows"/"cannot_delete_rows" set in the
// DocType JSON are silently DROPPED — DocField's own real database
// schema has no column for either property, so bench migrate's sync
// step never persists them (confirmed live: a direct DocField query for
// either name fails with "Field not permitted in query", meaning the
// column genuinely doesn't exist). grid.js's own real client-side check
// (frappe/public/js/frappe/form/grid.js) ALSO accepts a plain runtime
// property directly on the grid object itself — that path works, this
// sets it there instead. All 11 real modules are pre-seeded on install
// (install.py's _seed_module_policy_rows) and this doctype has no create
// permission on the child rows beyond that seed, so locking the row set
// here matches what was already true underneath — just removes the
// "Add Row"/per-row delete affordances that implied otherwise.
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
