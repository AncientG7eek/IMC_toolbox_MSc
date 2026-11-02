from pathlib import Path

import typer


PACKAGE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PACKAGE_DIR / "data" / "cohorts"


def complete_datasets(
    ctx: typer.Context,
    args: list[str],
    incomplete: str,
) -> list[str]:
    """Autocomplete dataset names from the package data directory."""
    
    if not DATA_DIR.is_dir():
        return []

    return sorted(
        directory.name
        for directory in DATA_DIR.iterdir()
        if directory.is_dir()
        and directory.name.startswith(incomplete)
    )