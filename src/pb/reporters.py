"""Handles output formatting for the CLI (text, JSON)."""

import json
import click
import typer

def render(data):
    """Render data to stdout, respecting the --json flag."""
    ctx = click.get_current_context()
    if ctx.obj.get("json"):
        print(json.dumps({"ok": True, "data": data}, indent=2))
    else:
        # For now, just print the raw data.
        # A more sophisticated version would format this for human readability.
        if isinstance(data, list):
            for item in data:
                print(item)
        elif isinstance(data, dict):
            for key, value in data.items():
                print(f"{key}: {value}")
        else:
            print(data)

def panic(code: str, message: str):
    """Render a fatal error and exit."""
    ctx = click.get_current_context()
    if ctx.obj.get("json"):
        print(json.dumps({"ok": False, "error": {"code": code, "message": message}}, indent=2))
    else:
        typer.secho(f"Error [{code}]: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)
