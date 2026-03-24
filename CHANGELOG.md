# Changelog

## v0.1.2 — 2026-03-24

Initial public release of the ProjectBrain CLI on PyPI. (Packaging fixes from v0.1.1.)

## v0.1.1 — 2026-03-24

Initial public release of the ProjectBrain CLI.

### What's included

**Authentication**
- `pb login` — email/password, Google OAuth, and GitHub OAuth
- `pb login --token pb_xxx` — direct API key or JWT login
- `pb whoami` / `pb logout`
- Credentials stored in `~/.pb/config.json`; override with `PB_TOKEN`

**Agent runner (`pb run`)**
- Polls ProjectBrain for tasks claimed by your agent and executes them
- Human login flow: lists team agents and prompts for selection; skip with `--agent <name>`
- Agent key flow: reads identity from the API and runs directly
- **GitHub mode** — automatically enabled when the project has GitHub configured; spawns a Docker container per task and opens pull requests via `GITHUB_TOKEN`
- **Adapter mode** — runs a local adapter script (`claude_code`, `gemini`) when Docker/GitHub is not configured
- MCP server URL auto-derived from `--server`; override with `--mcp-url`
- `--once` flag for single-tick CI runs
- Configurable poll interval, concurrency, and log level

**Project & task management**
- `pb projects list` / `pb projects get <id>`
- `pb tasks list` (filter by status, assignee, full-text search)
- `pb tasks get <id>`

**Knowledge**
- `pb knowledge list` / `pb knowledge search` — hybrid semantic + keyword search

**Curation**
- `pb curate run` — AI-assisted knowledge review and improvement

**Shell completions**
- `pb completion install` — sets up tab completion for bash, zsh, and fish

**Developer ergonomics**
- `--json` flag on any command for raw JSON output (pipe-friendly)
- `--server` flag to point at a self-hosted or local instance
- `--version` to print the installed version
