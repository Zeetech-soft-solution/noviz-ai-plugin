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
// The real Noviz AI mark (same visual pattern as Zeetech's own "Z" —
// dark rounded-square background, bold letter in the brand teal — see
// noviz-ai-plugin/public/images/icon-master.svg for the source SVG and
// generation script). Embedded as a data: URI rather than referenced by
// a /assets/noviz_ai/... URL: a real, separate infra issue found live
// this session on the demo deployment (the frontend/nginx container
// only has frappe/erpnext baked into its own image, so ANY /assets/
// noviz_ai/... path 404s there) means a plain <img src> reference can't
// be trusted to work on every real deployment. A data: URI has no
// dependency on any site's own asset-serving config at all.
const NOVIZ_AI_LOGO_DATA_URI =
	'data:image/png;base64,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';

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
			width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0; display: block;
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
			/* Attach/camera — real port of Pro's own Composer.tsx icon pair,
			same two icons, same position (left of the text input), same
			behavior (both call the same send-an-image path with an
			optional note). */
			.noviz-ai-chat-icon-btn {
				background: none; border: 1px solid var(--border-color, #d1d8dd); border-radius: 6px;
				width: 36px; height: 36px; font-size: 16px; cursor: pointer; flex-shrink: 0;
				display: flex; align-items: center; justify-content: center;
			}
			.noviz-ai-chat-icon-btn:hover { background: var(--control-bg, #f4f5f6); }
			.noviz-ai-camera-overlay {
				position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 2000;
				display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
			}
			.noviz-ai-camera-overlay video { max-width: 92vw; max-height: 70vh; border-radius: 8px; }
			.noviz-ai-camera-overlay .noviz-ai-camera-actions { display: flex; gap: 12px; }
			.noviz-ai-scan-note-row { display: flex; gap: 8px; padding: 10px 0 0; }
			.noviz-ai-scan-note-row input { flex: 1; }

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
					<img class="noviz-ai-logo" src="${NOVIZ_AI_LOGO_DATA_URI}" alt="${__('Noviz AI')}" />
					<div class="noviz-ai-header-text">
						<h3>${__('Noviz AI')}</h3>
						<div class="noviz-ai-subtitle">${__('ERP Assistant for')} ${frappe.defaults.get_default('company') || frappe.sys_defaults.company || ''}</div>
					</div>
				</div>
				<div class="noviz-ai-chat-log"></div>
				<div class="noviz-ai-chat-input-row">
					<button type="button" class="noviz-ai-chat-icon-btn noviz-ai-attach-btn" title="${__('Attach an image')}">📎</button>
					<button type="button" class="noviz-ai-chat-icon-btn noviz-ai-camera-btn" title="${__('Scan with camera')}">📷</button>
					<input type="file" class="noviz-ai-file-input" accept="image/jpeg,image/png,image/webp" style="display:none" />
					<input type="text" class="form-control noviz-ai-chat-input"
						placeholder="${__('Ask about your ERPNext data...')}" />
					<button class="btn btn-primary btn-sm noviz-ai-chat-send">${__('Send')}</button>
				</div>
			</div>
		`).appendTo(this.page.body);

		this.$log = this.$container.find('.noviz-ai-chat-log');
		this.$input = this.$container.find('.noviz-ai-chat-input');
		this.$sendBtn = this.$container.find('.noviz-ai-chat-send');
		this.$fileInput = this.$container.find('.noviz-ai-file-input');

		this.$sendBtn.on('click', () => this.send());
		// Real port of Pro's own Composer.tsx attach/camera pair — 2MB cap
		// (same limit the relay's own scan route enforces server-side via
		// multer), image/jpeg|png|webp only.
		const MAX_IMAGE_BYTES = 2 * 1024 * 1024;
		this.$container.find('.noviz-ai-attach-btn').on('click', () => {
			if (!this.sending) this.$fileInput.trigger('click');
		});
		this.$fileInput.on('change', (e) => {
			const file = e.target.files && e.target.files[0];
			e.target.value = '';
			if (!file) return;
			if (file.size > MAX_IMAGE_BYTES) {
				frappe.msgprint(__('That image is too large — please pick one under 2MB.'));
				return;
			}
			this.promptForNoteAndSend(file);
		});
		this.$container.find('.noviz-ai-camera-btn').on('click', () => {
			if (!this.sending) this.openCamera();
		});
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

	/** Shared by send() and sendImage() — the actual result rendering is
	 *  identical either way (a normal chat turn or a scanned-image turn
	 *  both finish as the SAME {reply, html, document, turnId} shape),
	 *  only how the turn STARTS differs. */
	_renderTurnResult($thinking, message) {
		const reply = (message && message.reply) || __('No reply received.');
		$thinking.html(frappe.markdown(reply));
		if (message && message.html) {
			$thinking.append(message.html);
			$(`<button type="button" class="noviz-ai-msg-export noviz-ai-print-export">${__('Export PDF')}</button>`).appendTo($thinking);
		}
		if (message && message.document) {
			this.appendDocumentLink($thinking, message.document);
		}
		// Track the relay's own turnId so the NEXT message continues this
		// same conversation instead of starting fresh — real memory, not
		// just a longer single reply. Works the same way whether the turn
		// started from typed text or a scanned image.
		if (message && message.turnId) {
			this.lastTurnId = message.turnId;
		}
		this.$log.scrollTop(this.$log[0].scrollHeight);
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
			callback: (r) => this._renderTurnResult($thinking, r.message),
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

	/** A short optional note travels alongside the image (e.g. "this is
	 *  from our supplier X") — same real field agent.routes.ts's own
	 *  /scan route has always accepted, ported here as a plain prompt
	 *  dialog rather than a persistent input, since it's genuinely
	 *  optional and per-image.
	 *
	 *  Real bug found live via browser testing: Frappe's own default
	 *  Dialog behavior closes on an outside/backdrop click OR Escape,
	 *  with NO callback and no visible feedback — an accidental
	 *  off-target click silently discarded the already-picked image,
	 *  with nothing telling the person their scan never went anywhere
	 *  (confirmed live: a coordinate slightly off the real Send button
	 *  landed on the backdrop instead and the request never fired at
	 *  all). `static: true` is Frappe's own documented option for
	 *  exactly this — the ONLY ways to close this dialog now are the
	 *  explicit Send action or its own visible × button, never an
	 *  accidental miss-click. `onhide` cleans up the dialog's own DOM
	 *  element every time it closes (either path), rather than leaving
	 *  a hidden, orphaned one behind for every scan attempted in a long
	 *  session — also confirmed live (the SAME accidental-dismiss
	 *  incident left a real second stacked dialog in the page). */
	promptForNoteAndSend(file) {
		const d = new frappe.ui.Dialog({
			title: __('Scan document'),
			static: true,
			fields: [
				{ fieldtype: 'Data', fieldname: 'note', label: __('Note (optional)'), description: __('Anything that helps, e.g. which supplier or customer this is from.') },
			],
			primary_action_label: __('Send'),
			primary_action: (values) => {
				d.hide();
				this.sendImage(file, values.note || '');
			},
			onhide: () => d.$wrapper.remove(),
		});
		d.show();
	}

	/** Real port of Pro's own CameraCapture.tsx — live camera preview,
	 *  one frame captured to canvas on demand, exported as JPEG stepping
	 *  quality down [0.85, 0.7, 0.55, 0.4] until under the same 2MB cap
	 *  the relay enforces, media stream always stopped on close (capture,
	 *  cancel, or the browser denying camera access) so the camera light
	 *  never stays on after this overlay closes. */
	openCamera() {
		const MAX_IMAGE_BYTES = 2 * 1024 * 1024;
		const $overlay = $(`
			<div class="noviz-ai-camera-overlay">
				<video autoplay playsinline></video>
				<div class="noviz-ai-camera-actions">
					<button type="button" class="btn btn-primary noviz-ai-camera-capture">${__('Capture')}</button>
					<button type="button" class="btn btn-secondary noviz-ai-camera-cancel">${__('Cancel')}</button>
				</div>
			</div>
		`).appendTo(document.body);
		const $video = $overlay.find('video')[0];
		let stream = null;

		const close = () => {
			if (stream) stream.getTracks().forEach((t) => t.stop());
			$overlay.remove();
		};
		$overlay.find('.noviz-ai-camera-cancel').on('click', close);

		navigator.mediaDevices
			.getUserMedia({ video: { facingMode: 'environment' } })
			.then((s) => {
				stream = s;
				$video.srcObject = s;
			})
			.catch(() => {
				frappe.msgprint(__('Could not access the camera. Check your browser permissions, or use Attach instead.'));
				close();
			});

		$overlay.find('.noviz-ai-camera-capture').on('click', () => {
			const canvas = document.createElement('canvas');
			canvas.width = $video.videoWidth;
			canvas.height = $video.videoHeight;
			canvas.getContext('2d').drawImage($video, 0, 0);

			const qualities = [0.85, 0.7, 0.55, 0.4];
			const tryQuality = (i) => {
				canvas.toBlob(
					(blob) => {
						if (!blob) return;
						if (blob.size > MAX_IMAGE_BYTES && i < qualities.length - 1) {
							tryQuality(i + 1);
							return;
						}
						const file = new File([blob], 'scan.jpg', { type: 'image/jpeg' });
						close();
						this.promptForNoteAndSend(file);
					},
					'image/jpeg',
					qualities[i]
				);
			};
			tryQuality(0);
		});
	}

	/** Real port of agent.routes.ts's own /scan flow, adapted for this
	 *  thin-plugin architecture — see api.py's scan_image() doc comment
	 *  for the full server-side path. A plain frappe.call can't carry a
	 *  binary file in its JSON args, so this is a raw fetch() with
	 *  FormData instead, matching the standard Frappe convention for a
	 *  whitelisted method that needs a real file upload (the CSRF token
	 *  header is the one thing frappe.call would otherwise add for us).
	 *  The user-visible bubble reads "[scanned image]" (+ note) rather
	 *  than the real OCR'd text — same discipline as Pro's own chat
	 *  history label for a scan turn, the actual extracted text still
	 *  reaches the model, it's just not what's shown as "what you typed". */
	sendImage(file, note) {
		this.sending = true;
		this.$sendBtn.prop('disabled', true);
		this.addMessage('user', note ? `[${__('scanned image')}] ${note}` : `[${__('scanned image')}]`);
		const $thinking = this.addMessage('assistant', __('Reading the image...'));

		const formData = new FormData();
		formData.append('image', file);
		if (note) formData.append('note', note);
		if (this.lastTurnId) formData.append('previous_turn_id', this.lastTurnId);

		fetch('/api/method/noviz_ai.api.scan_image', {
			method: 'POST',
			headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token },
			body: formData,
		})
			.then(async (res) => {
				if (!res.ok) {
					const body = await res.json().catch(() => ({}));
					throw new Error((body._server_messages && JSON.parse(JSON.parse(body._server_messages)[0]).message) || body.exception || __('Scan failed.'));
				}
				return res.json();
			})
			.then((data) => this._renderTurnResult($thinking, data.message))
			.catch((err) => {
				$thinking.html(frappe.markdown(err.message || __('Scan failed.')));
			})
			.finally(() => {
				this.sending = false;
				this.$sendBtn.prop('disabled', false);
			});
	}
}
