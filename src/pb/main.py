"""ProjectBrain CLI entry point."""

from __future__ import annotations
from typing import Optional

import typer
from typing_extensions import Annotated

from pb import __version__
from pb.commands import auth, curate, knowledge, projects, tasks, run, completion, backfill_embeddings


app = typer.Typer()


def version_callback(value: bool):
    if value:
        print(f"pb version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    use_json: Annotated[bool, typer.Option("--json", help="Output raw JSON.")] = False,
    server: Annotated[Optional[str], typer.Option("--server", envvar="PB_SERVER", help="API server URL override.")] = None,
    version: Annotated[Optional[bool], typer.Option("--version", callback=version_callback, is_eager=True)] = None,
):
    """ProjectBrain CLI — manage projects, tasks, and agents."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json
    if server:
        ctx.obj["server"] = server
    ctx.obj["app"] = app


app.command()(auth.login)
app.command()(auth.logout)
app.command()(auth.whoami)
app.add_typer(knowledge.app, name="knowledge")
app.add_typer(projects.app, name="projects")
app.command()(run.run)
app.add_typer(tasks.app, name="tasks")
app.add_typer(curate.app, name="curate")
app.add_typer(completion.app, name="completion")
app.command("backfill-embeddings")(backfill_embeddings.main)


if __name__ == "__main__":
    app()
