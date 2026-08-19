from pathlib import Path

import typer

from imc_curator.config import get_projects_dir
from imc_curator.download import download
from imc_curator.project import create_project


def init(
    url: str = typer.Option(..., help="URL of the dataset archive"),
    name: str = typer.Option(..., help="Name of the dataset"),
):
    """Download and initialize a new IMC dataset project."""

    projects_dir = get_projects_dir()

    project_dir = create_project(
        name=name,
        path=projects_dir,
    )

    archive = project_dir / "data" / "raw" / "dataset.zip"

    download(url, archive)

    typer.echo(f"Project created: {project_dir}")