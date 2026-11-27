import typer

from imc_curator import __version__
from imc_curator.commands.init import init
from imc_curator.commands.inspect import inspect
from imc_curator.commands.populate import populate
from imc_curator.commands.examine import examine
from imc_curator.commands.extract import extract
from imc_curator.commands.curate import curate
from imc_curator.commands.finalize import finalize
from imc_curator.commands.preprocess import preprocess
from imc_curator.commands.adapt import adapt
from imc_curator.commands.generate import generate
from imc_curator.commands.delete_dataset import delete_dataset


app = typer.Typer(
    name="imc-curator",
    help="Tools for curating imaging mass cytometry datasets.",
)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the installed version and exit.",
        is_eager=True,
    ),
) -> None:
    """Curate Imaging Mass Cytometry datasets."""
    if version:
        typer.echo(f"imc-curator {__version__}")
        raise typer.Exit()


app.command()(init)
app.command()(inspect)
app.command()(populate)
app.command()(examine)
app.command()(extract)
app.command()(curate)
app.command()(finalize)
app.command()(preprocess)
app.command()(adapt)
app.command(name="generate")(generate)
app.command(name="generate-experiment", hidden=True)(generate)
app.command()(delete_dataset)
