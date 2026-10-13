from pathlib import Path
import shutil
from imc_curator.config import load_search_config

SEARCH_CONFIG = load_search_config()

def materialize_file(
    source: Path,
    destination: Path,
) -> Path:
    """Copy a file into the curated project structure."""

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(source, destination)

    return destination


def materialize_directory(
    source: Path,
    destination: Path,
) -> Path:
    """Copy a directory into the curated project structure."""

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
    )

    return destination

def get_category_config(category: str) -> dict:
    return SEARCH_CONFIG["categories"][category]

def materialize_category(
    project_dir: Path,
    raw_dir: Path,
    category: str,
    paths: list[str],
):
    config = SEARCH_CONFIG["categories"][category]

    destination = (
        project_dir / config["destination"]
    )

    for relative_path in paths:
        source = raw_dir / relative_path

        if not source.exists():
            raise RuntimeError(
                f"Input does not exist: {source}"
            )

        if source.is_dir():
            materialize_directory(
                source,
                destination / source.name,
            )
        else:
            materialize_file(
                source,
                destination / source.name,
            )