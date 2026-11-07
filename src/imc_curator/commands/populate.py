import typer
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

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
        help="Name of the cohort project to populate.",
        autocompletion=complete_datasets,
    ),
) -> None:
    
    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    inputs = load_manifest(project_dir=project_dir, command="inspect")
    
    raw_dir = project_dir / "data" / "raw" / "source"

    # Collect categories that actually need to be populated.
    categories_to_populate = [
        (category, entries)
        for category, entries in inputs.items()
        if category != "unclassified"
        and category in SEARCH_CATEGORIES
        and entries
    ]

    # Count the total number of entries.
    total_files = sum(
        len(entries)
        for _, entries in categories_to_populate
    )

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:

        task = progress.add_task(
            "Populating project...",
            total=total_files,
        )

        for category, entries in inputs.items():
            if category == "unclassified" or not entries:
                continue

            if category not in SEARCH_CATEGORIES:
                continue
                
            materialize_category(
                project_dir=project_dir,
                raw_dir=raw_dir,
                category=category,
                entries=entries,
                progress=progress,
                task_id=task,
            )

    typer.echo(
        f"Successfully populated {name} project"
    )