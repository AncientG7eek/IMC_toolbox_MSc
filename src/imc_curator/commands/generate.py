from pathlib import Path
import tomllib

import pandas as pd
import typer
import yaml

from imc_curator.config import get_curated_file_path, load_config


def _filter_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _load_filter_file(path: Path) -> dict[str, list[str]]:
    if path.suffix.lower() == ".toml":
        with path.open("rb") as file:
            data = tomllib.load(file)
    else:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}

    filters = data.get("filters", data)
    return {
        "cohort": _filter_values(filters.get("cohort")),
        "feature": _filter_values(filters.get("feature")),
        "value": _filter_values(filters.get("value")),
    }


def generate(
    config_file: Path = typer.Option(
        None,
        "--config",
        help="TOML/YAML file with cohort/feature/value filters.",
    ),
    cohort: str = typer.Option(
        "",
        "--cohort",
        help="Comma-separated Cohort filter.",
    ),
    feature: str = typer.Option(
        "",
        "--feature",
        help="Filter by Standardized Feature column.",
    ),
    value: str = typer.Option(
        "",
        "--value",
        help="Filter by Standardized Value column.",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output CSV path for the filtered experiment.",
    ),
) -> None:
    """Filter curated image-clinical data into an experiment CSV."""
    config = load_config()
    path = get_curated_file_path(
        config,
        "global_image_clinical_file",
    )

    table = pd.read_csv(path)

    filters = {
        "cohort": [],
        "feature": [],
        "value": [],
    }
    if config_file is not None:
        filters.update(_load_filter_file(config_file))
    if cohort.strip():
        filters["cohort"] = _filter_values(cohort)
    if feature.strip():
        filters["feature"] = _filter_values(feature)
    if value.strip():
        filters["value"] = _filter_values(value)

    column_by_filter = {
        "cohort": "Cohort",
        "feature": "Standardized Feature",
        "value": "Standardized Value",
    }
    for key, values in filters.items():
        if not values:
            continue
        column = column_by_filter[key]
        table = table[table[column].astype(str).isin(values)]

    output.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output, index=False)

    typer.echo(f"Wrote {len(table)} rows to {output}")
