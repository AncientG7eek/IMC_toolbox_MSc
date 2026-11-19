"""Shared image-to-panel map writing for all extraction sources."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


PANEL_MAP_COLUMNS = [
    "tiff_file",
    "panel_id",
    "panel_signature",
    "panel_file",
]


def project_relative(path: str | Path, project_dir: Path) -> str:
    """Return a project-relative POSIX path when possible."""
    project_dir = project_dir.resolve()
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = project_dir / resolved
    resolved = resolved.resolve()

    if resolved.is_relative_to(project_dir):
        return resolved.relative_to(project_dir).as_posix()
    return resolved.as_posix()


def selected_panel_file(
    selected_panels_dir: Path,
    panel_id: str,
    project_dir: Path,
) -> str:
    """Return the project-relative path to a selected panel CSV."""
    return project_relative(
        selected_panels_dir / f"{panel_id}.csv",
        project_dir,
    )


def init_panel_map(output_path: Path) -> Path:
    """Create or truncate the combined image-to-panel map with a header."""
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=PANEL_MAP_COLUMNS,
        )
        writer.writeheader()

    return output_path


def append_panel_map_rows(
    output_path: Path,
    rows: list[dict[str, Any]],
) -> None:
    """Append image-to-panel rows to the combined map."""
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not output_path.exists():
        init_panel_map(output_path)

    with output_path.open(
        "a",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=PANEL_MAP_COLUMNS,
            extrasaction="ignore",
        )
        writer.writerows(rows)


def remap_tiff_files(
    output_path: Path,
    from_dir: Path,
    to_dir: Path,
    project_dir: Path,
) -> None:
    """Replace an image directory prefix in the panel map."""
    output_path = output_path.expanduser().resolve()
    from_prefix = project_relative(from_dir, project_dir)
    to_prefix = project_relative(to_dir, project_dir)

    with output_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = [dict(row) for row in csv.DictReader(file)]

    for row in rows:
        tiff_file = str(row.get("tiff_file", ""))
        if tiff_file.startswith(from_prefix + "/"):
            row["tiff_file"] = (
                to_prefix + "/" + tiff_file[len(from_prefix) + 1 :]
            )

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=PANEL_MAP_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
