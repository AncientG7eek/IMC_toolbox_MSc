
import csv
import shutil
from pathlib import Path
from typing import Any

import tifffile
import typer

from imc_curator.config import (
    get_global_file_path,
    get_global_subdir,
    get_projects_dir,
    get_raw_source_dir,
    load_config,
)


MARKER_MANIFEST_SUFFIX = "marker_mapping_review.csv"
CLINICAL_MANIFEST_SUFFIX = "clinical_mapping_review.csv"

CLINICAL_COLUMNS = [
    "Standardized Feature",
    "Standardized Value",
    "Cohort",
    "Original Feature",
    "Original Value",
]

IMAGE_CLINICAL_COLUMNS = [
    "global_path",
    "relative_path",
    "Cohort",
    "Standardized Feature",
    "Standardized Value",
]

IMAGE_REGISTER_COLUMNS = [
    "global_path",
    "relative_path",
    "shape",
    "panel_name",
    "cohort_name",
    "project_name",
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
    manifest_suffix: str,
) -> list[Path]:
    """Discover manifests in both legacy and multi-table layouts."""
    return sorted(
        {
            path
            for path in curate_dir.rglob(f"*{manifest_suffix}")
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
    existing_cohorts = {
        row.get("Cohort", "").strip().casefold()
        for row in rows
        if row.get("Cohort", "").strip()
    }
    reused_cohorts: list[str] = []

    for review in manifest_rows:
        original_feature = review.get("original_feature", "").strip()
        original_value = review.get("original_value", "").strip()
        review_cohort = review.get("cohort", "").strip() or cohort
        if (
            review_cohort.casefold() in existing_cohorts
            and review_cohort not in reused_cohorts
        ):
            reused_cohorts.append(review_cohort)
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
            review_cohort,
            original_feature,
            original_value,
        )
        if record in existing:
            continue

        rows.append(dict(zip(headers, record)))
        existing.add(record)

    rows.sort(
        key=lambda row: (
            row.get("Standardized Feature", "").strip().casefold(),
            row.get("Standardized Value", "").strip().casefold(),
            row.get("Cohort", "").strip().casefold(),
        )
    )
    write_csv(path, headers, rows)

    if reused_cohorts:
        typer.echo(
            "Following clinical cohort names were already taken by "
            "existing cohorts in the global files:"
        )
        typer.echo(", ".join(reused_cohorts))
        typer.echo(
            "Please go back to the examine manifest, rename the cohort "
            "and redo the following steps."
        )


def update_global_image_clinical(
    path: Path,
    match_files: list[Path],
    clinical_sources: list[tuple[Path, list[dict[str, str]]]],
    project_name: str,
    relative_images_dir: str,
    proceed: bool,
) -> None:
    headers, rows = ensure_csv(path, IMAGE_CLINICAL_COLUMNS)
    headers = list(IMAGE_CLINICAL_COLUMNS)
    rows = [
        {column: row.get(column, "") for column in headers}
        for row in rows
    ]
    existing = {
        tuple(row.get(column, "").strip() for column in IMAGE_CLINICAL_COLUMNS)
        for row in rows
    }

    reviews_by_source: dict[str, list[dict[str, str]]] = {}
    for _, review_rows in clinical_sources:
        for review in review_rows:
            source_file = review.get("source_file", "").strip()
            if source_file:
                reviews_by_source.setdefault(source_file, []).append(review)

    for match_file in match_files:
        cohort = match_file.stem.removesuffix("_image_clinical_matches")
        review_rows = reviews_by_source.get(match_file.name, [])
        review_map = {}

        for review in review_rows:
            feature, value = _final_clinical_mapping(review, proceed)
            original_feature = review.get("original_feature", "").strip()
            original_value = review.get("original_value", "").strip()
            if not feature or not value or not original_feature:
                continue
            key = (original_feature.casefold(), original_value.casefold())
            review_map[key] = (feature, value)

        _, match_rows = read_csv(match_file)
        for match_row in match_rows:
            image = match_row.get("image_path", "").strip()
            if not image:
                continue

            for column, value in match_row.items():
                if column in {"image_path", "image_name", "image_id"}:
                    continue
                value = value.strip()
                if not value:
                    continue
                key = (column.casefold(), value.casefold())
                mapping = review_map.get(key)
                if mapping is None:
                    continue

                record = {
                    "global_path": "",
                    "relative_path": f"{project_name}/{image}",
                    "Cohort": cohort,
                    "Standardized Feature": mapping[0],
                    "Standardized Value": mapping[1],
                }
                record_key = tuple(
                    record[column] for column in IMAGE_CLINICAL_COLUMNS
                )
                if record_key not in existing:
                    rows.append(record)
                    existing.add(record_key)

    rows.sort(
        key=lambda row: (
            row.get("Cohort", "").strip().casefold(),
            row.get("relative_path", "").strip().casefold(),
            row.get("Standardized Feature", "").strip().casefold(),
            row.get("Standardized Value", "").strip().casefold(),
        )
    )
    write_csv(path, headers, rows)


def update_global_image_register(
    register_path: Path,
    all_images_dir: Path,
    project_dir: Path,
    selected_images_dir: Path,
    panel_map_path: Path,
    image_clinical_path: Path,
    project_name: str,
    relative_images_dir: str,
) -> None:
    headers, rows = ensure_csv(register_path, IMAGE_REGISTER_COLUMNS)

    existing_by_relative = {
        row.get("relative_path", "").strip(): row
        for row in rows
        if row.get("relative_path", "").strip()
    }
    existing_by_global = {
        row.get("global_path", "").strip(): row
        for row in rows
        if row.get("global_path", "").strip()
    }

    used_ordinals = {
        int(Path(row.get("global_path", "")).stem)
        for row in rows
        if row.get("global_path", "").strip()
        and Path(row.get("global_path", "")).stem.isdigit()
    }
    next_ordinal = max(used_ordinals, default=0) + 1

    _, panel_map_rows = read_csv(panel_map_path)
    panel_by_image = {
        row.get("tiff_file", "").strip(): Path(
            row.get("panel_file", "")
        ).stem
        for row in panel_map_rows
        if row.get("tiff_file", "").strip()
    }

    _, image_clinical_rows = read_csv(image_clinical_path)
    cohort_by_image = {}
    for row in image_clinical_rows:
        image = row.get("image", "").strip()
        cohort = row.get("Cohort", "").strip()
        if image and cohort:
            cohort_by_image.setdefault(image, cohort)

    all_images_dir.mkdir(parents=True, exist_ok=True)
    image_paths = sorted(
        (
            path
            for path in selected_images_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".tif", ".tiff"}
        ),
        key=lambda path: str(path).casefold(),
    )

    for image_path in image_paths:
        project_image_path = image_path.relative_to(
            selected_images_dir
        ).as_posix()
        relative_path = (
            f"{project_name}/{relative_images_dir}/{project_image_path}"
        )

        existing_row = existing_by_relative.get(relative_path)
        if existing_row:
            global_path = existing_row.get("global_path", "").strip()
        else:
            global_path = (
                f"{all_images_dir.as_posix()}/{next_ordinal}.tiff"
            )
            next_ordinal += 1

            selected_key = image_path.relative_to(project_dir).as_posix()

            shape = []
            try:
                with tifffile.TiffFile(image_path) as tif:
                    if tif.series:
                        shape = list(tif.series[0].shape)
            except Exception:
                shape = []

            row = {
                "global_path": global_path,
                "relative_path": relative_path,
                "shape": str(shape),
                "panel_name": panel_by_image.get(
                    selected_key,
                    "",
                ),
                "cohort_name": cohort_by_image.get(
                    selected_key,
                    "",
                ),
                "project_name": project_name,
            }
            rows.append(row)
            existing_by_relative[relative_path] = row
            existing_by_global[global_path] = row

        symlink_path = all_images_dir / Path(global_path).name
        if symlink_path.is_symlink() or symlink_path.exists():
            continue
        symlink_path.symlink_to(image_path.resolve())

    rows.sort(
        key=lambda row: (
            row.get("project_name", "").strip().casefold(),
            row.get("cohort_name", "").strip().casefold(),
            row.get("panel_name", "").strip().casefold(),
            row.get("relative_path", "").strip().casefold(),
        )
    )
    write_csv(register_path, headers, rows)


def add_paths_to_image_clinical(
    image_clinical_path: Path,
    image_register_path: Path,
) -> None:
    """Populate global_path/relative_path in the image-clinical file."""
    headers, rows = ensure_csv(
        image_clinical_path,
        IMAGE_CLINICAL_COLUMNS,
    )
    headers = list(IMAGE_CLINICAL_COLUMNS)
    rows = [
        {column: row.get(column, "") for column in headers}
        for row in rows
    ]

    register_headers, register_rows = read_csv(image_register_path)
    register_by_image = {
        row.get("relative_path", "").strip(): row
        for row in register_rows
        if row.get("relative_path", "").strip()
    }

    for row in rows:
        relative_path = row.get("relative_path", "").strip()
        register_row = register_by_image.get(relative_path)
        if register_row is not None:
            row["global_path"] = register_row.get(
                "global_path",
                "",
            ).strip()
            row["relative_path"] = register_row.get(
                "relative_path",
                "",
            ).strip()

    write_csv(image_clinical_path, headers, rows)


def split_register_rows(
    rows: list[dict[str, str]],
    train_ratio: float = 0.8,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split register rows into train and test sets."""
    train_count = int(len(rows) * train_ratio)
    return rows[:train_count], rows[train_count:]


def update_global_image_split(
    split_dir: Path,
    all_images_dir: Path,
    register_path: Path,
) -> None:
    """Create train/test symlink folders that mirror all_images ordinals."""
    _, rows = read_csv(register_path)
    train_rows, test_rows = split_register_rows(rows)

    for subset, subset_rows in (
        ("train", train_rows),
        ("test", test_rows),
    ):
        for row in subset_rows:
            panel_name = row.get("panel_name", "").strip() or "unassigned"
            global_name = Path(
                row.get("global_path", "").strip()
            ).name
            if not global_name:
                continue

            source_symlink = all_images_dir / global_name
            if not source_symlink.is_symlink():
                continue

            destination = (
                split_dir / subset / panel_name / global_name
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink() or destination.exists():
                destination.unlink()
            destination.symlink_to(source_symlink.resolve())


def _panel_name_from_filename(path: Path) -> str:
    """Handle current parsed names and the older marker-parser convention."""
    name = path.name

    if name.endswith("_parsed.csv"):
        return name[:-len("_parsed.csv")]

    prefix = "markers_form_"
    suffix = "_panel_parsed.csv"
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix):-len(suffix)]

    if name.endswith(".csv"):
        return name[:-4]

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
    panel_by_file = {
        path: _panel_name_from_filename(path)
        for path in extracted_marker_files
    }

    headers, rows = ensure_csv(
        channel_path, ["Marker Name"]
    )
    headers = [
        header
        for header in headers
        if header not in {"Comment", "Aliases"}
    ]
    rows = [
        {header: row.get(header, "") for header in headers}
        for row in rows
    ]

    reused_columns: list[str] = []
    for panel in sorted(set(panel_by_file.values())):
        if panel not in headers:
            headers.append(panel)
            for row in rows:
                row[panel] = ""
        else:
            reused_columns.append(panel)

    if reused_columns:
        typer.echo(
            "Following panel names were already taken by "
            "existing panels in the global files:\n"
            f"{', '.join(reused_columns)}\n"
            "Please go back to the examine manifest, rename "
            "the file and redo the following steps."
        )

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
            f"No marker review manifests found under {marker_manifests_dir}"
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


    marker_names_path = get_global_file_path(
        config,
        "global_marker_names_file",
    )
    marker_channels_path = get_global_file_path(
        config,
        "global_marker_channels_file",
    )
    clinical_values_path = get_global_file_path(
        config,
        "global_clinical_values_file",
    )
    image_clinical_path = get_global_file_path(
        config,
        "global_image_clinical_file",
    )
    image_register_path = get_global_file_path(
        config,
        "global_image_register_file",
    )
    all_images_dir = get_global_subdir(
        config,
        "global_images_subdir",
    )
    global_split_dir = get_global_subdir(
        config,
        "global_split_subdir",
    )
    relative_images_dir = config["curation"]["relative_images_dir"]

    extracted_dir = (
        project_dir / "metadata" / "markers" / "selected"
    )
    extracted_marker_files = sorted(
        path for path in extracted_dir.glob("*.csv")
        if path.is_file()
    )

    if not extracted_marker_files:
        raise FileNotFoundError(
            f"No selected marker files found under {extracted_dir}"
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
    clinical_match_files = sorted(
        (
            project_dir
            / "metadata"
            / "clinical"
            / "selected"
        ).glob("*_image_clinical_matches.csv")
    )
    update_global_image_clinical(
        image_clinical_path,
        clinical_match_files,
        clinical_sources,
        project_name=name,
        relative_images_dir=relative_images_dir,
        proceed=proceed,
    )
    selected_images_dir = (
        project_dir
        / config["project_file_system"]["selected_images_dir"]
    )
    panel_map_path = (
        project_dir
        / "curation_manifests"
        / "extract"
        / "image_panel_map.csv"
    )
    update_global_image_register(
        image_register_path,
        all_images_dir,
        project_dir,
        selected_images_dir,
        panel_map_path,
        image_clinical_path,
        project_name=name,
        relative_images_dir=relative_images_dir,
    )
    add_paths_to_image_clinical(
        image_clinical_path,
        image_register_path,
    )
    update_global_image_split(
        global_split_dir,
        all_images_dir,
        image_register_path,
    )
    update_global_marker_channels(
        marker_channels_path,
        marker_names_path,
        extracted_marker_files,
        marker_sources,
    )

    answer = typer.prompt(
        "The final image files are under data/raw/selected. Files in "
        "data/raw/source and data/raw/unpacked are redundant at this "
        "point. Do you want to delete them? Yes/no",
        default="yes",
        show_default=False,
    )
    if answer.strip().lower() in {"yes", "y"}:
        unpacked_dir = (
            project_dir
            / config["project_file_system"]["unpacked_images_dir"]
        )
        source_dir = get_raw_source_dir(
            project_dir=project_dir,
            config=config,
        )
        for directory in (source_dir, unpacked_dir):
            if directory.is_dir():
                shutil.rmtree(directory)
                typer.echo(f"Deleted {directory}")

    typer.echo(f"Finalization completed for project: {name}")
    typer.echo(f"Marker manifests processed: {len(marker_manifests)}")
    typer.echo(f"Clinical manifests processed: {len(clinical_manifests)}")
    typer.echo(f"Marker tables processed: {len(extracted_marker_files)}")
