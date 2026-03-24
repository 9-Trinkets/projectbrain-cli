# ProjectBrain CLI

Command-line interface for [ProjectBrain](https://projectbrain.tools) — manage projects, tasks, knowledge, and run AI agents from your terminal.

## Installation

```bash
pip install project-brain
```

Requires Python 3.11+.

## Quick Start

```bash
# Log in (opens browser)
pb login --google

# List your projects
pb projects list

# Start the agent runner
pb run --project <project-id> --agent <agent-name>
```

## Authentication

| Method | Command |
|--------|---------|
| Google OAuth | `pb login --google` |
| GitHub OAuth | `pb login --github` |
| Email / password | `pb login` |
| API token | `pb login --token pb_xxx` |

```bash
pb whoami   # show current identity
pb logout   # clear stored credentials
```

Credentials are stored in `~/.pb/config.json`. Set `PB_TOKEN` in your environment to override.

## Commands

### `pb run` — Start the agent runner

Connects an agent to ProjectBrain and polls for tasks to execute.

```bash
pb run --project <project-id>                    # interactive agent selection
pb run --project <project-id> --agent <name>     # skip selection prompt
pb run --project <project-id> --once             # single tick, then exit
```

**Options**

| Flag | Default | Description |
|------|---------|-------------|
| `--project`, `-p` | *(required)* | Project ID |
| `--agent`, `-a` | interactive | Agent name or ID prefix |
| `--interval` | `60` | Poll interval in seconds |
| `--once` | `false` | Run one tick and exit |
| `--max-concurrent` | `1` | Max simultaneous tasks |
| `--mcp-url` | auto-derived | MCP server URL |
| `--github OWNER/REPO` | auto-detected | Enable GitHub mode (Docker + PRs) |
| `--rebuild` | `false` | Force rebuild of agent Docker image |
| `--log-level` | `INFO` | Logging verbosity |

**GitHub mode** is enabled automatically when your project has GitHub configured. The runner spawns a Docker container per task and opens pull requests. Requires `GITHUB_TOKEN` in your environment.

**Adapter mode** (no Docker) uses a local adapter script. The adapter is resolved from the agent's configured type (`claude_code`, `gemini`, etc.).

### `pb projects`

```bash
pb projects list           # list all projects
pb projects get <id>       # show project details
```

### `pb tasks`

```bash
pb tasks list --project <id>                    # list tasks
pb tasks list --project <id> --status todo      # filter by status
pb tasks list --project <id> --search "auth"    # search
pb tasks get <task-id>                          # show task detail
```

### `pb knowledge`

```bash
pb knowledge search --project <id> "auth middleware"   # semantic search
pb knowledge list --project <id>                       # list entries
```

### `pb curate`

AI-assisted knowledge curation — reviews and improves knowledge entries in a project.

```bash
pb curate run --project <id>
```

### `pb completion`

Shell tab-completion setup.

```bash
pb completion install        # install for current shell
pb completion show           # print completion script
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PB_TOKEN` | API token or JWT (overrides stored credentials) |
| `PB_SERVER` | API server URL (default: `https://api.projectbrain.tools`) |
| `PB_MCP_URL` | MCP server URL (default: auto-derived from `PB_SERVER`) |
| `GITHUB_TOKEN` | GitHub personal access token (required for GitHub mode) |
| `GITHUB_REPO` | Override GitHub repo (`owner/repo`) |
| `PB_RUNNER_PATH` | Override path to `runner.py` |
| `PB_OAUTH_PORT` | Local port for OAuth callback (default: `8085`) |

## Global Flags

```bash
pb --json <command>          # output raw JSON
pb --server <url> <command>  # override API server
pb --version                 # print version
```

## License

MIT
