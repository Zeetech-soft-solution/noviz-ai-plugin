### Noviz AI

Open-source Frappe/ERPNext integration plugin for Noviz AI. The plugin acts as a lightweight client that connects ERPNext to the Noviz Relay API, with AI processing, orchestration, and business logic handled by the Noviz AI platform.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app noviz_ai
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/noviz_ai
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
