"""Credential and configuration storage (~/.pb/config.json)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path.home() / ".pb"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

DEFAULT_SERVER = "https://api.projectbrain.tools"


def _read_raw() -> dict[str, Any]:
    if not _CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(_CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_raw(data: dict[str, Any]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")
    # Restrict permissions to owner only
    _CONFIG_FILE.chmod(0o600)


def get_token() -> str | None:
    """Return the auth token.  PB_TOKEN env var takes precedence."""
    env = os.environ.get("PB_TOKEN")
    if env:
        return env
    return _read_raw().get("token")


def get_file_token() -> str | None:
    """Return the token stored in the config file, ignoring PB_TOKEN env var."""
    return _read_raw().get("token")


def get_server() -> str:
    """Return the API server URL."""
    env = os.environ.get("PB_SERVER")
    if env:
        return env.rstrip("/")
    return _read_raw().get("server", DEFAULT_SERVER).rstrip("/")


def save(token: str, server: str | None = None) -> None:
    """Persist token (and optional server) to config file."""
    data = _read_raw()
    data["token"] = token
    if server:
        data["server"] = server.rstrip("/")
    _write_raw(data)


def token_source() -> str | None:
    """Return where the active token comes from: 'env', 'file', or None."""
    if os.environ.get("PB_TOKEN"):
        return "env"
    if _read_raw().get("token"):
        return "file"
    return None


def clear() -> None:
    """Remove stored credentials."""
    if _CONFIG_FILE.exists():
        _CONFIG_FILE.unlink()
