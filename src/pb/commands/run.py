"""pb run — start the collaborator runner loop."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from pb import config
from pb.client import APIError, request, resolve_project
from pb.reporters import panic


def _find_runner() -> Path:
    """Locate runner.py relative to the CLI package or via RUNNER_PATH env."""
    explicit = os.getenv("PB_RUNNER_PATH")
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        panic(code="runner_not_found", message=f"PB_RUNNER_PATH points to missing file: {explicit}")

    # Walk up from cli/src/pb/commands/run.py → repo root, then into runner/
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    candidate = repo_root / "runner" / "runner.py"
    if candidate.is_file():
        return candidate
    panic(
        code="runner_not_found",
        message="Cannot locate runner/runner.py. Set PB_RUNNER_PATH or run from the project repo."
    )


# Adapter name → required env vars (beyond what the runner already injects)
_ADAPTER_ENV_REQUIREMENTS: dict[str, list[str]] = {
    "gemini": ["GEMINI_API_KEY"],
    "claude_code": [],
}


def _derive_mcp_url(server: str) -> str:
    """Derive the MCP server URL from the API server URL.

    For local dev (localhost / 127.0.0.1) the MCP server runs on port 8001
    per docker-compose.  For any other host the production MCP server is used.
    """
    stripped = server.rstrip("/")
    m = re.match(r"(https?://(?:localhost|127\.0\.0\.1))(?::\d+)?$", stripped)
    if m:
        return f"{m.group(1)}:8001"
    return "https://mcp.projectbrain.tools/mcp"


def _resolve_adapter_hook(adapter: str, runner_path: Path) -> str | None:
    """Return a WORK_HOOK command for the given adapter name, or None."""
    adapters_dir = runner_path.parent / "adapters"
    # Prefer .py adapter, fall back to .sh
    for ext in (".py", ".sh"):
        candidate = adapters_dir / f"{adapter}{ext}"
        if candidate.is_file():
            if ext == ".py":
                return f"{sys.executable} {candidate}"
            return f"bash {candidate}"
    return None


def _check_mcp_health(mcp_url: str) -> None:
    """Verify the MCP server is reachable before starting the runner.

    Hits the /health endpoint.  Emits a warning (not an error) if unreachable
    so the runner can still start for adapters that don't use MCP.
    """
    health_url = re.sub(r"/mcp$", "", mcp_url.rstrip("/")) + "/health"
    try:
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=5):
            pass
    except urllib.error.URLError as exc:
        typer.echo(
            f"Warning: MCP server unreachable at {health_url} — {exc}\n"
            "  If you're running locally, start it with: docker compose up -d mcp\n"
            "  If using production, confirm JWT_SECRET_KEY is set on the MCP Render service\n"
            "  to match the API service's auto-generated JWT_SECRET_KEY.",
            err=True,
        )
    except Exception:
        pass  # Don't block startup for unexpected errors


def _check_adapter_env(adapter: str) -> None:
    """Raise typer.Exit if required env vars for the adapter are missing."""
    required = _ADAPTER_ENV_REQUIREMENTS.get(adapter, [])
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        panic(
            code="missing_env_vars",
            message=f"Adapter '{adapter}' requires: {', '.join(missing)}. Set them in your environment before running."
        )


# Adapter → Docker image name / Dockerfile name
_ADAPTER_IMAGE: dict[str, str] = {
    "gemini":     "pb-agent-gemini",
    "claude_code": "pb-agent-claude",
}
_ADAPTER_DOCKERFILE: dict[str, str] = {
    "gemini":     "Dockerfile.gemini",
    "claude_code": "Dockerfile.claude",
}

# Env vars the runner injects per-task that must be forwarded into the container.
# Listed without values so docker inherits them from the runner's environment.
_CONTAINER_PASSTHROUGH = [
    # Task context (set by runner per task)
    "TASK_ID", "TASK_TITLE", "TASK_STATUS", "PROJECT_ID", "ATTEMPT",
    # Runner config
    "API_TOKEN", "SERVER_URL", "PB_MCP_URL",
    # PB stage config
    "PB_ROLE_DEFINITION", "PB_ACTIONS", "PB_PROMPT_INSTRUCTIONS",
    # Agent API keys
    "GEMINI_API_KEY", "GEMINI_MODEL",
    "ANTHROPIC_API_KEY", "CLAUDE_FLAGS",
    "OPENAI_API_KEY",
    # Git identity (optional overrides)
    "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_NAME",
]


def _detect_github_repo() -> str | None:
    """Try to infer owner/repo from the current directory's git remote."""
    try:
        out = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    # https://github.com/owner/repo.git  or  git@github.com:owner/repo.git
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", out)
    return m.group(1) if m else None


def _find_docker_dir() -> Path | None:
    """Locate runner/docker/ relative to the repo root."""
    explicit = os.getenv("PB_RUNNER_PATH")
    if explicit:
        candidate = Path(explicit).parent / "docker"
        if candidate.is_dir():
            return candidate
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    candidate = repo_root / "runner" / "docker"
    if candidate.is_dir():
        return candidate
    return None


def _ensure_agent_image(
    adapter: str,
    docker_dir: Path,
    rebuild: bool = False,
    github_repo: str | None = None,
) -> str:
    """Return the Docker image name for the adapter, building it if needed.

    Pull order (when image is absent or --rebuild requested):
      1. Try ghcr.io/{owner}/pb-agent-{type}:latest  (CI-built, always up-to-date)
      2. Fall back to a local docker build from source
    """
    image = _ADAPTER_IMAGE[adapter]

    if not rebuild:
        probe = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
        )
        if probe.returncode == 0:
            return image

    # Try pulling the CI-built image from GHCR first (skip when --rebuild is forced)
    owner = github_repo.split("/")[0].lower() if github_repo else None
    if owner and not rebuild:
        remote_base = f"ghcr.io/{owner}/pb-agent-base:latest"
        remote_image = f"ghcr.io/{owner}/{image}:latest"
        typer.echo(f"Pulling {remote_image} from GHCR…")
        pull_base = subprocess.run(["docker", "pull", remote_base], capture_output=True)
        pull_img = subprocess.run(["docker", "pull", remote_image], capture_output=True)
        if pull_base.returncode == 0 and pull_img.returncode == 0:
            # Tag as the local name so docker run uses it
            subprocess.run(["docker", "tag", remote_base, "pb-agent-base"], check=True)
            subprocess.run(["docker", "tag", remote_image, image], check=True)
            typer.echo(f"Pulled {image} from GHCR.")
            return image
        typer.echo("GHCR pull failed (image may not exist yet) — building locally…")

    repo_root = docker_dir.parent.parent
    typer.echo("Building pb-agent-base (first time, this takes a minute)…")
    subprocess.run(
        ["docker", "build",
         "-f", str(docker_dir / "Dockerfile.base"),
         "-t", "pb-agent-base",
         str(repo_root)],
        check=True,
    )
    typer.echo(f"Building {image}…")
    subprocess.run(
        ["docker", "build",
         "-f", str(docker_dir / _ADAPTER_DOCKERFILE[adapter]),
         "-t", image,
         str(repo_root)],
        check=True,
    )
    return image


def _make_container_work_hook(image: str, github_repo: str) -> str:
    """Return the WORK_HOOK shell command that runs one task in a container."""
    env_flags = " ".join(f"-e {v}" for v in _CONTAINER_PASSTHROUGH)
    return (
        f"docker run --rm {env_flags} "
        f"-e GITHUB_TOKEN "               # forwarded from outer env
        f"-e GITHUB_REPO={github_repo} "
        f"-e PB_COMMUNICATION_PROTOCOL=github "
        f"-v /var/run/docker.sock:/var/run/docker.sock "
        f"{image}"
    )


def _select_agent(server: str, token: str, agent_hint: str | None) -> tuple[str, str, str, str]:
    """Resolve agent identity for a human-authenticated user.

    Returns (agent_name, agent_id, run_token, adapter).
    """
    members = request("GET", "/api/teams/members", server=server, token=token)
    agents = [m for m in members if m.get("user_type") == "agent"]
    if not agents:
        panic(code="no_agents_on_team", message="No agents on your team. Create one in the Team page first.")

    # If --agent was provided, match by name prefix or short ID
    if agent_hint:
        hint_lower = agent_hint.lower()
        matches = [
            a for a in agents
            if hint_lower in a["name"].lower() or a["id"].lower().startswith(hint_lower)
        ]
        if len(matches) == 1:
            agent = matches[0]
        elif len(matches) > 1:
            names = ", ".join(m["name"] for m in matches)
            panic(code="ambiguous_agent", message=f"Ambiguous agent '{agent_hint}': matches {names}")
        else:
            panic(code="agent_not_found", message=f"No agent matching '{agent_hint}'.")
    else:
        # Interactive selection
        typer.echo("\nAvailable agents:")
        for i, a in enumerate(agents, 1):
            desc = f" — {a['description']}" if a.get("description") else ""
            typer.echo(f"  {i}. {a['name']} ({a['adapter']}){desc}")
        typer.echo()

        choice = 0
        while not (1 <= choice <= len(agents)):
            choice = typer.prompt("Select agent", type=int)
            if not (1 <= choice <= len(agents)):
                typer.echo(f"Error: Please enter a number between 1 and {len(agents)}.", err=True)

        agent = agents[choice - 1]

    typer.echo(f"Agent: {agent['name']} ({agent['id'][:8]})")

    # Get a run token (JWT) that authenticates as the agent
    resp = request(
        "POST", f"/api/teams/agents/{agent['id']}/run-token",
        server=server, token=token,
    )
    return agent["name"], agent["id"], resp["access_token"], agent.get("adapter", "")


def run(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project", "-p", help="Project ID.")],
    agent_hint: Annotated[Optional[str], typer.Option("--agent", "-a", help="Agent name or ID (skip selection prompt).")] = None,
    interval: Annotated[int, typer.Option("--interval", help="Tick interval in seconds.")] = 60,
    once: Annotated[bool, typer.Option("--once", help="Run a single tick then exit.")] = False,
    max_concurrent: Annotated[int, typer.Option("--max-concurrent", help="Max tasks held simultaneously.")] = 1,
    work_hook: Annotated[Optional[str], typer.Option("--work-hook", help="Shell command invoked per claimed task.")] = None,
    mcp_url: Annotated[Optional[str], typer.Option("--mcp-url", envvar="PB_MCP_URL", help="MCP server URL (default: auto-derived from --server).")] = None,
    rebuild: Annotated[bool, typer.Option("--rebuild", help="Force rebuild of the agent Docker image.")] = False,
    github_repo: Annotated[Optional[str], typer.Option("--github", metavar="OWNER/REPO", help="Override the GitHub repo for container mode (owner/repo). GitHub mode is enabled automatically when the project has GitHub configured — this flag is only needed to override the repo or force-enable when auto-detection fails.")] = None,
    log_level: Annotated[str, typer.Option("--log-level", help="Logging level.")] = "INFO",
) -> None:
    """Start the collaborator runner.

    When authenticated as a human (via `pb login`), lists team agents and
    prompts you to select one.  Use --agent to skip the prompt.

    When authenticated as an agent (PB_TOKEN=pb_xxx), runs directly.

    GitHub mode (Docker container + branch + PR) is enabled automatically
    when the project has GitHub configured in settings.  Stages with
    communication_protocol=github will run in a container; other stages use
    the local adapter.  Pass --github owner/repo to override the repo.
    """
    try:
        server = ctx.obj.get("server") or config.get_server()
        token = config.get_token()
        if not token:
            panic(code="not_authenticated", message="Not authenticated. Run `pb login` first or set PB_TOKEN.")

        project_id = resolve_project(project_id, server=server)

        # Detect whether we're authenticated as an agent or a human
        adapter = ""
        if token.startswith("pb_") and agent_hint:
            # --agent provided but PB_TOKEN is an agent key; try human JWT from config file
            file_token = config.get_file_token()
            if file_token and not file_token.startswith("pb_"):
                typer.echo("Note: ignoring PB_TOKEN agent key; using login session for --agent lookup.")
                _name, agent_id, run_token, adapter = _select_agent(server, file_token, agent_hint)
            else:
                panic(
                    code="human_auth_required",
                    message="--agent requires a human login session to select a different agent, but only agent API keys were found (PB_TOKEN env and ~/.pb/config.json). Run `pb login --google` (or --github / email) to store a human JWT, then retry."
                )
        elif token.startswith("pb_"):
            # Agent API key — original flow
            typer.echo("Fetching agent config…")
            me = request("GET", "/api/teams/agents/me", server=server, token=token)
            agent_id = me["id"]
            run_token = token
            adapter = me.get("adapter", "")
            typer.echo(f"Agent: {me.get('name') or me.get('email', agent_id)} ({agent_id[:8]})")
        else:
            # Human JWT — select an agent
            _name, agent_id, run_token, adapter = _select_agent(server, token, agent_hint)

        runner_path = _find_runner()

        # Resolve GitHub config — always try, regardless of whether --github was passed.
        # Priority: explicit --github flag > GITHUB_REPO env > project API settings > git remote detection.
        env_repo = os.environ.get("GITHUB_REPO") or os.environ.get("PB_GITHUB_REPO")
        env_token = os.environ.get("GITHUB_TOKEN")

        api_repo, api_token = None, None
        try:
            resp = request("GET", f"/api/projects/{project_id}/github", server=server, token=token)
            api_repo = resp.get("repo")
            api_token = resp.get("token")
        except Exception:
            pass

        # --github with an explicit repo overrides everything; --github without a value auto-detects.
        if github_repo is not None and github_repo != "":
            resolved_repo = github_repo
        else:
            resolved_repo = env_repo or api_repo or _detect_github_repo() or ""

        resolved_token = env_token or api_token or ""

        # If --github was explicitly passed but GitHub isn't configured → hard error.
        if github_repo is not None and not resolved_token:
            panic(
                code="github_token_missing",
                message="--github requires GITHUB_TOKEN in your environment or configured in the project settings.",
            )

        # Enable container mode if GitHub is configured and adapter supports Docker.
        github_ready = bool(resolved_token and resolved_repo and adapter in _ADAPTER_IMAGE)
        if github_ready:
            if not shutil.which("docker"):
                if github_repo is not None:
                    panic(
                        code="docker_not_found",
                        message="--github requires Docker. Install it from https://docs.docker.com/get-docker/",
                    )
                typer.echo("Warning: GitHub is configured but Docker is not installed — running in WORK_HOOK mode (no PRs).", err=True)
                github_ready = False

        if github_ready:
            docker_dir = _find_docker_dir()
            if not docker_dir:
                panic(
                    code="docker_dir_not_found",
                    message="Cannot locate runner/docker/. Set PB_RUNNER_PATH or run from the project repo.",
                )
            os.environ["GITHUB_TOKEN"] = resolved_token
            _check_adapter_env(adapter)
            image = _ensure_agent_image(adapter, docker_dir, rebuild=rebuild, github_repo=resolved_repo)
            work_hook = _make_container_work_hook(image, resolved_repo)
            typer.echo(f"GitHub mode: {image} → {resolved_repo}")
        elif not work_hook and adapter:
            _check_adapter_env(adapter)
            work_hook = _resolve_adapter_hook(adapter, runner_path)
            if work_hook:
                typer.echo(f"Adapter: {adapter} (WORK_HOOK mode — no GitHub, no PRs)")
            else:
                typer.echo(f"Warning: no adapter script found for '{adapter}'")

        resolved_mcp_url = mcp_url or _derive_mcp_url(server)
        _check_mcp_health(resolved_mcp_url)
        env = {
            **os.environ,
            "SERVER_URL": server.rstrip("/"),
            "API_TOKEN": run_token,
            "PROJECT_ID": project_id,
            "AGENT_ID": str(agent_id),
            "TICK_INTERVAL": str(interval),
            "MAX_CONCURRENT": str(max_concurrent),
            "LOG_LEVEL": log_level,
            "PB_MCP_URL": resolved_mcp_url,
        }
        # Always pass GitHub config to runner so it can validate communication_protocol=github tasks.
        if resolved_token:
            env["GITHUB_TOKEN"] = resolved_token
        if resolved_repo:
            env["GITHUB_REPO"] = resolved_repo
        if work_hook:
            env["WORK_HOOK"] = work_hook

        if once:
            env["PB_RUN_ONCE"] = "1"

        typer.echo(f"Starting runner (project={project_id[:8]}, interval={interval}s)…")
        proc = subprocess.Popen([sys.executable, str(runner_path)], env=env)
        try:
            sys.exit(proc.wait())
        except KeyboardInterrupt:
            # Forward SIGINT and give the runner a few seconds to finish cleanly
            typer.echo("\nStopping runner…")
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                typer.echo("Runner did not exit in time, terminating.")
                proc.terminate()
                proc.wait(timeout=3)
            typer.echo("Runner stopped.")
            sys.exit(130)
    except APIError as e:
        if e.code == 401:
            panic(
                code="not_authenticated",
                message="Invalid or expired token. Run `pb login` to re-authenticate (or check PB_TOKEN).",
            )
        panic(code=str(e.code), message=str(e))
