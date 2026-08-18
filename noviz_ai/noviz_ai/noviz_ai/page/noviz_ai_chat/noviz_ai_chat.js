// Native desk chat page. This is a thin UI shell only — every real
// decision (what tool to call, what data means, how to phrase the
// answer, and now how a result is RENDERED) happens on the private
// central relay; this file's whole job is collecting a prompt, calling
// the plugin's one whitelisted method, and injecting whatever HTML
// comes back. No entity/tool knowledge here, and — as of this pass —
// no table-building logic here either: the relay sends REAL pre-
// rendered HTML (relayReasoningEngine.ts reusing the same
// rendererRegistry/tableRenderer.ts the single-tenant product's own
// chat already relies on), this file just injects it.
frappe.pages['noviz-ai-chat'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Noviz AI Chat',
		single_column: true,
	});

	new NovizAIChat(page);
};

if (!document.getElementById('noviz-ai-chat-style')) {
	$(`<style id="noviz-ai-chat-style">
		#page-noviz-ai-chat .container { max-width: 100%; }
		#page-noviz-ai-chat .page-head, #page-noviz-ai-chat .page-title { display: none; }

		.noviz-ai-main { display: flex; flex-direction: column; height: calc(100vh - 120px); width: 100%; }
		.noviz-ai-header {
			display: flex; align-items: center; gap: 10px; padding-bottom: 14px;
			border-bottom: 1px solid var(--border-color, #d1d8dd); margin-bottom: 14px;
		}
		.noviz-ai-logo {
			width: 32px; height: 32px; border-radius: 8px; background: #1e7a5c;
			color: #fff; display: flex; align-items: center; justify-content: center;
			font-weight: 700; font-size: 15px; flex-shrink: 0;
		}
		.noviz-ai-header-text h3 { margin: 0; font-size: 16px; }
		.noviz-ai-header-text .noviz-ai-subtitle { font-size: 12px; color: var(--text-muted, #8d99a6); }

		.noviz-ai-chat-log { flex: 1; overflow-y: auto; padding: 4px 0; }
		.noviz-ai-chat-msg {
			padding: 10px 14px; border-radius: 10px; margin-bottom: 12px;
			white-space: pre-wrap; box-shadow: 0 1px 2px rgba(0,0,0,0.06);
		}
		/* Same side/alignment as the response — matching Pro's own layout
		   (a plain left-aligned bar for the user's own question, not a
		   right-aligned chat-bubble split). */
		.noviz-ai-chat-msg-user {
			background: var(--control-bg, #f4f5f6); font-weight: 600; max-width: 92%;
		}
		.noviz-ai-chat-msg-assistant {
			background: var(--fg-color, #fff); border: 1px solid var(--border-color, #e2e8e4);
			max-width: 92%;
		}
		.noviz-ai-chat-msg-assistant p:last-child { margin-bottom: 0; }

		/* Matches the class names rendererRegistry's own tableRenderer.ts/
		   cardsRenderer.ts emit — this page has no access to Pro's own
		   bundled CSS, so the same visual language is redefined here,
		   scoped to just this page. */
		.noviz-ai-chat-msg-assistant .erp-agent-report { margin-top: 10px; }
		.noviz-ai-chat-msg-assistant .erp-agent-table-scroll { overflow-x: auto; }
		.noviz-ai-chat-msg-assistant .erp-agent-table { border-collapse: collapse; width: 100%; font-size: 13px; }
		.noviz-ai-chat-msg-assistant .erp-agent-table th,
		.noviz-ai-chat-msg-assistant .erp-agent-table td { border: 1px solid var(--border-color, #d1d8dd); padding: 6px 10px; text-align: left; white-space: nowrap; }
		.noviz-ai-chat-msg-assistant .erp-agent-table th { background: var(--control-bg, #f4f5f6); font-weight: 600; }
		.noviz-ai-chat-msg-assistant .erp-agent-row-highlight { background: #fff8e1; }
		.noviz-ai-chat-msg-assistant .erp-agent-row-id-link {
			background: none; border: none; padding: 0; color: #1e7a5c; text-decoration: underline;
			cursor: pointer; font-size: inherit; font-weight: 600;
		}
		.noviz-ai-chat-msg-assistant .erp-agent-empty { color: var(--text-muted, #8d99a6); font-style: italic; }
		/* Real bug found live 2026-08-18: this styled ".erp-agent-cards"
		   (plural) — a class cardsRenderer.ts never actually emits. The
		   real single-record detail view is ".erp-agent-card" (singular,
		   one per record) containing ".erp-agent-card-row"/"-label"/
		   "-value" — those went completely unstyled (plain stacked divs,
		   no border/spacing), which is genuinely what "so many cards, so
		   many icons" was describing: not a structure problem (the HTML
		   is the SAME cardsRenderer.ts Pro's own chat renders), a missing-
		   CSS one. Ported directly from Pro's own styles.css so a single
		   quotation/customer/etc. record looks exactly like it does there. */
		.noviz-ai-chat-msg-assistant .erp-agent-card {
			border: 1px solid var(--border-color, #d1d8dd); border-radius: 12px;
			background: var(--fg-color, #fff); box-shadow: 0 1px 3px rgba(0,0,0,0.04); overflow: hidden;
		}
		.noviz-ai-chat-msg-assistant .erp-agent-card + .erp-agent-card { margin-top: 10px; }
		.noviz-ai-chat-msg-assistant .erp-agent-card-row {
			display: flex; gap: 16px; padding: 9px 14px; border-top: 1px solid var(--border-color, #d1d8dd);
		}
		.noviz-ai-chat-msg-assistant .erp-agent-card-row:first-child { border-top: none; }
		.noviz-ai-chat-msg-assistant .erp-agent-card-label {
			flex: 0 0 160px; color: var(--text-muted, #8d99a6); font-weight: 600; font-size: 11.5px;
			letter-spacing: 0.02em; text-transform: uppercase; padding-top: 1px;
		}
		.noviz-ai-chat-msg-assistant .erp-agent-card-value { flex: 1; font-size: 13px; word-break: break-word; }
		.noviz-ai-chat-msg-assistant .erp-agent-next-steps { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
		.noviz-ai-chat-msg-assistant button.erp-agent-next-step:not(.erp-agent-row-id-link) {
			background: var(--control-bg, #f4f5f6); border: 1px solid var(--border-color, #d1d8dd);
			border-radius: 6px; padding: 5px 10px; font-size: 12px; cursor: pointer;
		}
		/* Per-message export — placed right below the table/card itself,
		   matching Pro's own "Export to PDF" placement under each result,
		   not just a single page-level button. Buttons sit side-by-side
		   (not stacked full-width), matching Pro's own layout when both a
		   print export AND a real document download are available for the
		   same reply. */
		.noviz-ai-msg-export {
			margin-top: 10px; margin-right: 8px; background: none; border: 1px solid var(--border-color, #d1d8dd);
			border-radius: 6px; padding: 5px 10px; font-size: 12px; cursor: pointer; color: #1e7a5c;
			display: inline-block; text-decoration: none;
		}
		/* The REAL ERPNext-generated PDF (frappe.utils.print_format.
		   download_pdf) — filled/primary so it reads as the "real
		   document" action, distinct from the plain browser-print export
		   next to it. */
		.noviz-ai-doc-download {
			background: #1e7a5c; border-color: #1e7a5c; color: #fff; font-weight: 600;
		}

		.noviz-ai-chat-input-row { display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid var(--border-color, #d1d8dd); }
		.noviz-ai-chat-input { flex: 1; }

		@media print {
			body * { visibility: hidden; }
			/* Printing one message marks it with .noviz-ai-print-this (its
			   own per-message Export PDF button, see printOnly()'s own doc
			   comment) — only the marked element and its children become
			   visible. */
			.noviz-ai-print-this, .noviz-ai-print-this * { visibility: visible; }
			.noviz-ai-print-this { position: absolute; top: 0; left: 0; width: 100%; height: auto; }
			.noviz-ai-msg-export { display: none; }
		}
	</style>`).appendTo('head');
}

class NovizAIChat {
	constructor(page) {
		this.page = page;
		this.sending = false;
		// Real conversation memory (matching Pro's own per-session chat
		// memory) — the relay's own "turnId" from the last final reply,
		// sent back as "previous_turn_id" on the NEXT message so the
		// relay can load that conversation's history and continue it
		// instead of starting fresh every message. Scoped to this page
		// instance only — a reload is a genuinely new conversation, same
		// session boundary Pro's own memory uses.
		this.lastTurnId = null;
		this.render();
	}

	render() {
		this.$container = $(`
			<div class="noviz-ai-main">
				<div class="noviz-ai-header">
					<div class="noviz-ai-logo">N</div>
					<div class="noviz-ai-header-text">
						<h3>${__('Noviz AI')}</h3>
						<div class="noviz-ai-subtitle">${__('ERP Assistant for')} ${frappe.defaults.get_default('company') || frappe.sys_defaults.company || ''}</div>
					</div>
				</div>
				<div class="noviz-ai-chat-log"></div>
				<div class="noviz-ai-chat-input-row">
					<input type="text" class="form-control noviz-ai-chat-input"
						placeholder="${__('Ask about your ERPNext data...')}" />
					<button class="btn btn-primary btn-sm noviz-ai-chat-send">${__('Send')}</button>
				</div>
			</div>
		`).appendTo(this.page.body);

		this.$log = this.$container.find('.noviz-ai-chat-log');
		this.$input = this.$container.find('.noviz-ai-chat-input');
		this.$sendBtn = this.$container.find('.noviz-ai-chat-send');

		this.$sendBtn.on('click', () => this.send());
		this.$input.on('keydown', (e) => {
			if (e.key === 'Enter' && !this.sending) this.send();
		});

		// A row's own id, or a next_steps action button, inside the
		// injected HTML is a real clickable prompt-sender — same
		// data-action -> click delegation ResponseView.tsx wires for
		// Pro's own chat. Delegated on the log itself since these
		// buttons come from server-rendered HTML injected after the
		// fact, not elements this file created directly.
		this.$log.on('click', '.erp-agent-next-step[data-action]', (e) => {
			if (this.sending) return;
			this.send($(e.currentTarget).attr('data-action'));
		});
		// Per-message export button, appended in addMessage() below —
		// delegated the same way since it's added to server-rendered
		// content after the fact. Bound to ".noviz-ai-print-export"
		// specifically, NOT the shared ".noviz-ai-msg-export" visual
		// class — real bug found live: the Download PDF link (real
		// ERPNext PDF, appendDocumentLink below) also carries
		// ".noviz-ai-msg-export" purely for matching button styling,
		// so binding this handler to that class made clicking Download
		// PDF ALSO trigger window.print() on top of its own real
		// navigation — the user saw "print the details" instead of the
		// actual document PDF.
		this.$log.on('click', '.noviz-ai-print-export', (e) => {
			this.printOnly($(e.currentTarget).closest('.noviz-ai-chat-msg'));
		});

		this.addMessage(
			'assistant',
			__('Hi! Ask me anything about your ERPNext data — quotations, sales orders, or customers.')
		);

		// Real first-time-setup screen — before this existed, an
		// unconfigured site rendered this exact chat box anyway, and the
		// FIRST sign anything was wrong was a raw error dialog the moment
		// someone actually typed a question. Checked async so the chat
		// shell itself still renders instantly either way.
		this.checkStatus();
	}

	/** noviz_ai.api.get_status() is safe to call even when nothing is
	 *  configured at all (unlike send_message, which throws on purpose
	 *  once an actual chat attempt is made) — real pre-flight state, not
	 *  a guess from whether the page loaded. */
	checkStatus() {
		frappe.call({
			method: 'noviz_ai.api.get_status',
			callback: (r) => {
				const status = r.message || {};
				if (status.configured) return;

				this.$input.prop('disabled', true);
				this.$sendBtn.prop('disabled', true);
				this.$input.attr('placeholder', __('Noviz AI is not set up yet'));

				const $setup = $('<div class="noviz-ai-chat-msg noviz-ai-chat-msg-assistant noviz-ai-setup-notice"></div>').appendTo(this.$log);
				if (status.can_configure) {
					$setup.html(
						`<p>${__('Noviz AI is not configured yet. Add your Relay Base URL and API Key to get started.')}</p>` +
						`<a class="btn btn-primary btn-sm" href="/app/noviz-ai-settings">${__('Configure Noviz AI Settings')}</a>`
					);
				} else {
					$setup.text(__('Noviz AI is not set up yet. Ask your ERPNext administrator to configure it under Noviz AI Settings.'));
				}
			},
		});
	}

	/** Prints ONLY the given element (one message, via its own per-message
	 *  Export PDF button) — the browser's own native print-to-PDF, no
	 *  jsPDF/html2canvas dependency added to this thin plugin. The marker
	 *  class is removed on the browser's own 'afterprint' event (fires
	 *  whether the user actually printed or cancelled the dialog), so
	 *  the page returns to normal either way without a fixed timeout
	 *  guess. */
	printOnly($el) {
		$el.addClass('noviz-ai-print-this');
		const cleanup = () => {
			$el.removeClass('noviz-ai-print-this');
			window.removeEventListener('afterprint', cleanup);
		};
		window.addEventListener('afterprint', cleanup);
		window.print();
	}

	/** Real ERPNext-generated PDF for the one record this reply is about
	 *  (relayReasoningEngine.ts's own "document" field on a single-record
	 *  ".get" reply) — the SAME frappe.utils.print_format.download_pdf
	 *  endpoint ERPNext's own "Print"/"Download PDF" desk button calls.
	 *  Built and opened entirely client-side: unlike Pro's chat (a
	 *  separate origin, has to proxy the PDF bytes through its own
	 *  backend), this page IS a page inside the customer's own real
	 *  Frappe site, so the browser's already-authenticated session cookie
	 *  carries straight through — no relay round-trip, no new backend
	 *  route, and the real per-user/per-document ERPNext permission check
	 *  applies exactly as if they'd clicked ERPNext's own button. */
	appendDocumentLink($msg, doc) {
		const url = `/api/method/frappe.utils.print_format.download_pdf?doctype=${encodeURIComponent(doc.doctype)}&name=${encodeURIComponent(doc.id)}&no_letterhead=0`;
		$(`<a href="${url}" target="_blank" rel="noopener" class="noviz-ai-msg-export noviz-ai-doc-download">${__('Download PDF')}</a>`).appendTo($msg);
	}

	/** `html` (when present) is real, pre-rendered markup from the relay
	 *  (rendererRegistry) — injected as-is, appended after the markdown-
	 *  rendered text reply, same "text explains, table shows the real
	 *  rows" layout Pro's own chat uses. A per-message Export PDF button
	 *  is added right below it, matching Pro's own placement. */
	addMessage(role, text, html) {
		const cssClass = role === 'user' ? 'noviz-ai-chat-msg-user' : 'noviz-ai-chat-msg-assistant';
		const $msg = $(`<div class="noviz-ai-chat-msg ${cssClass}"></div>`).appendTo(this.$log);
		if (role === 'assistant') {
			// The model's own prose is still markdown (bold labels, bullet
			// lists) even when a real table also follows it — rendered via
			// Frappe's own built-in sanitizing renderer, not a new
			// dependency. User's own input stays plain text — no reason to
			// interpret what THEY typed as markup.
			$msg.html(frappe.markdown(text));
			if (html) {
				$msg.append(html);
				$(`<button type="button" class="noviz-ai-msg-export noviz-ai-print-export">${__('Export PDF')}</button>`).appendTo($msg);
			}
		} else {
			$msg.text(text);
		}
		this.$log.scrollTop(this.$log[0].scrollHeight);
		return $msg;
	}

	/** `promptOverride` lets a row-id click / next-step button send a
	 *  real new prompt without the user retyping it — same mechanism
	 *  the ordinary input box uses underneath. */
	send(promptOverride) {
		const prompt = (promptOverride || this.$input.val()).trim();
		if (!prompt || this.sending) return;

		this.sending = true;
		this.$sendBtn.prop('disabled', true);
		if (!promptOverride) this.$input.val('');
		this.addMessage('user', prompt);
		const $thinking = this.addMessage('assistant', __('Thinking...'));

		frappe.call({
			method: 'noviz_ai.api.send_message',
			args: { prompt: prompt, previous_turn_id: this.lastTurnId },
			callback: (r) => {
				const reply = (r.message && r.message.reply) || __('No reply received.');
				$thinking.html(frappe.markdown(reply));
				if (r.message && r.message.html) {
					$thinking.append(r.message.html);
					$(`<button type="button" class="noviz-ai-msg-export noviz-ai-print-export">${__('Export PDF')}</button>`).appendTo($thinking);
				}
				if (r.message && r.message.document) {
					this.appendDocumentLink($thinking, r.message.document);
				}
				// Track the relay's own turnId so the NEXT message
				// continues this same conversation instead of starting
				// fresh — real memory, not just a longer single reply.
				if (r.message && r.message.turnId) {
					this.lastTurnId = r.message.turnId;
				}
				this.$log.scrollTop(this.$log[0].scrollHeight);
			},
			error: () => {
				// frappe.call already shows the real server error to the
				// user via its own dialog — just clear the placeholder
				// rather than showing a second, redundant message.
				$thinking.remove();
			},
			always: () => {
				this.sending = false;
				this.$sendBtn.prop('disabled', false);
			},
		});
	}
}
