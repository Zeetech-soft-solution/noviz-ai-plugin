// Native desk chat page. This is a thin UI shell only — every real
// decision (what tool to call, what data means, how to phrase the
// answer) happens on the private central relay; this file's whole job
// is collecting a prompt, calling the plugin's one whitelisted method,
// and rendering whatever comes back. No entity/tool knowledge here.
frappe.pages['noviz-ai-chat'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Noviz AI Chat',
		single_column: true,
	});

	new NovizAIChat(page);
};

// Minimal inline styling — a full CSS asset felt like overkill for one
// small page, and inline keeps this a genuinely thin, single-file UI.
if (!document.getElementById('noviz-ai-chat-style')) {
	$(`<style id="noviz-ai-chat-style">
		/* Frappe's own page container caps width by default (Bootstrap
		   .container) — explicit product decision: use the full page
		   width, not a narrow centered column, so this override is scoped
		   to just this page's own wrapper. */
		#page-noviz-ai-chat .container { max-width: 100%; }
		.noviz-ai-chat { display: flex; flex-direction: column; height: calc(100vh - 200px); width: 100%; }
		.noviz-ai-chat-log { flex: 1; overflow-y: auto; padding: 10px 0; }
		.noviz-ai-chat-msg { padding: 8px 12px; border-radius: 8px; margin-bottom: 8px; white-space: pre-wrap; }
		.noviz-ai-chat-msg-user { background: var(--bg-blue, #e3f2fd); margin-left: auto; max-width: 60%; }
		/* Assistant replies can carry real tables (frappe.markdown below
		   turns the model's own markdown into real HTML) — no width cap,
		   a wide table shouldn't get squeezed into 60% of the page. */
		.noviz-ai-chat-msg-assistant { background: var(--bg-gray, #f0f0f0); margin-right: auto; max-width: 95%; }
		.noviz-ai-chat-msg-assistant table { border-collapse: collapse; margin: 8px 0; width: 100%; background: var(--fg-color, #fff); }
		.noviz-ai-chat-msg-assistant th, .noviz-ai-chat-msg-assistant td { border: 1px solid var(--border-color, #d1d8dd); padding: 6px 10px; text-align: left; }
		.noviz-ai-chat-msg-assistant th { background: var(--control-bg, #f4f5f6); font-weight: 600; }
		.noviz-ai-chat-msg-assistant p:last-child { margin-bottom: 0; }
		.noviz-ai-chat-input-row { display: flex; gap: 8px; padding-top: 8px; border-top: 1px solid var(--border-color, #d1d8dd); }
		.noviz-ai-chat-input { flex: 1; }
		/* Export renders ONLY the chat log — the browser's own
		   print-to-PDF handles the actual PDF generation, zero
		   dependencies added to this thin plugin for it. */
		@media print {
			body * { visibility: hidden; }
			.noviz-ai-chat-log, .noviz-ai-chat-log * { visibility: visible; }
			.noviz-ai-chat-log { position: absolute; top: 0; left: 0; width: 100%; height: auto; }
		}
	</style>`).appendTo('head');
}

class NovizAIChat {
	constructor(page) {
		this.page = page;
		this.sending = false;
		this.render();
	}

	render() {
		this.$container = $(`
			<div class="noviz-ai-chat">
				<div class="noviz-ai-chat-log"></div>
				<div class="noviz-ai-chat-input-row">
					<input type="text" class="form-control noviz-ai-chat-input"
						placeholder="${__('Ask about your ERPNext data...')}" />
					<button class="btn btn-default btn-sm noviz-ai-chat-export">${__('Export PDF')}</button>
					<button class="btn btn-primary btn-sm noviz-ai-chat-send">${__('Send')}</button>
				</div>
			</div>
		`).appendTo(this.page.body);

		this.$log = this.$container.find('.noviz-ai-chat-log');
		this.$input = this.$container.find('.noviz-ai-chat-input');
		this.$sendBtn = this.$container.find('.noviz-ai-chat-send');
		this.$exportBtn = this.$container.find('.noviz-ai-chat-export');

		this.$sendBtn.on('click', () => this.send());
		this.$input.on('keydown', (e) => {
			if (e.key === 'Enter' && !this.sending) this.send();
		});
		// Browser-native print-to-PDF — no jsPDF/html2canvas, no new
		// dependency in this deliberately thin plugin. The @media print
		// rule above hides everything except the chat log itself.
		this.$exportBtn.on('click', () => window.print());

		this.addMessage(
			'assistant',
			__('Hi! Ask me anything about your ERPNext data — quotations, sales orders, or customers.')
		);
	}

	addMessage(role, text) {
		const cssClass = role === 'user' ? 'noviz-ai-chat-msg-user' : 'noviz-ai-chat-msg-assistant';
		const $msg = $(`<div class="noviz-ai-chat-msg ${cssClass}"></div>`).appendTo(this.$log);
		if (role === 'assistant') {
			// The model's replies are markdown (bold labels, bullet
			// lists, occasionally a real table) — render it as real HTML
			// instead of showing raw asterisks/pipes. frappe.markdown is
			// Frappe's own built-in sanitizing renderer (same one comment
			// threads/ToDo descriptions already use), not a new
			// dependency. User's own input stays plain text below — no
			// reason to interpret what THEY typed as markup.
			$msg.html(frappe.markdown(text));
		} else {
			$msg.text(text);
		}
		this.$log.scrollTop(this.$log[0].scrollHeight);
	}

	send() {
		const prompt = this.$input.val().trim();
		if (!prompt || this.sending) return;

		this.sending = true;
		this.$sendBtn.prop('disabled', true);
		this.$input.val('');
		this.addMessage('user', prompt);
		this.addMessage('assistant', __('Thinking...'));
		const $thinking = this.$log.find('.noviz-ai-chat-msg-assistant').last();

		frappe.call({
			method: 'noviz_ai.api.send_message',
			args: { prompt: prompt },
			callback: (r) => {
				const reply = (r.message && r.message.reply) || __('No reply received.');
				$thinking.html(frappe.markdown(reply));
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
