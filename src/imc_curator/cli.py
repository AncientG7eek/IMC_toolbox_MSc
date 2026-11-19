import typer

from imc_curator.commands.init import init
from imc_curator.commands.inspect import inspect
from imc_curator.commands.populate import populate
from imc_curator.commands.examine import examine
from imc_curator.commands.extract import extract
from imc_curator.commands.curate import curate
from imc_curator.commands.finalize import finalize
from imc_curator.commands.adapt import adapt
from imc_curator.commands.generate_experiment import generate_experiment
from imc_curator.commands.delete_dataset import delete_dataset


app = typer.Typer(
    name="imc-curator",
    help="Tools for curating imaging mass cytometry datasets.",
)


app.command()(init)
app.command()(inspect)
app.command()(populate)
app.command()(examine)
app.command()(extract)
app.command()(curate)
app.command()(finalize)
app.command()(adapt)
app.command()(generate_experiment)
app.command()(delete_dataset)
