import typer

from imc_curator.services.curation.finalize.finalize import finalizer
from imc_curator.completion import complete_datasets
from imc_curator.progress_bar import ProgressManager

def finalize(
    name: str = typer.Argument(
        ...,
        help="Name of the cohort project to finalize the curation process of.",
        autocompletion=complete_datasets,
    ),
) -> None:
    """Finalizes the curation process of the dataset. 
    The global clinical and marker metadata tables 
    on the cohort and panel levels get appended with 
    information from this curation project."""

    with ProgressManager() as progress:
        with progress.stage("Finalizing project"):
            finalizer(name=name)
