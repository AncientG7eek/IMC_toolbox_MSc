from pathlib import Path

import typer

from imc_curator.config import load_config
from imc_curator.progress_bar import ProgressManager
from imc_curator.services.processing.preprocess import (
    load_preprocess_config,
    preprocess_config_path,
    preprocess_registered_images,
    write_default_preprocess_config,
)


def preprocess(
    config_file: Path = typer.Option(
        None,
        "--config",
        help=(
            "TOML preprocessing config. Defaults to preprocessing.toml "
            "in the curated database."
        ),
    ),
    dataset: list[str] = typer.Option(
        None,
        "--dataset",
        help=(
            "Only process these panels. Repeat the option for multiple "
            "panels."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing preprocessed images.",
    ),
) -> None:
    """Apply the curated-database preprocessing config to all images."""
    config = load_config()
    resolved_config_path = preprocess_config_path(
        config,
        config_file,
    )

    if not resolved_config_path.is_file():
        write_default_preprocess_config(resolved_config_path)
        typer.echo(
            "Wrote default preprocessing config to "
            f"{resolved_config_path}"
        )

    preprocess_config = load_preprocess_config(
        resolved_config_path
    )

    with ProgressManager() as progress:
        result = preprocess_registered_images(
            config,
            preprocess_config,
            datasets=dataset,
            force=force,
            progress=progress,
        )

    typer.echo(result.report)
