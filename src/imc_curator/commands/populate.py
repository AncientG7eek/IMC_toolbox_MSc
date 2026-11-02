import typer

from imc_curator.config import get_projects_dir, load_search_config
from imc_curator.commands_code.discovery.populate.load_report import load_manifest
from imc_curator.commands_code.discovery.populate.populate import materialize_category
from imc_curator.completion import complete_datasets


SEARCH_CATEGORIES = set(
    load_search_config()["categories"]
)


def populate(
    name: str = typer.Argument(
        ...,
        help="Name of the cohort project to inspect.",
        autocompletion=complete_datasets,
    ),
) -> None:
    
    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    manifest = load_manifest(project_dir=project_dir, command="inspect")
    inputs = manifest.get("inputs", {})

    raw_dir = project_dir / "data" / "raw" / "source"

    if not isinstance(inputs, dict):
        raise typer.BadParameter(
            "The manifest's [inputs] section must be a table."
        )
    
    for category, entries in inputs.items():
        if category == "unclassified" or not entries:
            continue

        if category not in SEARCH_CATEGORIES:
            continue

        if not isinstance(entries, list):
            raise typer.BadParameter(
                f"Inputs for category {category!r} must be a list."
            )

        for entry in entries:
            if isinstance(entry, dict):
                if not isinstance(entry.get("path"), str):
                    raise typer.BadParameter(
                        f"Manifest entry in {category!r} must have "
                        "a string 'path' field."
                    )

        materialize_category(
            project_dir=project_dir,
            raw_dir=raw_dir,
            category=category,
            entries=entries,
        )

    typer.echo(
        f"Successfully populated {name} project"
    )