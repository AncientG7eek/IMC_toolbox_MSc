"""Rewrite unpacked TIFFs to contain only channels selected for their panel."""

from __future__ import annotations

import csv
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import tifffile

from imc_curator.commands_code.discovery.examine.submodules.extract_ome_channels import (
    extract_tiff_metadata,
)
from imc_curator.commands_code.discovery.examine.submodules.ome_panel_parser import (
    load_regex_rules,
    parse_channel,
)

if TYPE_CHECKING:
    from imc_curator.progress_bar import ProgressManager


def _read_panel_channels(panel_path: Path) -> list[dict[str, str]]:
    with panel_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return [dict(row) for row in csv.DictReader(file)]


def _read_source_channel_numbers(
    project_dir: Path,
    panel_file: str,
) -> list[int]:
    stem = Path(panel_file).stem
    info_path = (
        project_dir
        / "curation_manifests"
        / "extract"
        / "markers"
        / f"{stem}.toml"
    )
    if not info_path.is_file():
        return []

    with info_path.open("rb") as file:
        data = tomllib.load(file)

    values = data.get("post_selection", {}).get(
        "source_channel_numbers",
        [],
    )
    return [int(value) for value in values]


def _read_tiff_stack(tiff_path: Path) -> np.ndarray:
    """Read a TIFF as a CYX array without relying on OME series parsing."""
    with tifffile.TiffFile(tiff_path) as tiff:
        pages = list(tiff.pages)

        if not pages:
            raise ValueError(f"TIFF has no pages: {tiff_path}")

        if len(pages) == 1:
            array = pages[0].asarray()
            if array.ndim == 2:
                array = array[None, :, :]
            return array

        arrays = [page.asarray() for page in pages]
        return np.stack(arrays, axis=0)


def _sorted_channel_indices(
    tiff_path: Path,
    panel_channels: list[dict[str, str]],
) -> tuple[list[int], list[str], list[str]]:
    channels, _ = extract_tiff_metadata(
        tiff_path,
        tiff_path.parent,
    )
    rules = load_regex_rules()
    parsed_channels = [
        parse_channel(channel, rules)
        for channel in channels
    ]

    indices: list[int] = []
    labels: list[str] = []
    names: list[str] = []
    for panel_channel in panel_channels:
        marker = panel_channel.get("biological_marker", "").strip()
        metal = panel_channel.get("metal_isotope", "").strip()
        raw_channel = None
        for index, parsed in enumerate(parsed_channels):
            if index in indices:
                continue
            parsed_marker = str(
                parsed.get("biological_marker") or ""
            ).strip()
            parsed_metal = str(
                parsed.get("metal_ion") or ""
            ).strip()
            raw_name = str(
                parsed.get("raw_name") or ""
            ).strip()
            raw_fluor = str(
                parsed.get("raw_fluor") or ""
            ).strip()

            marker_matches = (
                marker.casefold()
                in {parsed_marker.casefold(), raw_name.casefold()}
            )
            metal_matches = (
                not metal
                or metal.casefold()
                in {parsed_metal.casefold(), raw_fluor.casefold()}
            )
            if marker_matches and metal_matches:
                raw_channel = parsed
                break

        if raw_channel is None:
            continue

        index = int(raw_channel.get("channel_number", -1))
        if index < 0 or index in indices:
            continue
        indices.append(index)
        labels.append(
            str(raw_channel.get("raw_name", "")).strip()
        )
        names.append(marker)

    return indices, labels, names


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

        image = _read_tiff_stack(tiff_path)
        if image.ndim != 3:
            skipped += 1
            continue

        source_numbers = _read_source_channel_numbers(
            project_dir,
            panel_file,
        )
        if source_numbers:
            selected_indices = []
            selected_labels = []
            selected_names = []
            for channel, index in zip(panel_channels, source_numbers):
                if 0 <= index < image.shape[0] and index not in selected_indices:
                    selected_indices.append(index)
                    selected_labels.append(
                        str(channel.get("metal_isotope", "")).strip()
                    )
                    selected_names.append(
                        str(channel.get("biological_marker", "")).strip()
                    )
        else:
            selected_indices, selected_labels, selected_names = (
                _sorted_channel_indices(tiff_path, panel_channels)
            )

        if not selected_indices:
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
