from __future__ import annotations

import csv
from pathlib import Path


MARKER_MANIFEST_SUFFIX = "marker_mapping_review.csv"


CLINICAL_MANIFEST_SUFFIX = "clinical_mapping_review.csv"


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
