# Real, in-process tabular PDF rendering — the LOCAL half of
# report.generate's real architecture (see relayReasoningEngine.ts's own
# buildReportSpec doc comment for the full design/"why"). Deliberately
# NOT a new pip dependency: frappe.utils.pdf.get_pdf() is ERPNext's own
# real, already-present HTML-to-PDF pipeline — the EXACT SAME one
# frappe.utils.print_format.download_pdf (api.py's own appendDocumentLink
# counterpart) already uses successfully for a single document's real
# print PDF. Building a plain HTML table and handing it to that function
# reuses infrastructure this box already has working, rather than adding
# a second, independent PDF-rendering path (fpdf2, reportlab, ...) this
# thin plugin would then have to maintain forever.
import frappe


def _escape(value) -> str:
	if value is None:
		return ""
	return frappe.utils.escape_html(str(value))


# A table with more than this many columns is cramped on portrait A4 —
# those default to landscape unless the caller (relay spec) says otherwise.
_LANDSCAPE_COLUMN_THRESHOLD = 6


def render_table_pdf(title: str, columns: list, rows: list, orientation: str = None) -> bytes:
	"""columns: [{"key": "<real native fieldname>", "label": "<display label>"}, ...]
	rows: real fetched records (dicts) — one per row, keyed by the SAME
	native fieldnames `columns` names.

	orientation: "Portrait" | "Landscape". None (the default) auto-picks —
	landscape once a report has more than _LANDSCAPE_COLUMN_THRESHOLD
	columns so a wide register/financial report isn't cut off the page.
	An explicit value from the spec always wins.

	Kept as a real, reusable function (not inlined into one whitelisted
	endpoint) on purpose — the same real, direct user ask this session
	also raised: "when we send email the same we need to attach and
	send". Any future "email this report" feature calls this exact
	function too (frappe.sendmail's own `attachments` parameter takes
	{"fname":..., "fcontent":...} — this function's own return value
	slots straight in), never a second PDF-building implementation.
	"""
	header_html = "".join(f"<th>{_escape(c['label'])}</th>" for c in columns)
	body_rows = []
	for row in rows:
		cells = "".join(f"<td>{_escape(row.get(c['key']))}</td>" for c in columns)
		body_rows.append(f"<tr>{cells}</tr>")

	html = f"""
	<html>
	<head>
		<style>
			body {{ font-family: Helvetica, Arial, sans-serif; font-size: 9px; color: #222; }}
			h2 {{ margin: 0 0 4px 0; font-size: 16px; }}
			.noviz-report-meta {{ color: #666; margin-bottom: 12px; font-size: 9px; }}
			table {{ width: 100%; border-collapse: collapse; }}
			th, td {{ border: 1px solid #ccc; padding: 4px 6px; text-align: left; word-break: break-word; }}
			th {{ background: #f2f2f2; font-weight: bold; }}
			tr:nth-child(even) td {{ background: #fafafa; }}
		</style>
	</head>
	<body>
		<h2>{_escape(title)}</h2>
		<div class="noviz-report-meta">{len(rows)} row(s) — generated {frappe.utils.now()}</div>
		<table>
			<thead><tr>{header_html}</tr></thead>
			<tbody>{"".join(body_rows)}</tbody>
		</table>
	</body>
	</html>
	"""
	from frappe.utils.pdf import get_pdf

	if orientation not in ("Portrait", "Landscape"):
		orientation = "Landscape" if len(columns) > _LANDSCAPE_COLUMN_THRESHOLD else "Portrait"
	return get_pdf(html, options={"orientation": orientation, "page-size": "A4"})


# Real, honest ceiling — same order of magnitude as reportGenerator.ts's
# own REPORT_ROW_CAP (10,000, local engine). This fetch runs entirely
# in-process against ERPNext (no chat-turn latency to worry about the
# way the relay's own now-removed page-by-page design did), so a single,
# real, generous cap is enough — no pagination state needed at all, just
# one real, direct frappe.get_list() call with a high limit.
REPORT_ROW_CAP = 10000


def fetch_entity_rows(doctype: str, fields: list, filters, limit=None, order_by=None) -> list:
	"""Real permission check first (same explicit discipline dispatcher.py's
	own get_list branch already uses) — this is the ONLY place a report's
	actual rows are ever fetched, always as the real logged-in person's
	own session, ERPNext's own DocPerm governing exactly what comes back.

	`limit`/`order_by` are honored when the relay's spec carries them —
	"Download PDF" for a bounded ask ("the last 37 quotations") exports
	exactly those 37, in that order. Absent (a plain unfiltered list) it
	stays "every row" up to REPORT_ROW_CAP, unordered."""
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(f"You do not have permission to read {doctype} records.", frappe.PermissionError)
	page_length = REPORT_ROW_CAP
	try:
		if limit is not None:
			page_length = max(1, min(int(limit), REPORT_ROW_CAP))
	except (TypeError, ValueError):
		page_length = REPORT_ROW_CAP
	rows = frappe.get_list(
		doctype,
		fields=fields or ["name"],
		filters=filters,
		order_by=order_by or None,
		limit_page_length=page_length,
	)
	return [dict(r) for r in rows]


def run_named_report(report_name: str, filters: dict) -> list:
	"""Real ERPNext named report (General Ledger, Profit and Loss, ...) —
	frappe.desk.query_report.run() is the exact same real, whitelisted
	function ERPNext's own desk Query Report screen calls, real
	permission checks (raises frappe.PermissionError for a report this
	session's real role can't access) included. Shared by dispatcher.py's
	own (now relay-unreachable, but still real/callable) run_report kind
	and generate_report_pdf below — one real implementation, not two."""
	from frappe.desk.query_report import run as run_query_report

	message = run_query_report(report_name=report_name, filters=filters or {})
	from noviz_ai.dispatcher import _normalize_report_result

	return _normalize_report_result(message)


# The complete, unpaginated version of analytics.aggregate/
# database_engine.execute_query's own groupBy result (that one is capped
# to 20 groups per reply — see relayReasoningEngine.ts's own
# GROUPS_PAGE_COUNT). Runs a single native SQL GROUP BY directly against
# ERPNext via frappe.get_list's own group_by/aggregate-function support —
# not a fetch-every-row-then-sum-in-Python loop, which would be slower
# and exactly the kind of large-data-over-the-wire pattern this whole
# report.generate architecture exists to avoid (see this file's own
# render_table_pdf doc comment for the zero-round-trip design).
#
# A raw SQL string like "SUM(`field`) as `alias`" in `fields` is rejected
# outright by this Frappe version's own query builder — "SQL functions
# are not allowed as strings in SELECT... Use dict syntax like
# {'COUNT': '*'} instead" (frappe/database/query.py's own
# _validate_select_field/SQLFunctionParser). The supported shape is a
# dict: {"SUM": "field_name", "as": "alias"} — see
# SQLFunctionParser.parse_function's own FUNCTION_MAPPING (COUNT/SUM/AVG/
# MAX/MIN, all uppercase).
_AGGREGATE_SQL = {"sum": "SUM", "avg": "AVG", "count": "COUNT", "min": "MIN", "max": "MAX"}


def run_aggregate_query(doctype: str, group_by_field: str, metrics: list, filters) -> list:
	"""metrics: [{"op": "sum"|"avg"|"count"|"min"|"max", "field": "<real native fieldname>", "label": "..."}]
	(the relay's own buildReportSpec already validated op/field against
	this entity's real schema — same trust boundary as fetch_entity_rows'
	own real frappe.has_permission check below, applied to whatever this
	ALREADY-AUTHENTICATED session can actually see).

	Returns one dict per real group, keyed `group_by_field` for the group
	value and `"<op>_<field>"` for each metric — the SAME key shape
	buildReportSpec's own `columns` already uses, so render_table_pdf's
	plain `row.get(c['key'])` lookup needs no special-casing here.
	Sorted by the FIRST metric's own value, descending — same real,
	deterministic "who/what has the most" answer analytics.aggregate's
	own groups already give, never left to chance query-planner order.
	"""
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(f"You do not have permission to read {doctype} records.", frappe.PermissionError)

	select_fields = [group_by_field]
	metric_aliases = []
	for m in metrics:
		op = m["op"]
		sql_fn = _AGGREGATE_SQL.get(op)
		if not sql_fn:
			frappe.throw(f'Unsupported aggregate op "{op}".')
		alias = f"{op}_{m['field']}"
		metric_aliases.append(alias)
		select_fields.append({sql_fn: m["field"], "as": alias})

	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=select_fields,
		group_by=group_by_field,
		# Real gap found live: a BACKTICK-quoted alias here is parsed as
		# `tabDocType`.`fieldname` table.field notation instead of a
		# registered function alias (see DatabaseQuery's own
		# _validate_and_parse_field_for_clause — the backtick check runs
		# BEFORE the function_aliases check) — plain, unquoted is correct.
		order_by=f"{metric_aliases[0]} desc",
		limit_page_length=0,  # real, explicit "no cap" — the whole point of this feature over the paginated tool
		as_list=False,
	)
	# frappe.get_list's own aggregate columns already come back as plain
	# numbers keyed by their alias — nothing further to reshape.
	return [dict(r) for r in rows]


def columns_from_rows(rows: list, requested: list = None) -> list:
	"""Same real default-columns behavior reportGenerator.ts's own
	columnsFromRows() gives the local product — the union of every real
	key seen across all rows (a named report's own output shape isn't
	known ahead of a real fetch, unlike entity_query's canonical field
	list). `requested` (a caller-given subset of native-ish keys) narrows
	when every one of them is real; an empty/no-match request falls back
	to the full set, same graceful "never an empty PDF over a typo"
	degrade every other columns path in this app already uses."""
	keys: list = []
	for row in rows:
		for k in row.keys():
			if k not in keys:
				keys.append(k)
	available = [{"key": k, "label": k.replace("_", " ").title()} for k in keys]
	if not requested:
		return available
	by_key = {c["key"]: c for c in available}
	narrowed = [by_key[k] for k in requested if k in by_key]
	return narrowed or available
