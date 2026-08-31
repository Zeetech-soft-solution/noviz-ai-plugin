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
#
# ── THE ERPNEXT "REPORT PDF" STANDARD (what render_table_pdf's named-
#    report path deliberately matches) ────────────────────────────────
# ERPNext's own Query Report PDF (Menu -> Print / Export -> PDF ->
# frappe.utils.print_format.report_to_pdf) is:
#   1. CLIENT-SIDE: the DataTable grid is serialised to an HTML <table>,
#      each column carrying label / fieldtype / width from the report's
#      own get_columns().
#   2. Per-fieldtype formatting applied there: Currency -> grouped digits
#      + 2 decimals, right-aligned; Int -> grouped integer; Date ->
#      dd-mm-yyyy; Link/Data -> plain text.
#   3. HTML + a small-font print stylesheet POSTed to report_to_pdf,
#      which just wraps it in get_pdf() -> wkhtmltopdf, orientation
#      Landscape (the default for every query report regardless of
#      width), page-size A4.
#   4. Wide reports (General Ledger, AR/AP Summary): ERPNext does NOT
#      shrink to fit — it lets the table overflow and expects the user
#      to hide columns (Menu -> Pick Columns) or export to Excel.
# We reproduce 1-3 exactly (real column meta, fieldtype formatting +
# right-align, Landscape A4, wkhtmltopdf). For 4 there is no column
# picker in chat, so instead of overflowing we auto-fit: table-layout
# fixed at 100% width, the <colgroup> widths as ratios, the body font
# steps down past ~12 columns, and any cell that still doesn't fit WRAPS
# (never clips). entity_query / aggregate_query PDFs are NOT reports and
# keep the plain original render.
import frappe


def _escape(value) -> str:
	if value is None:
		return ""
	return frappe.utils.escape_html(str(value))


_NUMERIC_FIELDTYPES = {"Currency", "Float", "Int", "Percent"}


def _fmt_cell(value, fieldtype: str) -> str:
	"""Same read as ERPNext's own grid: a Currency/Float value shows with
	thousands separators and 2 decimals (right-aligned via the .num class
	below), an Int as a plain integer, everything else as-is. No currency
	symbol — the report carries its own `currency` column and mixing a
	symbol in would only add width."""
	if value is None or value == "":
		return ""
	if fieldtype in ("Currency", "Float", "Percent"):
		try:
			return f"{float(value):,.2f}"
		except (TypeError, ValueError):
			return _escape(value)
	if fieldtype == "Int":
		try:
			return f"{int(value):,}"
		except (TypeError, ValueError):
			return _escape(value)
	return _escape(value)


def render_table_pdf(title: str, columns: list, rows: list, orientation: str = None) -> bytes:
	"""columns: [{"key": <native fieldname>, "label": <display label>,
	             "fieldtype"?: <ERPNext fieldtype>, "width"?: <px>}, ...]
	   — when a named report is the source, these are ERPNext's OWN column
	   definitions (real labels like "0-30", real Currency/Link fieldtypes,
	   real widths), so the PDF matches how the report looks in the desk.
	rows: real fetched records (dicts) keyed by the same native fieldnames.

	orientation: "Portrait" | "Landscape" (relay sets it per filter family);
	None -> Landscape, matching ERPNext's own report PDF dialog.

	Kept reusable (not inlined into the whitelisted endpoint) so a future
	"email this report" feature calls the exact same builder.
	"""
	def is_num(c):
		return c.get("fieldtype") in _NUMERIC_FIELDTYPES

	# Column metadata (fieldtype / width) is only present when the source
	# is a NAMED REPORT — the relay hands it ERPNext's own column defs.
	# entity_query / aggregate_query PDFs pass plain {key,label} only, and
	# keep the exact original render (auto layout, word-break wrap) — this
	# change is scoped to the named-report path.
	has_meta = any(c.get("fieldtype") or c.get("width") for c in columns)

	pdf_options = None
	if has_meta:
		# ── the ERPNext report-PDF standard (see the header comment) ────
		# A4, orientation from the relay (Landscape default for reports),
		# a plain auto-layout <table> — wkhtmltopdf's smart-shrinking
		# (on by default in get_pdf) scales a wide table to fit the page,
		# which is exactly what Frappe's own report_to_pdf relies on. NO
		# table-layout:fixed, NO forced width, NO custom page size — those
		# fight the smart-shrink. Font steps down at the same thresholds
		# Frappe's own print_template uses (4pt past 20 columns), numbers
		# right-aligned, a real column's width becomes its min-width.
		n = len(columns)
		font_px = 4 if n > 20 else 6 if n > 12 else 8
		th_cells = []
		for c in columns:
			w = f' style="min-width:{int(c["width"])}px"' if c.get("width") else ""
			th_cells.append(f'<th class="{"num" if is_num(c) else ""}"{w}>{_escape(c["label"])}</th>')
		header_html = "".join(th_cells)
		body_rows = [
			"<tr>" + "".join(
				f'<td class="{"num" if is_num(c) else ""}">{_fmt_cell(row.get(c["key"]), c.get("fieldtype"))}</td>'
				for c in columns
			) + "</tr>"
			for row in rows
		]
		colgroup = ""
		pdf_options = {"orientation": orientation if orientation in ("Portrait", "Landscape") else "Landscape", "page-size": "A4"}
		style = f"""
			body {{ font-family: Helvetica, Arial, sans-serif; font-size: {font_px}px; color: #222; }}
			h2 {{ margin: 0 0 4px 0; font-size: 14px; }}
			.noviz-report-meta {{ color: #666; margin-bottom: 8px; font-size: 8px; }}
			table {{ border-collapse: collapse; }}
			th, td {{
				border: 1px solid #ccc; padding: 2px 4px; vertical-align: top;
				word-break: break-word; overflow-wrap: anywhere;
			}}
			td.num, th.num {{ text-align: right; white-space: nowrap; }}
			th {{ background: #f2f2f2; font-weight: bold; text-align: left; }}
			tr:nth-child(even) td {{ background: #fafafa; }}
		"""
	else:
		colgroup = ""
		header_html = "".join(f"<th>{_escape(c['label'])}</th>" for c in columns)
		body_rows = [
			"<tr>" + "".join(f"<td>{_escape(row.get(c['key']))}</td>" for c in columns) + "</tr>"
			for row in rows
		]
		style = """
			body { font-family: Helvetica, Arial, sans-serif; font-size: 9px; color: #222; }
			h2 { margin: 0 0 4px 0; font-size: 16px; }
			.noviz-report-meta { color: #666; margin-bottom: 12px; font-size: 9px; }
			table { width: 100%; border-collapse: collapse; }
			th, td { border: 1px solid #ccc; padding: 4px 6px; text-align: left; word-break: break-word; }
			th { background: #f2f2f2; font-weight: bold; }
			tr:nth-child(even) td { background: #fafafa; }
		"""

	html = f"""
	<html>
	<head><style>{style}</style></head>
	<body>
		<h2>{_escape(title)}</h2>
		<div class="noviz-report-meta">{len(rows)} row(s) — generated {frappe.utils.now()}</div>
		<table>
			{colgroup}
			<thead><tr>{header_html}</tr></thead>
			<tbody>{"".join(body_rows)}</tbody>
		</table>
	</body>
	</html>
	"""
	from frappe.utils.pdf import get_pdf

	if pdf_options is None:
		# entity_query / aggregate_query — unchanged: A4, orientation from
		# the relay's filter family (Landscape default).
		if orientation not in ("Portrait", "Landscape"):
			orientation = "Landscape"
		pdf_options = {"orientation": orientation, "page-size": "A4"}
	return get_pdf(html, options=pdf_options)


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


def _report_column_meta(message: dict) -> list:
	"""ERPNext's own column definitions for a query report, normalised to
	the shape render_table_pdf wants: {key, label, fieldtype, width}. The
	report's `columns` come as {fieldname,label,fieldtype,width} dicts, or
	(older reports) plain "fieldname:Fieldtype/Options:width" strings —
	handle both. Returns [] when there's nothing usable, so the caller
	falls back to columns_from_rows()."""
	cols = (message or {}).get("columns") or []
	out = []
	for c in cols:
		if isinstance(c, dict):
			key = c.get("fieldname") or c.get("label")
			if not key:
				continue
			out.append({
				"key": key,
				"label": c.get("label") or key,
				"fieldtype": c.get("fieldtype"),
				"width": c.get("width"),
			})
		elif isinstance(c, str) and c:
			parts = c.split(":")
			key = parts[0]
			ftype = parts[1].split("/")[0] if len(parts) > 1 and parts[1] else None
			width = None
			if len(parts) > 2 and str(parts[2]).isdigit():
				width = int(parts[2])
			out.append({"key": key, "label": key.replace("_", " ").title(), "fieldtype": ftype, "width": width})
	return out


def _tenant_saved_columns(report_name: str) -> list:
	"""If someone on this ERPNext site has trimmed this standard report in
	the desk (per-column "Remove Column", then Menu -> Save), Frappe stored
	that as a Custom Report row — is_standard "No", reference_report set to
	this standard report, and json.columns holding the visible subset.
	Return that subset's real fieldnames (most-recently-saved wins), or []
	if nobody's trimmed it. We then narrow the PDF to exactly those
	columns — the report "template" the tenant already defined for
	themselves, honoured without them having to re-pick it in chat."""
	name = frappe.db.get_value(
		"Report",
		{"reference_report": report_name, "is_standard": "No", "report_type": "Custom Report", "disabled": 0},
		"name",
		order_by="modified desc",
	)
	if not name:
		return []
	raw = frappe.db.get_value("Report", name, "json")
	if not raw:
		return []
	try:
		saved = frappe.parse_json(raw)
	except Exception:
		return []
	wanted = []
	for c in (saved.get("columns") or []):
		if isinstance(c, dict):
			fn = c.get("fieldname") or c.get("id")
			if fn:
				wanted.append(fn)
		elif isinstance(c, str) and c:
			wanted.append(c.split(":")[0])
	return wanted


def run_named_report(report_name: str, filters: dict):
	"""Real ERPNext named report (General Ledger, Profit and Loss, ...) —
	frappe.desk.query_report.run() is the exact same real, whitelisted
	function ERPNext's own desk Query Report screen calls, real
	permission checks (raises frappe.PermissionError for a report this
	session's real role can't access) included.

	Returns (rows, columns): rows are the normalised dict rows; columns
	are ERPNext's OWN column defs ({key,label,fieldtype,width}) so
	generate_report_pdf renders the PDF the way the report looks in the
	desk (real labels like "0-30", Currency right-align, real widths). If
	the tenant has a SAVED trimmed version of this report (a Custom Report
	row), columns is narrowed to that saved subset. columns is [] only
	when the report exposes no usable metadata — caller then falls back
	to columns_from_rows()."""
	from frappe.desk.query_report import run as run_query_report

	message = run_query_report(report_name=report_name, filters=filters or {})
	from noviz_ai.dispatcher import _normalize_report_result

	rows = _normalize_report_result(message)
	columns = _report_column_meta(message)
	if columns:
		saved = _tenant_saved_columns(report_name)
		if saved:
			narrowed = [c for c in columns if c["key"] in saved]
			if narrowed:
				columns = narrowed
	return rows, columns


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


def run_aggregate_query(doctype: str, group_by_field: str, metrics: list, filters, limit=0) -> list:
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
		# 0 = no cap (the "complete" PDF); a positive `limit` scopes it to
		# the same rows on screen for the "this page" PDF.
		limit_page_length=max(0, int(limit or 0)),
		as_list=False,
	)
	# frappe.get_list's own aggregate columns already come back as plain
	# numbers keyed by their alias — nothing further to reshape.
	return [dict(r) for r in rows]


def run_joined_aggregate(base_doctype: str, link_fields: list, group_by_field: str, metrics: list, filters, limit=0) -> list:
	"""run_aggregate_query, plus a field pulled in from a LINKED doctype —
	a customer's phone (Customer.mobile_no) next to their overdue total,
	which a single-doctype GROUP BY can't reach. No hand SQL: get_list
	takes `"<link fieldname>.<target fieldname>"` in `fields` and Frappe 16
	auto-joins the linked doctype (a Link field is 1:1 from the base, so no
	fan-out). DocPerm respected exactly as get_list always does.

	link_fields: ["customer.mobile_no", ...] — the relay's buildReportSpec
	validated each link fieldname / target against the real schema.
	metrics: same [{"op","field","label"}] shape as run_aggregate_query.
	limit: 0 = every group ("total" PDF); a positive value scopes it to the
	same rows on screen ("this page" PDF).
	Returns the SAME key shape run_aggregate_query gives.
	"""
	if not frappe.has_permission(base_doctype, "read"):
		frappe.throw(f"You do not have permission to read {base_doctype} records.", frappe.PermissionError)

	select_fields = [group_by_field, *[lf for lf in (link_fields or []) if isinstance(lf, str) and "." in lf]]
	metric_aliases = []
	for m in metrics:
		fn = _AGGREGATE_SQL.get(m["op"])
		if not fn:
			frappe.throw(f'Unsupported aggregate op "{m["op"]}".')
		alias = f"{m['op']}_{m['field']}"
		metric_aliases.append(alias)
		select_fields.append({fn: m["field"], "as": alias})

	rows = frappe.get_list(
		base_doctype,
		filters=filters,
		fields=select_fields,
		group_by=group_by_field,
		order_by=f"{metric_aliases[0]} desc" if metric_aliases else None,
		limit_page_length=max(0, int(limit or 0)),
	)
	return [dict(r) for r in rows]


def run_aggregate_page(base_doctype: str, link_fields: list, group_by_field: str, metrics: list, filters, page_index=1, page_count=20) -> list:
	"""ONE page of run_joined_aggregate's result — the exact same query
	(same filters, same group_by, same deterministic sort: first metric,
	descending) sliced to page `page_index` (1-based) of `page_count`
	groups. The relay's on-screen table shows page N; "Download this page"
	sends that same page_index / page_count here and gets a PDF of exactly
	those rows. link_fields carries a linked column (a customer's phone)
	just as run_joined_aggregate does; pass [] / None when there isn't one.
	"""
	if not frappe.has_permission(base_doctype, "read"):
		frappe.throw(f"You do not have permission to read {base_doctype} records.", frappe.PermissionError)

	select_fields = [group_by_field, *[lf for lf in (link_fields or []) if isinstance(lf, str) and "." in lf]]
	metric_aliases = []
	for m in metrics:
		fn = _AGGREGATE_SQL.get(m["op"])
		if not fn:
			frappe.throw(f'Unsupported aggregate op "{m["op"]}".')
		alias = f"{m['op']}_{m['field']}"
		metric_aliases.append(alias)
		select_fields.append({fn: m["field"], "as": alias})

	size = max(1, int(page_count or 20))
	start = max(0, (max(1, int(page_index or 1)) - 1) * size)
	rows = frappe.get_list(
		base_doctype,
		filters=filters,
		fields=select_fields,
		group_by=group_by_field,
		order_by=f"{metric_aliases[0]} desc" if metric_aliases else None,
		limit_start=start,
		limit_page_length=size,
	)
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
