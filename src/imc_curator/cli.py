import typer

from imc_curator.commands.init import init
from imc_curator.commands.curate import curate
from imc_curator.commands.validate import validate


app = typer.Typer(
    name="imc-curator",
    help="Tools for curating imaging mass cytometry datasets.",
)


app.command()(init)
app.command()(curate)
app.command()(validate)