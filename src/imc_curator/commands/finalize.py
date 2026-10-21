import typer

from imc_curator.commands_code.curation.finalize import finalizer

def finalize(
    name: str = typer.Argument(
        ...,
        help="Name of the cohort project to finalize the curation process of.",
    ),
) -> None:
    """Finalizes the curation process of the dataset. 
    The global clinical and marker metadata tables 
    on the cohort and panel levels get appended with 
    information from this curation project."""

    finalizer(name=name)