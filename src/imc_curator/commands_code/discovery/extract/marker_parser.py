import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from imc_curator.commands_code.discovery.signature import (
    build_panel_id,
    build_panel_signature,
    format_panel_signature,
)
from imc_curator.commands_code.discovery.extract.panel_map import (
    append_panel_map_rows,
    project_relative,
    selected_panel_file,
)

if TYPE_CHECKING:
    from imc_curator.progress_bar import ProgressManager


REVIEW_COLUMN = "KEEP/REJECT [0/1]"

PANEL_COLUMNS = [
    "biological_marker",
    "channel_number",
    "metal_isotope",
]


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


def _scalar(value: object) -> object:
    """Convert pandas NA values to plain empty strings for CSV output."""
    if pd.isna(value):
        return ""
    return value


def extract_marker_tables(
    project_dir: Path,
    forms_dir: Path,
    selected_panels_dir: Path | None = None,
    panel_map_path: Path | None = None,
    progress: "ProgressManager | None" = None,
) -> str:
    """
    Parse marker-panel tables using their completed TOML forms
    and KEEP/REJECT review columns.
    """
    project_dir = project_dir.resolve()
    forms_dir = _resolve_path(str(forms_dir), project_dir)
    if selected_panels_dir is not None:
        selected_panels_dir = _resolve_path(
            str(selected_panels_dir),
            project_dir,
        )
        selected_panels_dir.mkdir(parents=True, exist_ok=True)
    if panel_map_path is not None:
        panel_map_path = _resolve_path(str(panel_map_path), project_dir)

    form_paths = sorted(forms_dir.glob("*/*.toml"))

    if not form_paths:
        return f"No marker TOML forms found in:\n  {forms_dir}"

    assignments_path = forms_dir / "assign_images_to_panels.toml"
    images_by_marker: dict[str, list[str]] = {}
    if assignments_path.is_file():
        assignments = _read_form(assignments_path)
        raw_mapping = assignments.get("images_by_marker", {})
        if isinstance(raw_mapping, dict):
            images_by_marker = {
                str(marker_file): [
                    str(image_path)
                    for image_path in image_paths
                ]
                for marker_file, image_paths in raw_mapping.items()
            }

    reports = [
        "",
        "MARKER EXTRACTION",
        f"Found {len(form_paths)} marker form(s):",
    ]

    form_iterable = (
        progress.track(
            form_paths,
            description="Parsing marker forms",
            total=len(form_paths),
            item_description=lambda path: path.name,
        )
        if progress
        else form_paths
    )

    for form_path in form_iterable:
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

        if not review_csv.is_file():
            raise FileNotFoundError(
                f"Review CSV specified by {form_path} was not found:\n"
                f"  {review_csv}"
            )

        marker_table = pd.read_csv(review_csv)

        if not marker_column and "biological_marker" in marker_table.columns:
            marker_column = "biological_marker"
        if not channel_column and "channel_number" in marker_table.columns:
            channel_column = "channel_number"
        if not metal_column and "metal_isotope" in marker_table.columns:
            metal_column = "metal_isotope"

        if not marker_column:
            raise ValueError(
                f"{form_path}: biological_marker_column is required."
            )

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
            # First data row -> 1, second data row -> 2, etc.
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

        if parsed_table.empty:
            parsed_table["panel_id"] = ""
            parsed_table["panel_signature"] = ""
        else:
            signature_channels = []
            for _, row in parsed_table.iterrows():
                signature_channels.append(
                    {
                        "channel_number": row.get("channel_number", 0),
                        "raw_name": row.get(marker_column, ""),
                        "raw_fluor": row.get("metal_isotope", ""),
                        "biological_marker": row.get("biological_marker", ""),
                        "metal_ion": row.get("metal_isotope", ""),
                    }
                )

            signature = build_panel_signature(
                signature_channels,
                marker_key="biological_marker",
                raw_name_key="raw_name",
                raw_fluor_key="raw_fluor",
            )
            panel_id = build_panel_id(signature)
            panel_signature = format_panel_signature(signature)

            parsed_table["panel_id"] = panel_id
            parsed_table["panel_signature"] = panel_signature

        if selected_panels_dir is not None and not parsed_table.empty:
            panel_rows = []
            for _, row in parsed_table.iterrows():
                marker = _scalar(row.get("biological_marker", ""))
                panel_rows.append(
                    {
                        "biological_marker": marker,
                        "channel_number": _scalar(
                            row.get("channel_number", "")
                        ),
                        "metal_isotope": _scalar(
                            row.get("metal_isotope", "")
                        ),
                    }
                )

            panel_path = selected_panels_dir / f"{panel_id}.csv"
            pd.DataFrame(panel_rows, columns=PANEL_COLUMNS).to_csv(
                panel_path,
                index=False,
            )

            if panel_map_path is not None:
                source_key = f"{form_path.parent.name}.csv"
                image_paths = images_by_marker.get(source_key, [])
                map_rows = []

                for image_path in image_paths:
                    map_rows.append(
                        {
                            "tiff_file": project_relative(
                                image_path,
                                project_dir,
                            ),
                            "panel_id": panel_id,
                            "panel_signature": panel_signature,
                            "panel_file": selected_panel_file(
                                selected_panels_dir,
                                panel_id,
                                project_dir,
                            ),
                        }
                    )

                if map_rows:
                    append_panel_map_rows(panel_map_path, map_rows)

        reports.extend(
            [
                f"Form: {form_path.resolve()}",
                f"Review CSV: {review_csv.resolve()}",
                f"Markers retained: {len(parsed_table)}",
                f"Markers rejected: {(decisions == 0).sum()}",
            ]
        )
        if selected_panels_dir is not None and not parsed_table.empty:
            reports.append(f"Selected panel: {panel_path.resolve()}")
        if panel_map_path is not None and not parsed_table.empty:
            reports.append(f"Images mapped: {len(image_paths)}")

    return "\n".join(reports)
