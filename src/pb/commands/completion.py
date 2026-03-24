"""Show shell completion scripts."""
import typer
import os
from typer import completion

app = typer.Typer(
    help="Show shell completion scripts. To install, add the output to your shell's startup file.",
)

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    shell: str = typer.Option(
        os.environ.get("SHELL", "").split("/")[-1],
        "--shell",
        "-s",
        help="The shell to generate completions for.",
        autocompletion=lambda: ["bash", "zsh", "fish", "powershell", "pwsh"],
    ),
    install: bool = typer.Option(
        False,
        "--install",
        help="Install completions for the current shell.",
    ),
):
    """
    Manage shell completions.
    """
    if ctx.invoked_subcommand is not None:
        return

    prog_name = os.environ.get("PB_PROG_NAME", "pb")
    if install:
        typer.echo(f"Installing completions for {shell}...")
        completion.install(shell=shell, prog_name=prog_name)
        raise typer.Exit()
    else:
        script = completion.get_completion_script(prog_name=prog_name, complete_var=f"_{prog_name.upper()}_COMPLETE", shell=shell)
        typer.echo(script)
        raise typer.Exit()
