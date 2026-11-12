
import csv
from pathlib import Path
from typing import Any

import typer

from imc_curator.config import get_projects_dir, load_config


MARKER_MANIFEST_SUFFIX = "marker_mapping_review.csv"
CLINICAL_MANIFEST_SUFFIX = "clinical_mapping_review.csv"

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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=headers, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def ensure_csv(
    path: Path, headers: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists() or path.stat().st_size == 0:
        write_csv(path, headers, [])
        return headers, []

    existing_headers, rows = read_csv(path)
    missing = set(headers) - set(existing_headers)
    if missing:
        raise ValueError(
            f"{path} is missing required columns: "
            f"{', '.join(sorted(missing))}"
        )
    return existing_headers, rows


def is_approved(value: str) -> bool:
    return value.strip() == "1"


def discover_manifests(
    curate_dir: Path,
    manifest_name: str,
) -> list[Path]:
    """Discover manifests in both legacy and multi-table layouts."""
    return sorted(
        {
            path
            for path in curate_dir.rglob(manifest_name)
            if path.is_file()
        },
        key=lambda path: str(path).casefold(),
    )


def check_approval(manifest_paths: list[Path]) -> list[str]:
    problems = []

    for path in manifest_paths:
        headers, rows = read_csv(path)

        if "approved" not in headers:
            raise ValueError(f"{path} has no 'approved' column")

        missing_rows = [
            str(index)
            for index, row in enumerate(rows, start=2)
            if not is_approved(row.get("approved", ""))
        ]

        if missing_rows:
            problems.append(
                f"{path}: unapproved CSV rows "
                f"{', '.join(missing_rows)}"
            )

    return problems




def _final_marker_name(
    row: dict[str, str], proceed: bool
) -> str:
    corrected = row.get("user_corrected_marker", "").strip()
    if corrected:
        return corrected

    action = row.get("action", "").strip().upper()
    suggested = row.get("suggested_standardized_marker", "").strip()

    if action in {
        "REVIEW_MATCH",
        "ADD_NEW_ENTITY",
    }:
        return suggested

    if action == "RESOLVE_AMBIGUITY" and proceed:
        return suggested

    return ""



def _final_clinical_mapping(
    row: dict[str, str], proceed: bool
) -> tuple[str, str]:
    corrected_feature = row.get("user_corrected_feature", "").strip()
    corrected_value = row.get("user_corrected_value", "").strip()

    if corrected_feature or corrected_value:
        return corrected_feature, corrected_value

    action = row.get("action", "").strip()

    if action in [
        "REVIEW_MATCH",
        "ADD_NEW_ENTITY",
    ]:
        return (
            row.get("suggested_standardized_feature", "").strip(),
            row.get("suggested_standardized_value", "").strip(),
        )

    if action == "RESOLVE_AMBIGUITY" and proceed:
        return (
            row.get("suggested_standardized_feature", "").strip(),
            row.get("suggested_standardized_value", "").strip(),
        )

    return "", ""


def _append_alias(existing: str, alias: str) -> str:
    aliases = [
        item.strip()
        for item in existing.replace("|", ";").split(";")
        if item.strip()
    ]
    if alias and alias not in aliases:
        aliases.append(alias)
    return "; ".join(aliases)


def _validate_final_mappings(
    marker_sources: list[tuple[Path, list[dict[str, str]]]],
    clinical_sources: list[tuple[Path, list[dict[str, str]]]],
    proceed: bool,
) -> None:
    errors = []

    for path, rows in marker_sources:
        for row_number, row in enumerate(rows, start=2):
            if not row.get("original_marker", "").strip():
                continue
            if not _final_marker_name(row, proceed):
                errors.append(
                    f"{path}, CSV row {row_number}: "
                    "no final standardized marker"
                )

    for path, rows in clinical_sources:
        for row_number, row in enumerate(rows, start=2):
            if not row.get("original_feature", "").strip():
                continue
            feature, value = _final_clinical_mapping(row, proceed)
            if not feature or not value:
                errors.append(
                    f"{path}, CSV row {row_number}: "
                    "no final standardized feature/value"
                )

    if errors:
        raise ValueError(
            "Some rows have no usable final mapping. Correct the manifests "
            "before finalizing:\n- " + "\n- ".join(errors)
        )


def update_global_marker_names(
    path: Path,
    manifest_rows: list[dict[str, str]],
) -> None:
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
                target.get("Aliases", ""), original
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
    headers, rows = ensure_csv(path, CLINICAL_COLUMNS)
    existing = {
        tuple(row.get(column, "").strip() for column in CLINICAL_COLUMNS)
        for row in rows
    }

    for review in manifest_rows:
        original_feature = review.get("original_feature", "").strip()
        original_value = review.get("original_value", "").strip()
        standardized_feature, standardized_value = (
            _final_clinical_mapping(review, proceed)
        )

        if not all(
            [
                original_feature,
                original_value,
                standardized_feature,
                standardized_value,
            ]
        ):
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

    rows.sort(
        key=lambda row: (
            row.get("Cohort", "").strip().casefold(),
            row.get("Standardized Feature", "").strip().casefold(),
            row.get("Standardized Value", "").strip().casefold(),
        )
    )
    write_csv(path, headers, rows)


def _panel_name_from_filename(path: Path) -> str:
    """Handle current parsed names and the older marker-parser convention."""
    name = path.name

    if name.endswith("_parsed.csv"):
        return name[:-len("_parsed.csv")]

    prefix = "markers_form_"
    suffix = "_panel_parsed.csv"
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix):-len(suffix)]

    raise ValueError(f"Cannot determine panel from filename: {name}")


def _source_key(value: str) -> str:
    """Normalize a source filename/path for manifest matching."""
    return Path(value.strip().replace("\\", "/")).name.casefold()


def _rows_for_panel(
    marker_sources: list[tuple[Path, list[dict[str, str]]]],
    extracted_path: Path,
) -> list[dict[str, str]]:
    """Find the manifest rows belonging to this extracted marker table."""
    target_name = extracted_path.name.casefold()
    target_panel = _panel_name_from_filename(extracted_path).casefold()

    explicit_matches = []
    legacy_candidates = []

    for manifest_path, rows in marker_sources:
        for row in rows:
            source_file = _source_key(row.get("source_file", ""))
            panel_id = row.get("panel_id", "").strip().casefold()

            if source_file:
                if source_file == target_name:
                    explicit_matches.append(row)
                continue

            # New per-panel manifests may be named after the panel.
            if (
                manifest_path.stem.casefold()
                in {
                    f"{target_panel}_mapping_review",
                    f"{target_panel}_marker_mapping_review",
                }
            ):
                explicit_matches.append(row)
            else:
                legacy_candidates.append(row)

    if explicit_matches:
        return explicit_matches

    # Backward compatibility: a single legacy manifest can be matched by
    # original marker + channel. Multiple legacy manifests are ambiguous.
    legacy_manifests = [
        (path, rows)
        for path, rows in marker_sources
        if path.parent == path.parents[0]
        and path.name.endswith(MARKER_MANIFEST_SUFFIX)
    ]
    if len(legacy_manifests) == 1:
        return legacy_candidates

    raise ValueError(
        f"No marker review rows found for {extracted_path.name}. "
        "Ensure the manifest contains source_file/panel_id, or is a "
        "single legacy marker_mapping_review.csv."
    )


def update_global_marker_channels(
    channel_path: Path,
    marker_names_path: Path,
    extracted_marker_files: list[Path],
    marker_sources: list[tuple[Path, list[dict[str, str]]]],
) -> None:
    _, marker_name_rows = ensure_csv(marker_names_path, MARKER_COLUMNS)
    aliases_by_marker = {
        row.get("Marker Name", "").strip():
        row.get("Aliases", "").strip()
        for row in marker_name_rows
        if row.get("Marker Name", "").strip()
    }

    panel_by_file = {
        path: _panel_name_from_filename(path)
        for path in extracted_marker_files
    }

    headers, rows = ensure_csv(
        channel_path, ["Marker Name", "Comment", "Aliases"]
    )

    for panel in sorted(set(panel_by_file.values())):
        if panel not in headers:
            headers.append(panel)
            for row in rows:
                row[panel] = ""

    by_name = {
        row.get("Marker Name", "").strip(): row
        for row in rows
        if row.get("Marker Name", "").strip()
    }

    for extracted_path, panel in panel_by_file.items():
        _, extracted_rows = read_csv(extracted_path)
        reviews = _rows_for_panel(marker_sources, extracted_path)

        for extracted in extracted_rows:
            original_marker = extracted.get("biological_marker", "").strip()
            channel_number = extracted.get("channel_number", "").strip()

            if not original_marker or not channel_number:
                continue

            matches = [
                review for review in reviews
                if review.get("original_marker", "").strip() == original_marker
                and review.get("channel_number", "").strip() == channel_number
            ]

            if len(matches) > 1:
                raise ValueError(
                    f"Ambiguous review rows for {extracted_path.name}: "
                    f"marker {original_marker!r}, channel {channel_number!r}."
                )
            if not matches:
                continue

            standardized = _final_marker_name(matches[0], proceed=True)
            if not standardized:
                continue

            if standardized not in by_name:
                new_row = {header: "" for header in headers}
                new_row["Marker Name"] = standardized
                rows.append(new_row)
                by_name[standardized] = new_row

            target = by_name[standardized]
            target["Aliases"] = aliases_by_marker.get(standardized, "")
            target[panel] = channel_number

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
    """Validate all curation manifests and update global reference files."""
    config = load_config()
    project_dir = get_projects_dir() / name
    curate_dir = project_dir / "curation_manifests" / "curate"

    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project directory not found: {project_dir}")

    marker_manifests_dir = curate_dir / "markers"
    clinical_manifests_dir = curate_dir / "clinical"
    marker_manifests = discover_manifests(
        marker_manifests_dir, 
        MARKER_MANIFEST_SUFFIX,
    )
    clinical_manifests = discover_manifests(
        clinical_manifests_dir, 
        CLINICAL_MANIFEST_SUFFIX,
    )

    if not marker_manifests:
        raise FileNotFoundError(
            f"No marker review manifests found under {curate_dir}"
        )

    # Clinical tables are optional for a cohort.
    marker_sources = [
        (path, read_csv(path)[1]) for path in marker_manifests
    ]
    clinical_sources = [
        (path, read_csv(path)[1]) for path in clinical_manifests
    ]

    # Validate all manifests that actually exist.
    problems = check_approval(marker_manifests + clinical_manifests)
    proceed = False

    if problems:
        typer.echo("These manifests still contain unapproved rows:")
        for problem in problems:
            typer.echo(f"- {problem}")
        answer = typer.prompt(
            'To continue with suggestions without approval, type "proceed"',
            default="",
            show_default=False,
        )
        if answer.strip().lower() != "proceed":
            typer.echo("Finalization cancelled.")
            raise typer.Exit(code=1)
        proceed = True

    _validate_final_mappings(marker_sources, clinical_sources, proceed)


    marker_names_path = Path(config["curation"]["global_marker_names_path"])
    marker_channels_path = Path(config["curation"]["global_marker_channels_path"])
    clinical_values_path = Path(config["curation"]["global_clinical_values_path"])

    extracted_dir = (
        project_dir / "curation_manifests" / "extract" / "markers"
    )
    extracted_marker_files = sorted(
        path for path in extracted_dir.glob("*_parsed.csv")
        if path.is_file()
    )

    if not extracted_marker_files:
        raise FileNotFoundError(
            f"No parsed marker files found under {extracted_dir}"
        )

    all_marker_rows = [
        row for _, rows in marker_sources for row in rows
    ]
    all_clinical_rows = [
        row for _, rows in clinical_sources for row in rows
    ]

    # All manifests and mappings are validated before global writes begin.
    update_global_marker_names(marker_names_path, all_marker_rows)
    update_global_clinical_values(
        clinical_values_path,
        all_clinical_rows,
        cohort=name,
        proceed=proceed,
    )
    update_global_marker_channels(
        marker_channels_path,
        marker_names_path,
        extracted_marker_files,
        marker_sources,
    )

    typer.echo(f"Finalization completed for cohort: {name}")
    typer.echo(f"Marker manifests processed: {len(marker_manifests)}")
    typer.echo(f"Clinical manifests processed: {len(clinical_manifests)}")
    typer.echo(f"Marker tables processed: {len(extracted_marker_files)}")
