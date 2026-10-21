
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from imc_curator.config import load_config


MARKER_NAME_COLUMNS = ["Marker Name", "Comment", "Aliases"]

CLINICAL_VALUE_COLUMNS = [
    "Standardized Feature",
    "Standardized Value",
    "Cohort",
    "Original Feature",
    "Original Value",
]


def _ensure_csv(path: Path, columns: list[str]) -> Path:
    """Create a missing or empty CSV file with the required header."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(columns)

    return path


def _read_csv(
    path: Path,
    required_columns: set[str] | None = None,
) -> list[dict[str, str]]:
    """Read a CSV and validate its header, even if it has no data rows."""
    path = Path(path)

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header: {path}")

        headers = {
            (header or "").strip()
            for header in reader.fieldnames
        }

        if required_columns and not required_columns.issubset(headers):
            missing = required_columns - headers
            raise ValueError(
                f"{path} is missing required columns: "
                f"{', '.join(sorted(missing))}"
            )

        return [
            {
                (key or "").strip(): (value or "").strip()
                for key, value in row.items()
            }
            for row in reader
        ]


def _normalise(value: str) -> str:
    """Trim whitespace and collapse repeated spaces."""
    return re.sub(r"\s+", " ", value or "").strip()


def _split_aliases(value: str) -> list[str]:
    """Split explicitly delimited aliases."""
    return [
        alias
        for part in re.split(r"[;|]", value or "")
        if (alias := _normalise(part))
    ]


def load_marker_mapping() -> dict[str, Any]:
    """Load marker names, aliases, and panel-specific original names."""
    config = load_config()
    path = Path(config["curation"]["global_marker_names_path"])

    _ensure_csv(path, MARKER_NAME_COLUMNS)

    rows = _read_csv(
        path,
        required_columns={"Marker Name", "Aliases"},
    )

    by_alias: dict[str, list[str]] = defaultdict(list)
    by_standardized_name: dict[str, dict[str, Any]] = {}

    metadata_columns = {"Marker Name", "Aliases", "Comment"}

    for row in rows:
        standardized_name = _normalise(row.get("Marker Name", ""))

        if not standardized_name:
            continue

        panel_names = {
            column: _normalise(value)
            for column, value in row.items()
            if column not in metadata_columns and _normalise(value)
        }

        aliases = _split_aliases(row.get("Aliases", ""))

        candidate_names = {
            _normalise(name)
            for name in [standardized_name, *aliases, *panel_names.values()]
            if _normalise(name)
        }

        by_standardized_name[standardized_name] = {
            "aliases": aliases,
            "panel_names": panel_names,
        }

        for name in candidate_names:
            if standardized_name not in by_alias[name]:
                by_alias[name].append(standardized_name)

    return {
        "by_alias": dict(by_alias),
        "by_original": dict(by_alias),  # Convenient alias for the input loader.
        "by_standardized_name": by_standardized_name,
    }


def load_clinical_mapping() -> dict[str, Any]:
    """Load original-to-standardized clinical feature/value mappings."""
    config = load_config()
    path = Path(config["curation"]["global_clinical_values_path"])

    _ensure_csv(path, CLINICAL_VALUE_COLUMNS)

    rows = _read_csv(
        path,
        required_columns=set(CLINICAL_VALUE_COLUMNS),
    )

    by_original: dict[tuple[str, str], list[dict[str, str]]] = (
        defaultdict(list)
    )
    by_standardized: dict[tuple[str, str], list[dict[str, str]]] = (
        defaultdict(list)
    )

    for row in rows:
        standardized_feature = _normalise(row["Standardized Feature"])
        standardized_value = _normalise(row["Standardized Value"])
        cohort = _normalise(row["Cohort"])
        original_feature = _normalise(row["Original Feature"])
        original_value = _normalise(row["Original Value"])

        if not all([
            standardized_feature,
            standardized_value,
            cohort,
            original_feature,
            original_value,
        ]):
            continue

        mapping = {
            "cohort": cohort,
            "original_feature": original_feature,
            "original_value": original_value,
            "standardized_feature": standardized_feature,
            "standardized_value": standardized_value,
        }

        original_key = (original_feature, original_value)
        standardized_key = (standardized_feature, standardized_value)

        if mapping not in by_original[original_key]:
            by_original[original_key].append(mapping)

        if mapping not in by_standardized[standardized_key]:
            by_standardized[standardized_key].append(mapping)

    return {
        "by_original": dict(by_original),
        "by_standardized": dict(by_standardized),
    }
