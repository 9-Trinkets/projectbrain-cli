"""Sync httpx client for the ProjectBrain API."""

from __future__ import annotations

from typing import Any

import httpx
import click  # Keep for other potential uses, though we're replacing ClickException

from pb import config


class APIError(Exception):
    """Custom exception for API errors."""
    def __init__(self, detail: str, code: int | None = None):
        self.detail = detail
        self.code = code
        super().__init__(self.detail)

    def __str__(self):
        if self.code:
            return f"API error ({self.code}): {self.detail}"
        return self.detail


def _make_client(server: str | None = None, token: str | None = None) -> httpx.Client:
    base = server or config.get_server()
    tok = token or config.get_token()
    if not tok:
        raise APIError(
            "Not authenticated. Run `pb login` first or set PB_TOKEN."
        )
    return httpx.Client(
        base_url=base,
        headers={"Authorization": f"Bearer {tok}"},
        timeout=30.0,
    )


def _handle_error(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        body = resp.json()
        detail = body.get("detail", body)
    except Exception:
        detail = resp.text or f"HTTP {resp.status_code}"
    if isinstance(detail, list):
        detail = "; ".join(
            d.get("msg", str(d)) if isinstance(d, dict) else str(d)
            for d in detail
        )
    raise APIError(detail=str(detail), code=resp.status_code)


def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    server: str | None = None,
    token: str | None = None,
) -> Any:
    """Make an authenticated API request and return parsed JSON."""
    with _make_client(server, token) as client:
        resp = client.request(method, path, params=params, json=json_body)
    _handle_error(resp)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


def resolve_project(value: str, *, server: str | None = None) -> str:
    """Resolve a project identifier to a UUID.

    Accepts a full UUID, a short UUID prefix (e.g. first 8 chars),
    or a project name (case-insensitive substring match).
    Raises APIError if no match or ambiguous.
    """
    import re
    # Full UUID — return as-is
    if re.match(r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$", value, re.I):
        return value

    projects = request("GET", "/api/projects/", server=server)

    # Short hex prefix (e.g. "a84c4871") — match against ID start
    if re.match(r"^[0-9a-f]+$", value, re.I) and len(value) >= 4:
        prefix = value.lower()
        matches = [p for p in projects if p["id"].lower().startswith(prefix)]
        if len(matches) == 1:
            return matches[0]["id"]
        if len(matches) > 1:
            names = ", ".join(f"{m['name']} ({m['id'][:8]})" for m in matches)
            raise APIError(f"Ambiguous ID prefix '{value}' — matches: {names}.")
        # Fall through to name search

    # Name search (case-insensitive substring)
    needle = value.lower()
    matches = [p for p in projects if needle in p["name"].lower()]
    if len(matches) == 1:
        return matches[0]["id"]
    if len(matches) == 0:
        raise APIError(f"No project matching '{value}'. Run `pb projects list` to see available projects.")
    names = ", ".join(m["name"] for m in matches)
    raise APIError(f"Ambiguous project name '{value}' — matches: {names}. Use the full UUID.")


def request_unauth(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    server: str | None = None,
) -> Any:
    """Make an unauthenticated API request (for login)."""
    base = server or config.get_server()
    with httpx.Client(base_url=base, timeout=30.0) as client:
        resp = client.request(method, path, json=json_body)
    _handle_error(resp)
    return resp.json()
