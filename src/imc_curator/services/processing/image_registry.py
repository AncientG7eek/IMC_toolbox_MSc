"""Helpers for reading and resolving the curated image register."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from imc_curator.config import (
    get_curated_file_path,
    get_workspace_dir,
    resolve_projects_dir,
)


REGISTER_COLUMNS = {
    "global_path",
    "relative_path",
    "panel_name",
}


def text_value(value: object) -> str:
    """Return a stripped string, treating pandas missing values as empty."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def load_image_register(config: dict) -> pd.DataFrame:
    """Load the curated image register."""
    register_path = get_curated_file_path(
        config,
        "global_image_register_file",
    )

    if not register_path.is_file():
        raise FileNotFoundError(
            f"Image register not found: {register_path}"
        )

    table = pd.read_csv(register_path)
    missing_columns = REGISTER_COLUMNS - set(table.columns)

    if missing_columns:
        raise ValueError(
            "Image register is missing columns: "
            f"{', '.join(sorted(missing_columns))}"
        )

    return table


def resolve_registered_image(
    row: dict,
    config: dict,
) -> Path | None:
    """Resolve one register row to an existing image file."""
    global_path = text_value(row.get("global_path"))
    relative_path = text_value(row.get("relative_path"))

    candidates: list[Path] = []

    if global_path:
        path = Path(global_path).expanduser()
        if not path.is_absolute():
            path = get_workspace_dir(config) / path
        candidates.append(path)

    if relative_path:
        candidates.append(resolve_projects_dir(config) / relative_path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    return None


def build_dataset_image_map(
    config: dict,
    datasets: list[str],
) -> tuple[dict[str, list[Path]], dict[str, str]]:
    """Map dataset/panel names to existing images from the register."""
    try:
        table = load_image_register(config)
    except (FileNotFoundError, ValueError) as exc:
        return {}, {"register": str(exc)}

    canonical_by_casefold = {
        dataset.casefold(): dataset
        for dataset in datasets
    }
    images_by_dataset: dict[str, list[Path]] = {}
    diagnostics: dict[str, str] = {}

    for row in table.to_dict(orient="records"):
        panel_name = text_value(row.get("panel_name"))
        dataset = canonical_by_casefold.get(panel_name.casefold())

        if dataset is None:
            continue

        image_path = resolve_registered_image(row, config)

        if image_path is None:
            diagnostics.setdefault(
                dataset,
                "Could not resolve "
                f"{text_value(row.get('relative_path')) or text_value(row.get('global_path'))!r}",
            )
            continue

        bucket = images_by_dataset.setdefault(dataset, [])
        if image_path not in bucket:
            bucket.append(image_path)

    return images_by_dataset, diagnostics
