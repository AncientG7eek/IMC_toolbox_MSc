import re
import tomllib
from pathlib import Path

import pandas as pd


REVIEW_COLUMN = "KEEP/REJECT [0/1]"


def _resolve_path(path: str, project_dir: Path) -> Path:
    """Resolve a path relative to the project unless it is absolute."""
    path = Path(path)

    if path.is_absolute():
        return path

    return project_dir / path


def _extract_value(value: object, pattern: str, field_name: str) -> object:
    """Extract a value with a regex, or return the original value."""
    if pd.isna(value):
        return pd.NA

    value = str(value).strip()

    if not pattern:
        return value

    match = re.search(pattern, value)

    if match is None:
        raise ValueError(
            f"Could not extract {field_name} from {value!r} "
            f"using regex {pattern!r}."
        )

    # Use the first capture group when one is provided.
    if match.lastindex:
        return match.group(1)

    return match.group(0)


def _read_form(form_path: Path) -> dict:
    """Read a TOML form."""
    with form_path.open("rb") as form_file:
        return tomllib.load(form_file)


def extract_marker_tables(
    project_dir: Path,
    forms_dir: Path,
    output_dir: Path,
) -> str:
    """
    Parse marker-panel tables using their completed TOML forms
    and KEEP/REJECT review columns.
    """
    project_dir = project_dir.resolve()
    forms_dir = _resolve_path(str(forms_dir), project_dir)
    output_dir = _resolve_path(str(output_dir), project_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    form_paths = sorted(forms_dir.glob("*.toml"))

    if not form_paths:
        return f"No marker TOML forms found in:\n  {forms_dir}"

    reports = [
        "",
        "MARKER EXTRACTION",
        f"Found {len(form_paths)} marker form(s):",
    ]

    for form_path in form_paths:
        form = _read_form(form_path)

        source_config = form.get("source", {})
        parsing_config = form.get("marker_parsing", {})

        review_csv = _resolve_path(
            source_config["review_csv"],
            project_dir,
        )

        marker_column = parsing_config.get(
            "biological_marker_column", ""
        )
        channel_column = parsing_config.get(
            "channel_number_column", ""
        )
        metal_column = parsing_config.get(
            "metal_isotope_column", ""
        )

        marker_regex = parsing_config.get(
            "biological_marker_regex", ""
        )
        metal_regex = parsing_config.get(
            "metal_isotope_regex", ""
        )

        if not marker_column:
            raise ValueError(
                f"{form_path}: biological_marker_column is required."
            )

        if not review_csv.is_file():
            raise FileNotFoundError(
                f"Review CSV specified by {form_path} was not found:\n"
                f"  {review_csv}"
            )

        marker_table = pd.read_csv(review_csv)

        if marker_column not in marker_table.columns:
            raise ValueError(
                f"{form_path}: marker column {marker_column!r} "
                f"was not found in {review_csv.name}. "
                f"Available columns: {list(marker_table.columns)}"
            )

        if REVIEW_COLUMN not in marker_table.columns:
            raise ValueError(
                f"{review_csv} is missing the required column "
                f"{REVIEW_COLUMN!r}."
            )

        for column in (channel_column, metal_column):
            if column and column not in marker_table.columns:
                raise ValueError(
                    f"{form_path}: configured column {column!r} "
                    f"was not found in {review_csv.name}."
                )

        decisions = pd.to_numeric(
            marker_table[REVIEW_COLUMN],
            errors="coerce",
        )

        invalid_decisions = decisions.isna() | ~decisions.isin([0, 1])

        if invalid_decisions.any():
            invalid_rows = (
                marker_table.index[invalid_decisions] + 2
            ).tolist()

            raise ValueError(
                f"{review_csv}: {REVIEW_COLUMN!r} must contain "
                f"only 0 or 1. Check CSV rows {invalid_rows}."
            )

        # Retain rows explicitly marked 1.
        parsed_table = marker_table.loc[decisions == 1].copy()

        # Add standardized parsed columns while preserving original data.
        parsed_table["biological_marker"] = parsed_table[
            marker_column
        ].map(
            lambda value: _extract_value(
                value,
                marker_regex,
                "biological marker",
            )
        )

        if channel_column:
            parsed_table["channel_number"] = parsed_table[channel_column]
        else:
            # Generate channel numbers from the original table row positions.
            # First data row -> 0, second data row -> 1, etc.
            parsed_table["channel_number"] = (
                parsed_table.index - marker_table.index.min()
            )

        if metal_column:
            parsed_table["metal_isotope"] = parsed_table[
                metal_column
            ].map(
                lambda value: _extract_value(
                    value,
                    metal_regex,
                    "metal isotope",
                )
            )
        else:
            parsed_table["metal_isotope"] = pd.NA

        output_path = (
            output_dir / f"{form_path.stem.removesuffix('_form')}_parsed.csv"
        )

        parsed_table.to_csv(output_path, index=False)

        reports.extend(
            [
                f"Form: {form_path.resolve()}",
                f"Review CSV: {review_csv.resolve()}",
                f"Markers retained: {len(parsed_table)}",
                f"Markers rejected: {(decisions == 0).sum()}",
                f"Parsed output: {output_path.resolve()}",
            ]
        )

    return "\n".join(reports)