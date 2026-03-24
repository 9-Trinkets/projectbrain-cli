"""pb login / logout / whoami commands."""

from __future__ import annotations
import typer
from typing import Optional
from typing_extensions import Annotated


import socket
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from pb import config
from pb.client import request, request_unauth, APIError
from pb.reporters import render, panic


# Fixed port so the redirect URI can be pre-registered in OAuth provider settings.
# Override with PB_OAUTH_PORT if 8085 conflicts.
_DEFAULT_OAUTH_PORT = 8085


def _get_oauth_port() -> int:
    import os
    return int(os.environ.get("PB_OAUTH_PORT", str(_DEFAULT_OAUTH_PORT)))


# ---------------------------------------------------------------------------
# OAuth callback page — styled to match the ProjectBrain dark UI.
# Tokens: brand warm gold #A88450, warm neutral slate, Lora + Plus Jakarta Sans.
# ---------------------------------------------------------------------------
_CALLBACK_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ProjectBrain — Logged In</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@400&family=Plus+Jakarta+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    min-height:100vh;
    display:flex;
    align-items:center;
    justify-content:center;
    background:#0A0A0B;
    color:#E8E3DA;
    font-family:'Plus Jakarta Sans',system-ui,sans-serif;
    line-height:1.65;
    letter-spacing:.01em;
  }
  .card {
    text-align:center;
    padding:48px 40px;
    background:#1A1714;
    border:1px solid #272420;
    border-radius:16px;
    max-width:420px;
    width:90%;
  }
  .icon {
    width:56px; height:56px;
    margin:0 auto 20px;
    background:#A88450;
    border-radius:50%;
    display:flex;
    align-items:center;
    justify-content:center;
  }
  .icon svg { width:28px; height:28px; fill:none; stroke:#fff; stroke-width:2.5; stroke-linecap:round; stroke-linejoin:round; }
  h1 {
    font-family:'Lora',serif;
    font-weight:400;
    font-size:26px;
    line-height:1.25;
    margin-bottom:8px;
  }
  p {
    color:#8A8580;
    font-size:15px;
  }
  .tag {
    display:inline-block;
    margin-top:24px;
    padding:6px 14px;
    font-size:12px;
    font-weight:500;
    letter-spacing:.04em;
    text-transform:uppercase;
    color:#C8A570;
    background:#261E15;
    border-radius:6px;
  }
</style>
</head>
<body>
  <div class="card">
    <div class="icon">
      <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
    </div>
    <h1>Logged in</h1>
    <p>You can close this tab and return to the terminal.</p>
    <span class="tag">ProjectBrain CLI</span>
  </div>
</body>
</html>
"""


def _run_oauth_callback_server(port: int) -> str | None:
    """Start a one-shot HTTP server to capture the OAuth code."""
    captured: dict[str, str | None] = {"code": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            qs = parse_qs(urlparse(self.path).query)
            captured["code"] = qs.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = _CALLBACK_HTML
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, *_args: object) -> None:
            pass  # silence request logs

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 120  # 2 minutes
    server.handle_request()
    server.server_close()
    return captured["code"]


def login(
    ctx: typer.Context,
    token_value: Annotated[Optional[str], typer.Option("--token", help="API token (pb_xxx or JWT).")] = None,
    use_google: Annotated[bool, typer.Option("--google", help="Login with Google (opens browser).")] = False,
    use_github: Annotated[bool, typer.Option("--github", help="Login with GitHub (opens browser).")] = False,
) -> None:
    """Authenticate with ProjectBrain."""
    server = ctx.obj.get("server")

    try:
        if token_value:
            # Token-based login — validate by calling /api/auth/me
            # Warn if overwriting a human JWT with an agent key
            existing = config.get_file_token()
            if (
                token_value.startswith("pb_")
                and existing
                and not existing.startswith("pb_")
            ):
                typer.echo(
                    "Warning: overwriting human login session with an agent API key. "
                    "Features like `pb run --agent` require human auth."
                )
            config.save(token_value, server)
            try:
                user = request("GET", "/api/auth/me", server=server, token=token_value)
            except APIError:
                config.clear()
                panic(code="invalid_token", message="Invalid token — could not authenticate.")
            render(user)
            return

        if use_google:
            _login_oauth(server, provider="google")
            return

        if use_github:
            _login_oauth(server, provider="github")
            return

        # Interactive email/password login
        email = typer.prompt("Email")
        password = typer.prompt("Password", hide_input=True)
        data = request_unauth(
            "POST",
            "/api/auth/login",
            json_body={"email": email, "password": password},
            server=server,
        )
        token = data["access_token"]
        config.save(token, server)

        # Fetch identity to confirm
        user = request("GET", "/api/auth/me", server=server, token=token)
        render(user)
    except APIError as e:
        panic(code=e.code, message=str(e))


_OAUTH_CONFIG = {
    "google": {
        "env_var": "PB_GOOGLE_CLIENT_ID",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "scope": "openid%20email%20profile",
        "extra_params": "&access_type=offline&prompt=select_account",
        "api_path": "/api/auth/google",
    },
    "github": {
        "env_var": "PB_GITHUB_CLIENT_ID",
        "auth_url": "https://github.com/login/oauth/authorize",
        "scope": "read:user%20user:email",
        "extra_params": "",
        "api_path": "/api/auth/github",
    },
}


def _login_oauth(server: str | None, provider: str) -> None:
    """Browser-based OAuth flow (Google or GitHub)."""
    import os
    cfg = _OAUTH_CONFIG[provider]

    try:
        client_id = os.environ.get(cfg["env_var"])
        if not client_id:
            try:
                providers = request_unauth("GET", "/api/auth/providers", server=server)
                client_id = (providers.get(provider) or {}).get("client_id")
            except APIError:
                pass # Fail over to the panic below
        if not client_id:
            panic(
                code="oauth_config_missing",
                message=f"{provider.title()} client ID not found. Set {cfg['env_var']} or deploy the /providers endpoint."
            )

        port = _get_oauth_port()
        redirect_uri = f"http://localhost:{port}/callback"

        params = (
            f"client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope={cfg['scope']}"
            f"{cfg['extra_params']}"
        )
        url = f"{cfg['auth_url']}?{params}"

        typer.echo(f"Opening browser for {provider.title()} login...")
        webbrowser.open(url)
        typer.echo("Waiting for callback (press Ctrl+C to cancel)...")

        code = _run_oauth_callback_server(port)
        if not code:
            panic(code="oauth_cancelled", message="No authorization code received. Login cancelled.")

        data = request_unauth(
            "POST",
            cfg['api_path'],
            json_body={"code": code, "redirect_uri": redirect_uri},
            server=server,
        )
        token = data["access_token"]
        config.save(token, server)

        user = request("GET", "/api/auth/me", server=server, token=token)
        render(user)
    except APIError as e:
        panic(code=e.code, message=str(e))


def whoami(ctx: typer.Context) -> None:
    """Show current authenticated identity."""
    server = ctx.obj.get("server")
    try:
        user = request("GET", "/api/auth/me", server=server)
        if ctx.obj.get("json"):
            render(user)
        else:
            typer.echo(f"{user['name']} <{user['email']}>")
            typer.echo(f"  ID:   {user['id']}")
            typer.echo(f"  Type: {user['user_type']}")
            src = config.token_source()
            source = "PB_TOKEN" if src == "env" else "~/.pb/config.json"
            typer.echo(f"  Auth: {source}")
    except APIError as e:
        panic(code=e.code, message=str(e))


def logout() -> None:
    """Clear stored credentials."""
    config.clear()
    typer.echo("Logged out.")
