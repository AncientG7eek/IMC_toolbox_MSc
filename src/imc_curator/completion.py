import typer

from imc_curator.config import get_projects_dir


def complete_datasets(
    ctx: typer.Context,
    args: list[str],
    incomplete: str,
) -> list[str]:
    """Autocomplete dataset names from the package data directory."""
    
    projects_dir = get_projects_dir()

    if not projects_dir.is_dir():
        return []

    return sorted(
        directory.name
        for directory in projects_dir.iterdir()
        if directory.is_dir()
        and directory.name.startswith(incomplete)
    )
