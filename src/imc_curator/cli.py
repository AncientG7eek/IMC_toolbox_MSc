import typer

from imc_curator.commands.init import init
from imc_curator.commands.inspect import inspect
from imc_curator.commands.populate import curate



app = typer.Typer(
    name="imc-curator",
    help="Tools for curating imaging mass cytometry datasets.",
)


app.command()(init)
app.command()(inspect)
app.command()(curate)
