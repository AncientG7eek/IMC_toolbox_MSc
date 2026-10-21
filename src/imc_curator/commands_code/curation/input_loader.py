
import csv
from pathlib import Path
from typing import Any

from imc_curator.config import get_projects_dir


IMAGE_COLUMNS = {"image_path", "image_name", "image_id"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV while preserving its column names and cell values."""
    matching_files = list(path.parent.absolute().glob(path.name))

    if len(matching_files) == 1:
        with matching_files[0].open(
            "r", encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.DictReader(file)
    
            if reader.fieldnames is None:
                raise ValueError(f"CSV file has no header: {path}")
    
            return [
                {
                    key: (value or "").strip()
                    for key, value in row.items()
                    if key is not None
                }
                for row in reader
            ]
    elif not matching_files:
        raise FileNotFoundError(
            f"No marker files found in {path.parent.absolute()}"
        )
    else:
        raise ValueError(
            f"Expected one marker file, found {len(matching_files)}: "
            f"{matching_files}"
        )
    


def load_extracted_markers(
    project_name: str,
    marker_mapping: dict[str, Any],
) -> dict[str, Any]:
    """
    Load extracted marker data and look up biological_marker values.

    Returns:
        rows:
            Original extracted rows, with standardized_marker_candidates added.

        matches:
            Distinct original marker names and their candidate mappings.

        unmatched:
            Distinct marker names with no reference match.
    """
    projects_dir = get_projects_dir()
    project_dir = projects_dir / project_name
    path = project_dir / "curation_manifests" / "extract" / "markers" / "markers_form_*_panel_parsed.csv"
    rows = _read_csv(path)

    if rows and "biological_marker" not in rows[0]:
        raise ValueError(
            f"{path} must contain a 'biological_marker' column"
        )

    # Support either reference key, depending on your reference_manager version.
    by_original = marker_mapping.get(
        "by_original",
        marker_mapping.get("by_alias", {}),
    )

    matches: dict[str, list[Any]] = {}
    unmatched: list[str] = []

    for row in rows:
        original_marker = row.get("biological_marker", "").strip()

        if not original_marker:
            continue

        if original_marker not in matches:
            candidates = by_original.get(original_marker, [])
            matches[original_marker] = candidates

            if not candidates:
                unmatched.append(original_marker)
                
    return {
        "rows": rows,
        "matches": matches,
        "unmatched": unmatched,
    }


def load_extracted_clinical(
    path: Path,
    clinical_mapping: dict[str, Any],
) -> dict[str, Any]:
    """
    Load extracted clinical data and look up unique feature/value pairs.

    The lookup key is (original_feature, original_value).

    Returns:
        rows:
            Original image-level clinical records.

        matches:
            Feature -> original value -> candidate mappings.

        unmatched:
            Feature -> original values with no reference match.
    """
    rows = _read_csv(path)

    if rows:
        missing_columns = IMAGE_COLUMNS - set(rows[0])
        if missing_columns:
            raise ValueError(
                f"{path} is missing required image columns: "
                f"{', '.join(sorted(missing_columns))}"
            )

    by_original = clinical_mapping.get("by_original", {})

    # Find clinical features from the CSV headers.
    clinical_features = [
        column
        for column in (rows[0].keys() if rows else [])
        if column not in IMAGE_COLUMNS
    ]

    matches: dict[str, dict[str, list[Any]]] = {}
    unmatched: dict[str, list[str]] = {}

    for feature in clinical_features:
        matches[feature] = {}
        unmatched[feature] = []

        # Collect unique non-empty values across all images.
        unique_values = dict.fromkeys(
            row[feature]
            for row in rows
            if row.get(feature, "").strip()
        )

        for value in unique_values:
            key = (feature, value)
            candidates = by_original.get(key, [])

            matches[feature][value] = candidates

            if not candidates:
                unmatched[feature].append(value)

    # Remove empty unmatched entries for a cleaner report.
    unmatched = {
        feature: values
        for feature, values in unmatched.items()
        if values
    }

    return {
        "rows": rows,
        "matches": matches,
        "unmatched": unmatched,
    }
