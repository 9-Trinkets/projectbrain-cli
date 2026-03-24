"""pb knowledge commands — facts, decisions, skills."""

from __future__ import annotations
from typing_extensions import Annotated
from typing import Optional
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table

from pb.client import request, resolve_project, APIError
from pb.reporters import render, panic

class KnowledgeType(str, Enum):
    fact = "fact"
    decision = "decision"
    skill = "skill"

_ENDPOINT_MAP = {
    "fact": "facts",
    "decision": "decisions",
    "skill": "skills",
}

app = typer.Typer()


@app.command("list")
def list_knowledge(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project", "-p", help="Project ID.")],
    ktype: Annotated[Optional[KnowledgeType], typer.Option("--type", "-t", help="Filter by knowledge type. Lists all types when omitted.")] = None,
    search: Annotated[Optional[str], typer.Option("--search", "-q", help="Search query.")] = None,
    category: Annotated[Optional[str], typer.Option("--category", help="Filter by category (facts & skills).")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max results per type.")] = 50,
) -> None:
    """List knowledge items for a project."""
    server = ctx.obj.get("server")
    try:
        project_id = resolve_project(project_id, server=server)
        types_to_query = [ktype.value] if ktype else list(_ENDPOINT_MAP.keys())
        all_items: list[tuple[str, dict]] = []

        for t in types_to_query:
            endpoint = _ENDPOINT_MAP[t]
            params: dict[str, str | int] = {"limit": limit}
            if search:
                params["q"] = search
            if category and t in ("fact", "skill"):
                params["category"] = category
            data = request("GET", f"/api/projects/{project_id}/{endpoint}", params=params, server=server)
            items = data.get("items", data) if isinstance(data, dict) else data
            for item in (items or []):
                all_items.append((t, item))

        render_data = [{"type": t, **item} for t, item in all_items]

        if ctx.obj.get("json"):
            render(render_data)
            return

        if not all_items:
            typer.echo("No knowledge items found.")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("ID", style="dim", no_wrap=True, max_width=8)
        table.add_column("Type", width=10)
        table.add_column("Title", min_width=20)
        table.add_column("Category", width=14)
        for t, item in all_items:
            table.add_row(
                item["id"][:8],
                t,
                item["title"],
                item.get("category") or "—",
            )
        Console().print(table)
    except APIError as e:
        panic(code=e.code, message=str(e))


@app.command("get")
def get_knowledge(
    ctx: typer.Context,
    item_id: Annotated[str, typer.Argument(help="The ID of the item to get.")],
    ktype: Annotated[KnowledgeType, typer.Option("--type", "-t", help="Knowledge type.")],
) -> None:
    """Show a single knowledge item."""
    try:
        endpoint = _ENDPOINT_MAP[ktype.value]
        data = request("GET", f"/api/{endpoint}/{item_id}", server=ctx.obj.get("server"))
        render(data)
    except APIError as e:
        panic(code=e.code, message=str(e))


@app.command("create")
def create_knowledge(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project", "-p", help="Project ID.")],
    ktype: Annotated[KnowledgeType, typer.Option("--type", "-t", help="Knowledge type.")],
    title: Annotated[str, typer.Option("--title", help="Title.")],
    body: Annotated[Optional[str], typer.Option("--body", help="Body text (or rationale for decisions).")] = None,
    category: Annotated[Optional[str], typer.Option("--category", help="Category (facts & skills).")] = None,
    tags: Annotated[Optional[str], typer.Option("--tags", help="Comma-separated tags (skills only).")] = None,
    task_id: Annotated[Optional[str], typer.Option("--task-id", help="Related task ID (decisions only).")] = None,
) -> None:
    """Create a knowledge item."""
    try:
        endpoint = _ENDPOINT_MAP[ktype.value]
        project_id = resolve_project(project_id, server=ctx.obj.get("server"))
        payload: dict = {"title": title}

        if ktype.value == "decision":
            if body:
                payload["rationale"] = body
            if task_id:
                payload["task_id"] = task_id
        else:
            if body:
                payload["body"] = body
            if category:
                payload["category"] = category
            if tags and ktype.value == "skill":
                payload["tags"] = [t.strip() for t in tags.split(",")]

        data = request(
            "POST",
            f"/api/projects/{project_id}/{endpoint}",
            json_body=payload,
            server=ctx.obj.get("server"),
        )
        render(data)
    except APIError as e:
        panic(code=e.code, message=str(e))
