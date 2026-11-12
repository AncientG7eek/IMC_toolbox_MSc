
import csv
from pathlib import Path
from typing import Any

from imc_curator.config import get_projects_dir


IMAGE_COLUMNS = {"image_path", "image_name", "image_id"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read one exact CSV path, preserving column names and cell values."""
    if not path.is_file():
        raise FileNotFoundError(f"CSV file does not exist: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
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


def _marker_candidates(
    original_marker: str,
    marker_mapping: dict[str, Any],
) -> list[Any]:
    """Look up candidates using the available reference-map index."""
    by_original = marker_mapping.get("by_original")
    by_alias = marker_mapping.get("by_alias", {})

    candidates = None
    if isinstance(by_original, dict):
        candidates = by_original.get(original_marker)

    if candidates is None and isinstance(by_alias, dict):
        candidates = by_alias.get(original_marker)

    return list(candidates or [])


def load_extracted_markers(
    project_name: str,
    marker_mapping: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Load every parsed marker table independently.

    Each returned bundle contains source_file, panel_id, path, rows,
    matches, and unmatched.
    """
    project_dir = Path(project_name)
    if not project_dir.is_absolute():
        project_dir = get_projects_dir() / project_dir
    project_dir = project_dir.resolve()

    marker_dir = project_dir / "metadata" / "markers" / "selected"
    marker_files = sorted(
        marker_dir.glob("*.csv"),
        key=lambda path: path.name.casefold(),
    )

    if not marker_files:
        raise FileNotFoundError(
            f"No selected panel tables found in {marker_dir}"
        )

    bundles: list[dict[str, Any]] = []

    for path in marker_files:
        rows = _read_csv(path)

        if rows:
            required = {"biological_marker", "channel_number"}
            missing = required - set(rows[0])
            if missing:
                raise ValueError(
                    f"{path} is missing required columns: "
                    f"{', '.join(sorted(missing))}"
                )

        panel_id = path.stem
        matches: dict[str, list[Any]] = {}
        unmatched: list[str] = []

        for row in rows:
            original_marker = row.get("biological_marker", "").strip()
            row["source_file"] = path.name
            row["panel_id"] = panel_id

            if not original_marker:
                row["standardized_marker_candidates"] = []
                continue

            if original_marker not in matches:
                candidates = _marker_candidates(
                    original_marker,
                    marker_mapping,
                )
                matches[original_marker] = candidates
                if not candidates:
                    unmatched.append(original_marker)

            row["standardized_marker_candidates"] = matches[
                original_marker
            ]

        bundles.append(
            {
                "source_file": path.name,
                "panel_id": panel_id,
                "path": path,
                "rows": rows,
                "matches": matches,
                "unmatched": unmatched,
            }
        )

    return bundles


def load_extracted_clinical(
    path: Path,
    clinical_mapping: dict[str, Any],
) -> dict[str, Any]:
    """
    Load one image-level clinical matching table.

    The lookup key is (original_feature, original_value).
    """
    path = Path(path)
    rows = _read_csv(path)

    if rows:
        missing_columns = IMAGE_COLUMNS - set(rows[0])
        if missing_columns:
            raise ValueError(
                f"{path} is missing required image columns: "
                f"{', '.join(sorted(missing_columns))}"
            )

    by_original = clinical_mapping.get("by_original", {})
    clinical_features = [
        column
        for column in (rows[0].keys() if rows else [])
        if column not in IMAGE_COLUMNS
        and column not in {"_merge", "image_id"}
    ]

    matches: dict[str, dict[str, list[Any]]] = {}
    unmatched: dict[str, list[str]] = {}

    for feature in clinical_features:
        matches[feature] = {}
        unmatched[feature] = []

        unique_values = dict.fromkeys(
            row.get(feature, "")
            for row in rows
            if row.get(feature, "").strip()
        )

        for value in unique_values:
            candidates = list(by_original.get((feature, value), []) or [])
            matches[feature][value] = candidates

            if not candidates:
                unmatched[feature].append(value)

    unmatched = {
        feature: values
        for feature, values in unmatched.items()
        if values
    }

    return {
        "source_file": path.name,
        "path": path,
        "rows": rows,
        "matches": matches,
        "unmatched": unmatched,
    }
