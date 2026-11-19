import typer

from imc_curator.config import get_projects_dir


MODEL_NAMES = ["immuvis"]


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


def complete_models(
    ctx: typer.Context,
    args: list[str],
    incomplete: str,
) -> list[str]:
    """Autocomplete registered model names."""
    return [
        name
        for name in MODEL_NAMES
        if name.startswith(incomplete)
    ]
