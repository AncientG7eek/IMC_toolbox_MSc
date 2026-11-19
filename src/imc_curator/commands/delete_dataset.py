import shutil
from pathlib import Path

import pandas as pd
import typer

from imc_curator.config import (
    get_global_file_path,
    get_global_subdir,
    get_projects_dir,
    load_config,
)
from imc_curator.completion import complete_datasets


def delete_dataset(
    name: str = typer.Argument(
        ...,
        help="Project name to delete from data and global files.",
        autocompletion=complete_datasets,
    ),
) -> None:
    """Delete a project directory and its global-file references."""
    project_dir = get_projects_dir() / name
    if not project_dir.is_dir():
        raise typer.BadParameter(
            f"Project directory does not exist: {project_dir}"
        )

    confirmed = typer.confirm(
        f"Delete project '{name}' and remove it from global files?",
        default=False,
    )
    if not confirmed:
        typer.echo("Deletion cancelled.")
        raise typer.Exit(code=1)

    config = load_config()
    register_path = get_global_file_path(
        config,
        "global_image_register_file",
    )
    image_clinical_path = get_global_file_path(
        config,
        "global_image_clinical_file",
    )
    clinical_values_path = get_global_file_path(
        config,
        "global_clinical_values_file",
    )
    marker_channels_path = get_global_file_path(
        config,
        "global_marker_channels_file",
    )
    all_images_dir = get_global_subdir(
        config,
        "global_images_subdir",
    )
    split_dir = get_global_subdir(
        config,
        "global_split_subdir",
    )

    removed_global_names: set[str] = set()
    removed_relative_paths: set[str] = set()
    removed_panels: set[str] = set()
    removed_cohorts: set[str] = set()

    if register_path.is_file():
        register = pd.read_csv(register_path)
        removed_rows = register[
            register["project_name"].astype(str) == name
        ]
        removed_global_names = {
            Path(value).name
            for value in removed_rows["global_path"].dropna().astype(str)
        }
        removed_relative_paths = set(
            removed_rows["relative_path"].dropna().astype(str)
        )
        removed_panels = set(
            removed_rows["panel_name"].dropna().astype(str)
        )
        removed_cohorts = set(
            removed_rows["cohort_name"].dropna().astype(str)
        )

    if image_clinical_path.is_file():
        image_clinical = pd.read_csv(image_clinical_path)
        removed_image_rows = image_clinical[
            image_clinical["relative_path"].astype(str).str.startswith(
                f"{name}/"
            )
        ]
        removed_cohorts.update(
            removed_image_rows["Cohort"].dropna().astype(str)
        )

    shutil.rmtree(project_dir)

    if register_path.is_file():
        register = pd.read_csv(register_path)
        register = register[
            register["project_name"].astype(str) != name
        ]
        register.to_csv(register_path, index=False)

    if image_clinical_path.is_file():
        image_clinical = pd.read_csv(image_clinical_path)
        image_clinical = image_clinical[
            ~image_clinical["relative_path"].astype(str).isin(
                removed_relative_paths
            )
        ]
        image_clinical.to_csv(image_clinical_path, index=False)

    if clinical_values_path.is_file():
        remaining_cohorts = set()
        if image_clinical_path.is_file():
            image_clinical = pd.read_csv(image_clinical_path)
            remaining_cohorts = set(
                image_clinical["Cohort"].dropna().astype(str)
            )
        clinical_values = pd.read_csv(clinical_values_path)
        clinical_values = clinical_values[
            ~clinical_values["Cohort"].astype(str).isin(
                removed_cohorts - remaining_cohorts
            )
        ]
        clinical_values.to_csv(clinical_values_path, index=False)

    if marker_channels_path.is_file():
        marker_channels = pd.read_csv(marker_channels_path)
        columns_to_drop = [
            column
            for column in marker_channels.columns
            if column in removed_panels
        ]
        if columns_to_drop:
            marker_channels = marker_channels.drop(
                columns=columns_to_drop
            )
            marker_channels.to_csv(marker_channels_path, index=False)

    for directory in (all_images_dir, split_dir):
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_symlink() and path.name in removed_global_names:
                path.unlink()

    typer.echo(f"Deleted project '{name}' and its global references.")
