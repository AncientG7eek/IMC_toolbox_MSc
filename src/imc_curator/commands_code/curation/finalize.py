
import csv
from pathlib import Path
from typing import Any

import typer

from imc_curator.config import get_projects_dir, load_config


MARKER_MANIFEST = "marker_mapping_review.csv"
CLINICAL_MANIFEST = "clinical_mapping_review.csv"

CLINICAL_COLUMNS = [
    "Standardized Feature",
    "Standardized Value",
    "Cohort",
    "Original Feature",
    "Original Value",
]

MARKER_COLUMNS = ["Marker Name", "Comment", "Aliases"]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV and return its header and rows."""
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")

        headers = [header.strip() for header in reader.fieldnames]
        rows = [
            {
                (key or "").strip(): (value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            for row in reader
        ]

    return headers, rows


def write_csv(
    path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
) -> None:
    """Write CSV rows while preserving the specified column order."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=headers,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def ensure_csv(path: Path, headers: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Create a missing reference file, or read the existing one."""
    if not path.exists() or path.stat().st_size == 0:
        write_csv(path, headers, [])
        return headers, []

    existing_headers, rows = read_csv(path)

    missing = set(headers) - set(existing_headers)
    if missing:
        raise ValueError(
            f"{path} is missing required columns: {', '.join(sorted(missing))}"
        )

    return existing_headers, rows


def is_approved(value: str) -> bool:
    return value.strip() == "1"


def check_approval(
    manifest_paths: list[Path],
) -> list[str]:
    """Return a report of manifests containing unapproved rows."""
    problems = []

    for path in manifest_paths:
        _, rows = read_csv(path)
        if not rows:
            continue

        if "approved" not in rows[0]:
            raise ValueError(f"{path} has no 'approved' column")

        # CSV row numbering includes the header, so first data row is row 2.
        missing_rows = [
            str(index)
            for index, row in enumerate(rows, start=2)
            if not is_approved(row.get("approved", ""))
        ]

        if missing_rows:
            problems.append(
                f"{path.name} lacks approval for CSV rows: "
                f"{', '.join(missing_rows)}"
            )

    return problems


def _final_marker_name(row: dict[str, str], proceed: bool) -> str:
    """Resolve the final standardized marker name from a review row."""
    corrected = row.get("user_corrected_marker", "").strip()
    if corrected:
        return corrected

    action = row.get("action", "").strip()

    if action == "REVIEW_MATCH":
        return row.get("suggested_standardized_marker", "").strip()

    if action == "ADD_NEW_ENTITY":
        return row.get("proposed_new_standardized_marker", "").strip()

    if action == "RESOLVE_AMBIGUITY" and proceed:
        return row.get("suggested_standardized_marker", "").strip()

    return ""


def _final_clinical_mapping(
    row: dict[str, str],
    proceed: bool,
) -> tuple[str, str]:
    """Resolve final standardized clinical feature and value."""
    corrected_feature = row.get("user_corrected_feature", "").strip()
    corrected_value = row.get("user_corrected_value", "").strip()

    if corrected_feature or corrected_value:
        return corrected_feature, corrected_value

    action = row.get("action", "").strip()

    if action == "REVIEW_MATCH":
        return (
            row.get("suggested_standardized_feature", "").strip(),
            row.get("suggested_standardized_value", "").strip(),
        )

    if action == "ADD_NEW_ENTITY":
        return (
            row.get("proposed_new_standardized_feature", "").strip(),
            row.get("proposed_new_standardized_value", "").strip(),
        )

    if action == "RESOLVE_AMBIGUITY" and proceed:
        return (
            row.get("suggested_standardized_feature", "").strip(),
            row.get("suggested_standardized_value", "").strip(),
        )

    return "", ""


def _append_alias(existing: str, alias: str) -> str:
    """Append an alias only if it is not already present."""
    aliases = [
        item.strip()
        for item in existing.replace("|", ";").split(";")
        if item.strip()
    ]

    if alias and alias not in aliases:
        aliases.append(alias)

    return "; ".join(aliases)


def _validate_final_mappings(
    marker_rows: list[dict[str, str]],
    clinical_rows: list[dict[str, str]],
    proceed: bool,
) -> None:
    """Reject rows that still have no usable final mapping."""
    errors = []

    for row_number, row in enumerate(marker_rows, start=2):
        if not row.get("original_marker", "").strip():
            continue

        if not _final_marker_name(row, proceed):
            errors.append(
                f"Marker manifest CSV row {row_number}: "
                f"no final standardized marker"
            )

    for row_number, row in enumerate(clinical_rows, start=2):
        if not row.get("original_feature", "").strip():
            continue

        feature, value = _final_clinical_mapping(row, proceed)
        if not feature or not value:
            errors.append(
                f"Clinical manifest CSV row {row_number}: "
                f"no final standardized feature/value"
            )

    if errors:
        raise ValueError(
            "Some rows have no usable final mapping. Please correct the "
            "manifest before finalizing:\n- " + "\n- ".join(errors)
        )


def update_global_marker_names(
    path: Path,
    manifest_rows: list[dict[str, str]],
) -> None:
    """Update marker names and append original names to Aliases."""
    headers, rows = ensure_csv(path, MARKER_COLUMNS)

    by_name = {
        row.get("Marker Name", "").strip(): row
        for row in rows
        if row.get("Marker Name", "").strip()
    }

    for review in manifest_rows:
        original = review.get("original_marker", "").strip()
        standardized = _final_marker_name(review, proceed=True)

        if not original or not standardized:
            continue

        if standardized not in by_name:
            new_row = {header: "" for header in headers}
            new_row["Marker Name"] = standardized
            new_row["Aliases"] = original
            rows.append(new_row)
            by_name[standardized] = new_row
        else:
            target = by_name[standardized]
            target["Aliases"] = _append_alias(
                target.get("Aliases", ""),
                original,
            )

    rows.sort(
        key=lambda row: row.get("Marker Name", "").strip().casefold()
    )

    write_csv(path, headers, rows)


def update_global_clinical_values(
    path: Path,
    manifest_rows: list[dict[str, str]],
    cohort: str,
    proceed: bool,
) -> None:
    """Append approved clinical mappings for this cohort."""
    headers, rows = ensure_csv(path, CLINICAL_COLUMNS)

    existing = {
        (
            row.get("Standardized Feature", "").strip(),
            row.get("Standardized Value", "").strip(),
            row.get("Cohort", "").strip(),
            row.get("Original Feature", "").strip(),
            row.get("Original Value", "").strip(),
        )
        for row in rows
    }

    for review in manifest_rows:
        original_feature = review.get("original_feature", "").strip()
        original_value = review.get("original_value", "").strip()

        standardized_feature, standardized_value = _final_clinical_mapping(
            review, proceed
        )

        if not all([
            original_feature,
            original_value,
            standardized_feature,
            standardized_value,
        ]):
            continue

        record = (
            standardized_feature,
            standardized_value,
            cohort,
            original_feature,
            original_value,
        )

        if record in existing:
            continue

        rows.append(dict(zip(headers, record)))
        existing.add(record)

    # Sort by cohort, then standardized feature, then standardized value.
    rows.sort(
        key=lambda row: (
            row.get("Cohort", "").strip().casefold(),
            row.get("Standardized Feature", "").strip().casefold(),
            row.get("Standardized Value", "").strip().casefold(),
        )
    )

    write_csv(path, headers, rows)


def _panel_name_from_filename(path: Path) -> str:
    """Derive panel name from markers_form_<panel>_panel_parsed.csv."""
    prefix = "markers_form_"
    suffix = "_panel_parsed.csv"
    name = path.name

    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix):-len(suffix)]

    raise ValueError(
        f"Cannot determine panel name from marker filename: {path.name}"
    )


def update_global_marker_channels(
    channel_path: Path,
    marker_names_path: Path,
    extracted_marker_files: list[Path],
    manifest_rows: list[dict[str, str]],
) -> None:
    """
    Update panel channel assignments in the global marker-channel reference.

    Marker Name is the standardized marker name. The Aliases column is copied
    from the global marker-name reference. Each panel gets a separate column.
    """
    marker_headers, marker_name_rows = ensure_csv(
        marker_names_path, MARKER_COLUMNS
    )

    aliases_by_marker = {
        row.get("Marker Name", "").strip():
        row.get("Aliases", "").strip()
        for row in marker_name_rows
        if row.get("Marker Name", "").strip()
    }

    panels = {
        _panel_name_from_filename(path)
        for path in extracted_marker_files
    }

    headers, rows = ensure_csv(
        channel_path,
        ["Marker Name", "Comment", "Aliases"],
    )

    # Add any new panel columns without removing existing columns.
    for panel in sorted(panels):
        if panel not in headers:
            headers.append(panel)
            for row in rows:
                row[panel] = ""

    by_name = {
        row.get("Marker Name", "").strip(): row
        for row in rows
        if row.get("Marker Name", "").strip()
    }

    # Associate review rows with each extracted file using marker/channel
    # information. Channel number is taken from the extracted CSV.
    for extracted_path in extracted_marker_files:
        panel = _panel_name_from_filename(extracted_path)
        _, extracted_rows = read_csv(extracted_path)

        for extracted in extracted_rows:
            original_marker = extracted.get("biological_marker", "").strip()
            channel_number = extracted.get("channel_number", "").strip()

            if not original_marker or not channel_number:
                continue

            matching_reviews = [
                review
                for review in manifest_rows
                if review.get("original_marker", "").strip() == original_marker
                and review.get("channel_number", "").strip() == channel_number
            ]

            if not matching_reviews:
                continue

            standardized = _final_marker_name(matching_reviews[0], proceed=True)
            if not standardized:
                continue

            if standardized not in by_name:
                new_row = {header: "" for header in headers}
                new_row["Marker Name"] = standardized
                new_row["Aliases"] = aliases_by_marker.get(standardized, "")
                rows.append(new_row)
                by_name[standardized] = new_row

            target = by_name[standardized]
            target["Aliases"] = aliases_by_marker.get(standardized, "")
            target[panel] = channel_number

    # Sort rows alphabetically by standardized marker name.
    rows.sort(
        key=lambda row: row.get("Marker Name", "").strip().casefold()
    )

    write_csv(channel_path, headers, rows)


def finalizer(
    name: str = typer.Argument(
        ...,
        help="Name of the cohort project to finalize.",
    ),
) -> None:
    """Validate curation approvals and update global reference files."""
    config = load_config()
    project_dir = get_projects_dir() / name
    curate_dir = project_dir / "curation_manifests" / "curate"

    marker_manifest_path = curate_dir / MARKER_MANIFEST
    clinical_manifest_path = curate_dir / CLINICAL_MANIFEST

    for path in [marker_manifest_path, clinical_manifest_path]:
        if not path.exists():
            raise FileNotFoundError(f"Curation manifest not found: {path}")

    problems = check_approval([
        marker_manifest_path,
        clinical_manifest_path,
    ])

    proceed = False
    if problems:
        typer.echo("These files still have rows without approval:")
        for problem in problems:
            typer.echo(f"- {problem}")

        typer.echo(
            "\nPlease review the rows and put 1 in the approved column."
        )
        answer = typer.prompt(
            'To continue with suggestions without approval, type "proceed"',
            default="",
            show_default=False,
        )

        if answer.strip().lower() != "proceed":
            typer.echo("Finalization cancelled.")
            raise typer.Exit(code=1)

        proceed = True

    _, marker_rows = read_csv(marker_manifest_path)
    _, clinical_rows = read_csv(clinical_manifest_path)

    # Even with "proceed", rows must resolve to usable final names.
    _validate_final_mappings(marker_rows, clinical_rows, proceed)

    marker_names_path = Path(
        config["curation"]["global_marker_names_path"]
    )
    marker_channels_path = Path(
        config["curation"]["global_marker_channels_path"]
    )
    clinical_values_path = Path(
        config["curation"]["global_clinical_values_path"]
    )

    extracted_marker_files = sorted(
        (
            project_dir
            / "curation_manifests"
            / "extract"
            / "markers"
        ).glob("markers_form_*_panel_parsed.csv")
    )

    if not extracted_marker_files:
        raise FileNotFoundError(
            "No extracted marker files found under "
            f"{project_dir / 'curation_manifests' / 'extract' / 'markers'}"
        )

    # Validate all inputs before making the global updates.
    update_global_marker_names(marker_names_path, marker_rows)

    update_global_clinical_values(
        clinical_values_path,
        clinical_rows,
        cohort=name,
        proceed=proceed,
    )

    update_global_marker_channels(
        marker_channels_path,
        marker_names_path,
        extracted_marker_files,
        marker_rows,
    )

    typer.echo(f"Finalization completed for cohort: {name}")
