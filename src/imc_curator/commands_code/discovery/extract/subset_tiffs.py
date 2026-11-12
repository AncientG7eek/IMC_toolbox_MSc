"""Rewrite unpacked TIFFs to contain only channels selected for their panel."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

import tifffile

if TYPE_CHECKING:
    from imc_curator.progress_bar import ProgressManager


def _read_panel_channels(panel_path: Path) -> list[dict[str, str]]:
    with panel_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return [dict(row) for row in csv.DictReader(file)]


def subset_images(
    project_dir: Path,
    images_output_dir: Path,
    selected_images_dir: Path,
    panel_map_path: Path,
    selected_panels_dir: Path,
    progress: "ProgressManager | None" = None,
) -> str:
    """Keep only selected channels in each unpacked TIFF."""
    project_dir = project_dir.resolve()
    images_output_dir = images_output_dir.resolve()
    selected_images_dir = selected_images_dir.expanduser().resolve()
    panel_map_path = panel_map_path.expanduser().resolve()
    selected_panels_dir = selected_panels_dir.expanduser().resolve()

    if not panel_map_path.is_file():
        return f"Image panel map not found: {panel_map_path}"

    with panel_map_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        map_rows = list(csv.DictReader(file))

    panels: dict[str, list[dict[str, str]]] = {}
    rewritten = 0
    skipped = 0
    missing = 0

    iterable = (
        progress.track(
            map_rows,
            description="Subsetting image channels",
            total=len(map_rows),
            item_description=lambda row: row.get("tiff_file", ""),
        )
        if progress
        else map_rows
    )

    for row in iterable:
        tiff_file = str(row.get("tiff_file", "")).strip()
        panel_file = str(row.get("panel_file", "")).strip()
        if not tiff_file or not panel_file:
            skipped += 1
            continue

        # MCD TIFFs are already written with only the selected channels.
        if "raw_imc_data" in Path(tiff_file).parts:
            skipped += 1
            continue

        tiff_path = project_dir / tiff_file
        if not tiff_path.is_file():
            missing += 1
            continue

        panel_path = project_dir / panel_file
        if not panel_path.is_file():
            missing += 1
            continue

        if panel_file not in panels:
            panels[panel_file] = _read_panel_channels(panel_path)
        panel_channels = panels[panel_file]

        image = tifffile.imread(tiff_path)
        if image.ndim != 3:
            skipped += 1
            continue

        selected_indices = []
        selected_labels = []
        selected_names = []
        for channel in panel_channels:
            try:
                channel_number = int(channel.get("channel_number", ""))
            except (TypeError, ValueError):
                continue
            index = channel_number
            if 0 <= index < image.shape[0] and index not in selected_indices:
                selected_indices.append(index)
                selected_labels.append(
                    str(channel.get("metal_isotope", "")).strip()
                )
                selected_names.append(
                    str(channel.get("biological_marker", "")).strip()
                )

        if not selected_indices:
            skipped += 1
            continue
        if len(selected_indices) == image.shape[0]:
            skipped += 1
            continue

        try:
            relative_path = tiff_path.relative_to(images_output_dir)
        except ValueError:
            relative_path = Path(tiff_path.name)

        destination_path = selected_images_dir / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        subset = image[selected_indices, :, :]
        tifffile.imwrite(
            destination_path,
            subset,
            metadata={
                "axes": "CYX",
                "channel_labels": selected_labels,
                "channel_names": selected_names,
            },
        )
        rewritten += 1

    return "\n".join(
        [
            "",
            "IMAGE CHANNEL SUBSETTING",
            f"Images processed: {len(map_rows)}",
            f"Images rewritten: {rewritten}",
            f"Images skipped: {skipped}",
            f"Images missing: {missing}",
            f"Selected image directory: {selected_images_dir}",
        ]
    )
