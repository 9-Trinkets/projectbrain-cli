"""pb tasks commands."""

from __future__ import annotations
from typing_extensions import Annotated
from typing import Optional

import typer

from rich.console import Console
from rich.table import Table

from pb.client import request, resolve_project, APIError
from pb.reporters import render, panic

app = typer.Typer()

STATUS_COLORS = {
    "todo": "white",
    "in_progress": "magenta",
    "blocked": "red",
    "done": "green",
    "cancelled": "yellow",
}


@app.command("list")
def list_tasks(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project", "-p", help="Project ID.")],
    status: Annotated[Optional[str], typer.Option("--status", "-s", help="Filter by status.")] = None,
    assignee: Annotated[Optional[str], typer.Option("--assignee", help="Filter by assignee ID.")] = None,
    search: Annotated[Optional[str], typer.Option("--search", "-q", help="Search query.")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max results.")] = 50,
) -> None:
    """List tasks for a project."""
    try:
        project_id = resolve_project(project_id, server=ctx.obj.get("server"))
        params: dict[str, str | int] = {"limit": limit}
        if status:
            params["status"] = status
        if assignee:
            params["assignee_id"] = assignee
        if search:
            params["q"] = search

        data = request("GET", f"/api/projects/{project_id}/tasks", params=params, server=ctx.obj.get("server"))
        items = data.get("items", data) if isinstance(data, dict) else data

        if ctx.obj.get("json"):
            render(data)
            return

        if not items:
            typer.echo("No tasks found.")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("ID", style="dim", no_wrap=True, max_width=8)
        table.add_column("Status", width=12)
        table.add_column("Pri", width=6)
        table.add_column("Title", min_width=20)
        for t in items:
            sid = t["id"][:8]
            status_str = t["status"]
            color = STATUS_COLORS.get(status_str, "white")
            table.add_row(
                sid,
                f"[{color}]{status_str}[/{color}]",
                t.get("priority") or "—",
                t["title"],
            )
        Console().print(table)
    except APIError as e:
        panic(code=e.code, message=str(e))


@app.command("get")
def get_task(
    ctx: typer.Context,
    task_id: Annotated[str, typer.Argument(help="The task ID to get.")],
) -> None:
    """Show task details and context."""
    try:
        data = request("GET", f"/api/tasks/{task_id}/context", server=ctx.obj.get("server"))
        if ctx.obj.get("json"):
            render(data)
            return

        t = data.get("task", data)
        typer.echo(f"{t['title']}")
        typer.echo(f"  ID:       {t['id']}")
        typer.echo(f"  Status:   {t['status']}")
        if t.get("priority"):
            typer.echo(f"  Priority: {t['priority']}")
        if t.get("description"):
            typer.echo(f"  Description: {t['description']}")
        if t.get("assignee_id"):
            typer.echo(f"  Assignee: {t['assignee_id']}")

        deps = data.get("blocked_by", [])
        if deps:
            typer.echo("  Blocked by:")
            for d in deps:
                typer.echo(f"    - [{d['status']}] {d['title']}")
    except APIError as e:
        panic(code=e.code, message=str(e))


@app.command("create")
def create_task(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project", "-p", help="Project ID.")],
    title: Annotated[str, typer.Option("--title", "-t", help="Task title.")],
    description: Annotated[Optional[str], typer.Option("--description", "-d", help="Task description.")] = None,
    status: Annotated[str, typer.Option("--status", "-s", help="Initial status.")] = "todo",
    priority: Annotated[Optional[str], typer.Option("--priority", help="Priority (low/medium/high/critical).")] = None,
    milestone: Annotated[Optional[str], typer.Option("--milestone", help="Milestone ID.")] = None,
    assignee: Annotated[Optional[str], typer.Option("--assignee", help="Assignee user ID.")] = None,
) -> None:
    """Create a new task."""
    try:
        project_id = resolve_project(project_id, server=ctx.obj.get("server"))
        payload: dict = {"title": title, "status": status}
        if description:
            payload["description"] = description
        if priority:
            payload["priority"] = priority
        if milestone:
            payload["milestone_id"] = milestone
        if assignee:
            payload["assignee_id"] = assignee

        data = request("POST", f"/api/projects/{project_id}/tasks", json_body=payload, server=ctx.obj.get("server"))
        render(data)
    except APIError as e:
        panic(code=e.code, message=str(e))


@app.command("update")
def update_task(
    ctx: typer.Context,
    task_id: Annotated[str, typer.Argument(help="The task ID to update.")],
    status: Annotated[Optional[str], typer.Option("--status", "-s", help="New status.")] = None,
    title: Annotated[Optional[str], typer.Option("--title", "-t", help="New title.")] = None,
    priority: Annotated[Optional[str], typer.Option("--priority", help="New priority.")] = None,
    assignee: Annotated[Optional[str], typer.Option("--assignee", help="Assignee user ID (use 'none' to clear).")] = None,
) -> None:
    """Update a task."""
    try:
        payload: dict = {}
        if status:
            payload["status"] = status
        if title:
            payload["title"] = title
        if priority:
            payload["priority"] = priority
        if assignee is not None:
            payload["assignee_id"] = None if assignee.lower() == "none" else assignee

        if not payload:
            panic(code="nothing_to_update", message="Nothing to update. Provide at least one option.")

        data = request("PATCH", f"/api/tasks/{task_id}", json_body=payload, server=ctx.obj.get("server"))
        render(data)
    except APIError as e:
        panic(code=e.code, message=str(e))
