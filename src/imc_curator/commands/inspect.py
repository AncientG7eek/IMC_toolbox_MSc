from pathlib import Path

import typer

from imc_curator.config import get_projects_dir
from imc_curator.commands_code.discovery.report import write_manifest
from imc_curator.commands_code.discovery.scanner import discover
from imc_curator.file_tree_plotting import save_manifest_tree



def inspect(
    name: str = typer.Argument(
        ...,
        help="Name of the cohort project to inspect.",
    ),
):
    """Inspect the source dataset and generate a manifest."""

    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    if not project_dir.exists():
        raise typer.BadParameter(
            f"Project does not exist: {project_dir}"
        )

    source_dir = (
        project_dir
        / "data"
        / "raw"
        / "source"
    )

    if not source_dir.exists():
        raise typer.BadParameter(
            f"Source dataset not found: {source_dir}"
        )

    typer.echo(
        f"Inspecting dataset: {source_dir}"
    )
    typer.echo("")

    suggestions = discover(
        source_dir=source_dir, 
        project_dir=project_dir,
    )

    typer.echo("Discovery results:")
    typer.echo("")

    for category, files in suggestions.items():
        typer.echo(f"{category}:")

        if not files:
            typer.echo("  (none)")
        else:
            for file in files:
                typer.echo(f"  - {file}")

        typer.echo("")

    manifest_path = write_manifest(
        project_dir=project_dir,
        project_name=name,
        suggestions=suggestions,
    )

    typer.echo(
        f"Manifest written to:\n  {manifest_path}"
    )

    tree_path = save_manifest_tree(
        manifest_path=manifest_path,
        project_dir=project_dir,
    )

    typer.echo(
        f"Manifest file tree written to:\n  {tree_path}"
    )

    typer.echo("")
    typer.echo(
        "Review and edit the manifest before "
        "running validation."
    )