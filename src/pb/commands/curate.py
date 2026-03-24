"""pb curate — project-level memory curator settings."""

from __future__ import annotations
from typing_extensions import Annotated

import typer

from pb.client import request, resolve_project, APIError
from pb.reporters import render, panic

app = typer.Typer()


@app.command("enable")
def enable_curate(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project", "-p", help="Project ID.")],
) -> None:
    """Enable curation for a project."""
    server = ctx.obj.get("server")
    try:
        project_id = resolve_project(project_id, server=server)
        data = request(
            "PATCH",
            f"/api/projects/{project_id}",
            json_body={"curation_enabled": True},
            server=server,
        )
        render(data)
    except APIError as e:
        panic(code=e.code, message=str(e))


@app.command("disable")
def disable_curate(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project", "-p", help="Project ID.")],
) -> None:
    """Disable curation for a project."""
    server = ctx.obj.get("server")
    try:
        project_id = resolve_project(project_id, server=server)
        data = request(
            "PATCH",
            f"/api/projects/{project_id}",
            json_body={"curation_enabled": False},
            server=server,
        )
        render(data)
    except APIError as e:
        panic(code=e.code, message=str(e))


@app.command("status")
def curate_status(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Option("--project", "-p", help="Project ID.")],
) -> None:
    """Show curation status for a project."""
    server = ctx.obj.get("server")
    try:
        project_id = resolve_project(project_id, server=server)
        data = request("GET", f"/api/projects/{project_id}", server=server)
        render(data)
    except APIError as e:
        panic(code=e.code, message=str(e))
