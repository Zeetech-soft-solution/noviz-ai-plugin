// Native desk chat page. This is a thin UI shell only — every real
// decision (what tool to call, what data means, how to phrase the
// answer) happens on the private central relay; this file's whole job
// is collecting a prompt, calling the plugin's one whitelisted method,
// and rendering whatever comes back. No entity/tool knowledge here.
//
// 2026-08-18: visually rebuilt to feel like Noviz's own Pro product
// (branded header, real message cards, a capabilities panel) — while
// deliberately STAYING a native Frappe desk page, not becoming a
// separate branded app with its own login. That was an explicit,
// locked-in architecture decision (no separate login, lives inside the
// customer's own ERPNext, discoverable via their own desk nav) —
// visual richness doesn't require throwing that away. The capabilities
// panel below lists the REAL V1 relay tool set
// (relayReasoningEngine.ts's own RELAY_READ_TOOLS), not a copy of
// Pro's much larger catalog — this plugin genuinely can only do what's
// listed, and the panel should never claim more than that.
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

		.noviz-ai-shell { display: flex; gap: 20px; height: calc(100vh - 120px); }

		.noviz-ai-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
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
			white-space: pre-wrap; max-width: 78%; box-shadow: 0 1px 2px rgba(0,0,0,0.06);
		}
		.noviz-ai-chat-msg-user {
			background: #1e7a5c; color: #fff; margin-left: auto;
		}
		.noviz-ai-chat-msg-assistant {
			background: var(--fg-color, #fff); border: 1px solid var(--border-color, #e2e8e4);
			margin-right: auto; max-width: 92%;
		}
		.noviz-ai-chat-msg-assistant table { border-collapse: collapse; margin: 8px 0; width: 100%; }
		.noviz-ai-chat-msg-assistant th, .noviz-ai-chat-msg-assistant td { border: 1px solid var(--border-color, #d1d8dd); padding: 6px 10px; text-align: left; }
		.noviz-ai-chat-msg-assistant th { background: var(--control-bg, #f4f5f6); font-weight: 600; }
		.noviz-ai-chat-msg-assistant p:last-child { margin-bottom: 0; }

		.noviz-ai-chat-input-row { display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid var(--border-color, #d1d8dd); }
		.noviz-ai-chat-input { flex: 1; }

		.noviz-ai-sidebar {
			width: 300px; flex-shrink: 0; overflow-y: auto; padding-left: 20px;
			border-left: 1px solid var(--border-color, #d1d8dd);
		}
		.noviz-ai-sidebar h4 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted, #8d99a6); margin: 0 0 10px; }
		.noviz-ai-cap-group { margin-bottom: 16px; }
		.noviz-ai-cap-group .cap-title { font-weight: 600; font-size: 13px; margin-bottom: 4px; }
		.noviz-ai-cap-group .cap-desc { font-size: 12px; color: var(--text-muted, #8d99a6); line-height: 1.5; }

		@media (max-width: 900px) {
			.noviz-ai-shell { flex-direction: column; height: auto; }
			.noviz-ai-sidebar { width: auto; border-left: none; border-top: 1px solid var(--border-color, #d1d8dd); padding-left: 0; padding-top: 16px; }
		}

		@media print {
			body * { visibility: hidden; }
			.noviz-ai-chat-log, .noviz-ai-chat-log * { visibility: visible; }
			.noviz-ai-chat-log { position: absolute; top: 0; left: 0; width: 100%; height: auto; }
		}
	</style>`).appendTo('head');
}

// The REAL V1 relay capability set, kept in one place so the panel and
// any future change stay honest about what this plugin can actually
// do — see relayReasoningEngine.ts's RELAY_READ_TOOLS for the source of
// truth this mirrors.
const NOVIZ_AI_CAPABILITIES = [
	{ title: 'Quotations', desc: 'List open/recent quotations, or look up one by ID.' },
	{ title: 'Sales Orders', desc: 'List sales orders, or look up one by ID.' },
	{ title: 'Customers', desc: 'List customer accounts, or look up one by ID.' },
];

class NovizAIChat {
	constructor(page) {
		this.page = page;
		this.sending = false;
		this.render();
	}

	render() {
		this.$container = $(`
			<div class="noviz-ai-shell">
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
						<button class="btn btn-default btn-sm noviz-ai-chat-export">${__('Export PDF')}</button>
						<button class="btn btn-primary btn-sm noviz-ai-chat-send">${__('Send')}</button>
					</div>
				</div>
				<div class="noviz-ai-sidebar">
					<h4>${__('What I can help with')}</h4>
				</div>
			</div>
		`).appendTo(this.page.body);

		const $sidebar = this.$container.find('.noviz-ai-sidebar');
		NOVIZ_AI_CAPABILITIES.forEach((cap) => {
			$(`<div class="noviz-ai-cap-group">
				<div class="cap-title">${frappe.utils.escape_html(cap.title)}</div>
				<div class="cap-desc">${frappe.utils.escape_html(cap.desc)}</div>
			</div>`).appendTo($sidebar);
		});

		this.$log = this.$container.find('.noviz-ai-chat-log');
		this.$input = this.$container.find('.noviz-ai-chat-input');
		this.$sendBtn = this.$container.find('.noviz-ai-chat-send');
		this.$exportBtn = this.$container.find('.noviz-ai-chat-export');

		this.$sendBtn.on('click', () => this.send());
		this.$input.on('keydown', (e) => {
			if (e.key === 'Enter' && !this.sending) this.send();
		});
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
			// lists, occasionally a real table) — render as real HTML via
			// Frappe's own built-in sanitizing renderer, not a new
			// dependency. User's own input stays plain text — no reason
			// to interpret what THEY typed as markup.
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
