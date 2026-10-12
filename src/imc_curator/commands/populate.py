from pathlib import Path

import typer

from imc_curator.config import get_projects_dir
from imc_curator.curation.load_report import load_manifest
from imc_curator.curation.populate import (
    materialize_category
)


def populate(
    name: str = typer.Argument(...),
):
    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    manifest = load_manifest(project_dir)
    inputs = manifest.get("inputs", {})

    raw_dir = project_dir / "data" / "raw" / "source"

    for category, paths in inputs.items():
        if not paths:
            continue

        materialize_category(
            project_dir=project_dir,
            raw_dir=raw_dir,
            category=category,
            paths=paths,
        )

    typer.echo(
        f"Successfully populated {name} project"
    )