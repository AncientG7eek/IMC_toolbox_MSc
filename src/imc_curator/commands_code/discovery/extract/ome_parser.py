"""Extract OME panels from the completed channel-selection form."""

from __future__ import annotations

import csv
import tomllib
from pathlib import Path
from typing import Any

from imc_curator.commands_code.discovery.examine.submodules.ome_panel_parser import (
    assign_panels,
    load_regex_rules,
    parse_channel,
    write_panel_reports,
)
from imc_curator.commands_code.discovery.extract.panel_map import (
    append_panel_map_rows,
    project_relative,
    selected_panel_file,
)
from imc_curator.commands_code.discovery.signature import format_panel_signature


def _resolve_path(path: Path, project_dir: Path) -> Path:
    """Resolve a path relative to the project unless it is absolute."""
    path = Path(path)
    return path if path.is_absolute() else project_dir / path


def _read_form(form_path: Path) -> dict[str, Any]:
    with form_path.open("rb") as file:
        return tomllib.load(file)


def _read_raw_channels(raw_channels_path: Path) -> list[dict[str, str]]:
    with raw_channels_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return [dict(row) for row in csv.DictReader(file)]


def extract_ome_panels(
    project_dir: Path,
    raw_channels_path: Path,
    form_path: Path,
    selected_panels_dir: Path,
    manifest_output_dir: Path,
    images_output_dir: Path | None = None,
    panel_map_path: Path | None = None,
) -> str:
    """Build OME panels and the image map from the user's channel selection."""
    project_dir = project_dir.resolve()
    raw_channels_path = _resolve_path(raw_channels_path, project_dir)
    form_path = _resolve_path(form_path, project_dir)
    selected_panels_dir = _resolve_path(selected_panels_dir, project_dir)
    manifest_output_dir = _resolve_path(manifest_output_dir, project_dir)
    if images_output_dir is not None:
        images_output_dir = _resolve_path(images_output_dir, project_dir)
    if panel_map_path is not None:
        panel_map_path = _resolve_path(panel_map_path, project_dir)

    if not raw_channels_path.is_file():
        return f"No OME raw channels file found at:\n  {raw_channels_path}"
    if not form_path.is_file():
        return f"No OME channel form found at:\n  {form_path}"

    form = _read_form(form_path)
    selected_labels = form.get("channel_selection", {}).get(
        "channel_labels",
        [],
    )
    if not isinstance(selected_labels, list):
        raise ValueError(
            f"{form_path}: channel_selection.channel_labels must be an array."
        )
    selected_label_set = {
        str(label).strip()
        for label in selected_labels
        if str(label).strip()
    }

    raw_channels = _read_raw_channels(raw_channels_path)
    filtered_channels = [
        channel
        for channel in raw_channels
        if str(channel.get("raw_name", "")).strip() in selected_label_set
    ]

    if not filtered_channels:
        return (
            "OME panel extraction skipped: no OME channels matched the "
            f"selection in {form_path}."
        )

    rules = load_regex_rules()
    parsed_channels = [
        parse_channel(channel, rules)
        for channel in filtered_channels
    ]
    panel_groups = assign_panels(parsed_channels)

    parsed_csv, panel_csv_paths, manifest_paths = write_panel_reports(
        parsed_channels=parsed_channels,
        panel_groups=panel_groups,
        output_dir=manifest_output_dir,
        panels_dir=selected_panels_dir,
    )

    if panel_map_path is not None:
        map_rows = []
        for panel_id, group in panel_groups.items():
            signature_text = format_panel_signature(group["signature"])
            for tiff_path in group["tiff_paths"]:
                tiff_file = Path(tiff_path)
                if images_output_dir is not None:
                    tiff_file = images_output_dir / tiff_file

                map_rows.append(
                    {
                        "tiff_file": project_relative(
                            tiff_file,
                            project_dir,
                        ),
                        "panel_id": panel_id,
                        "panel_signature": signature_text,
                        "panel_file": selected_panel_file(
                            selected_panels_dir,
                            panel_id,
                            project_dir,
                        ),
                    }
                )

        if map_rows:
            append_panel_map_rows(panel_map_path, map_rows)

    report = [
        "",
        "OME PANEL EXTRACTION",
        f"Form: {form_path.resolve()}",
        f"Selected channel labels: {sorted(selected_label_set)}",
        f"OME channels kept: {len(filtered_channels)}",
        f"Panel groups: {len(panel_groups)}",
        f"Selected panels: {len(panel_csv_paths)}",
        f"Panel manifests: {len(manifest_paths)}",
        f"Parsed channels: {parsed_csv.resolve()}",
        f"Selected panel directory: {selected_panels_dir.resolve()}",
    ]
    if panel_map_path is not None:
        report.append(f"Image-to-panel map: {panel_map_path.resolve()}")

    return "\n".join(report)
