### Noviz AI

Open-source Frappe/ERPNext integration plugin for Noviz AI. The plugin acts as a lightweight client that connects ERPNext to the Noviz Relay API, with AI processing, orchestration, and business logic handled by the Noviz AI platform.

### Architecture

The repository provides the integration layer between ERPNext and the Noviz AI platform. It is responsible for:

- Forwarding chat messages to the central Noviz AI relay.
- Executing the generic `{kind, doctype, filters, fields}` instructions returned by the relay through Frappe's native ORM.
- Returning the results to the Noviz AI platform.

All operations are executed in the context of the currently logged-in user (`frappe.session.user`). This means ERPNext's existing roles, permissions, and access controls are enforced natively, without requiring separate credentials.

The plugin does not contain entity definitions, business rules, prompts, AI orchestration, or application-specific reasoning. These capabilities are provided by the Noviz AI platform, a separate closed-source, multi-tenant service.

### License

mit
