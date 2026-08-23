### Noviz AI

Open-source Frappe/ERPNext integration plugin for Noviz AI. The plugin acts as a lightweight client that connects ERPNext to the Noviz Relay API, with AI processing, orchestration, and business logic handled by the Noviz AI platform.

### Architecture

This repo is deliberately thin. It only knows how to:

- forward a chat message to the central Noviz AI relay
- execute the generic `{kind, doctype, filters, fields}` instruction the relay sends back, using Frappe's own ORM
- hand the result back to the relay

Every call runs as the logged-in user (`frappe.session.user`) — real, native ERPNext permission enforcement applies exactly as if they'd used ERPNext's own UI, no separate credential involved.

The plugin has no knowledge of entity names, business rules, or prompts — none of that logic is shipped here. All AI reasoning, orchestration, and business logic run on the Noviz AI platform, a separate, closed-source, multi-tenant service. That split is why this plugin can be open source while the platform it talks to isn't.

Hosted access to the platform is available at [noviz.in](https://noviz.in).

### License

mit
