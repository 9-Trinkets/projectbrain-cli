"""pb projects commands."""

from __future__ import annotations
from typing_extensions import Annotated

import typer

from rich.console import Console
from rich.table import Table

from pb.client import request, APIError
from pb.reporters import render, panic

app = typer.Typer()


@app.command("list")
def list_projects(ctx: typer.Context) -> None:
    """List all projects."""
    try:
        data = request("GET", "/api/projects/", server=ctx.obj.get("server"))
        if ctx.obj.get("json"):
            render(data)
            return

        if not data:
            typer.echo("No projects found.")
            return
        table = Table(show_header=True, header_style="bold")
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("Name")
        table.add_column("Description", max_width=50)
        for p in data:
            table.add_row(p["id"][:8], p["name"], p.get("description") or "—")
        Console().print(table)
    except APIError as e:
        panic(code=e.code, message=str(e))


@app.command("get")
def get_project(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Argument(help="The project ID to get.")],
) -> None:
    """Show project details and summary."""
    try:
        data = request("GET", f"/api/projects/{project_id}/summary", server=ctx.obj.get("server"))
        if ctx.obj.get("json"):
            render(data)
            return
            
        p = data.get("project", data)
        typer.echo(f"{p['name']}")
        if p.get("description"):
            typer.echo(f"  {p['description']}")
        typer.echo()

        tc = data.get("task_counts", {})
        if tc:
            parts = [f"{k}: {v}" for k, v in tc.items() if v]
            typer.echo(f"  Tasks: {', '.join(parts)}")

        milestones = data.get("milestones", [])
        if milestones:
            done = sum(1 for m in milestones if m.get("status") == "completed")
            typer.echo(f"  Milestones: {done}/{len(milestones)} completed")
    except APIError as e:
        panic(code=e.code, message=str(e))
