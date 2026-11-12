"""Parse OME channel names and group TIFFs into candidate imaging panels.

This module operates on metadata records produced by ``extract_ome_channels.py``.
It does not read TIFF pixel data or make irreversible curation decisions.
Unmatched channel names are retained and marked for review.
"""

from __future__ import annotations

import csv
import tomli_w
from collections import defaultdict
from pathlib import Path
from typing import Any

from imc_curator.commands_code.discovery.channel_parser_rules import (
    load_channel_parser_rules,
)
from imc_curator.commands_code.discovery.signature import (
    build_panel_id,
    build_panel_signature,
    format_panel_signature,
)


IMAGE_PANEL_COLUMNS = [
    "tiff_path",
    "image_name",
    "image_id",
    "panel_id",
    "panel_signature",
]

PANEL_CHANNEL_COLUMNS = [
    "biological_marker",
    "channel_number",
    "metal_isotope",
]

MANIFEST_VERSION = 1


def load_regex_rules() -> list[dict[str, Any]]:
    """Load enabled regex rules from TOML and compile each pattern once.

    Expected format:
        [[rules]]
        id = "ome_parentheses_v1"
        description = "Marker followed by isotope in parentheses"
        source = "raw_name"
        pattern = '^(?P<biological_marker>.*?)\\s*\\((?P<metal_ion>[^()]+)\\)\\s*$'
        enabled = true
    """
    return load_channel_parser_rules(
        required_groups={"biological_marker", "metal_ion"},
    )


def parse_channel(
    channel: dict[str, Any],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Parse a channel record with the first matching enabled rule.

    The returned record preserves all input fields and adds parsed fields.
    Matching is attempted in the order rules appear in the TOML file.
    """
    parsed = dict(channel)
    raw_name = str(parsed.get("raw_name") or "").strip()
    raw_fluor = str(parsed.get("raw_fluor") or "").strip()
    display_marker = raw_name or raw_fluor or "unnamed"

    parsed.update({
        "biological_marker": "",
        "metal_ion": "",
        "parser_rule_id": "",
        "parse_status": "needs_review",
        "panel_marker": display_marker,
        "signature_marker": f"unparsed:{display_marker}",
    })

    for rule in rules:
        source_value = parsed.get(rule["source"])
        if source_value is None:
            continue

        value = str(source_value).strip()
        if not value:
            continue

        match = rule["compiled_pattern"].fullmatch(value)
        if match is None:
            continue

        marker = (match.group("biological_marker") or "").strip()
        metal = (match.group("metal_ion") or "").strip()

        # Do not count empty captures as a successful parse.
        if not marker or not metal:
            continue

        parsed.update({
            "biological_marker": marker,
            "metal_ion": metal,
            "parser_rule_id": rule["id"],
            "parse_status": "parsed",
            "panel_marker": marker,
            "signature_marker": marker,
        })
        break

    return parsed


def _tiff_path(channel: dict[str, Any]) -> str:
    value = channel.get("tiff_path")
    if value is None or not str(value).strip():
        raise ValueError(
            "Every channel record must contain a non-empty 'tiff_path' "
            "to assign candidate panels."
        )
    return str(value)


def _channel_sort_key(channel: dict[str, Any]) -> tuple[int, str, str]:
    """Sort channels in the order recorded by the OME extractor."""
    try:
        number = int(channel.get("channel_number") or 0)
    except (TypeError, ValueError):
        number = 0
    return (
        number,
        str(channel.get("channel_id") or ""),
        str(channel.get("raw_name") or ""),
    )


def assign_panels(
    parsed_channels: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Group TIFFs by their channel signatures.

    Returns a mapping keyed by stable ``panel_id``. Each group contains:
      - ``panel_id``: stable ID derived from the channel signature
      - ``signature``: serialisable channel signature
      - ``tiff_paths``: sorted unique TIFF paths in the group
      - ``channels``: representative channel records in channel order
      - ``source_channel_records``: all parsed channel records for group TIFFs
      - ``status``: review-needed if any channel is unparsed

    A TIFF's panel signature is marker-set based: marker-only, independent of
    channel order, and alphabetically sorted for stable serialisation.
    Unparsed channels use normalised raw-name fallback markers.
    Identical signatures get the same panel ID.
    """
    channels_by_tiff: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for channel in parsed_channels:
        channels_by_tiff[_tiff_path(channel)].append(channel)

    tiff_signatures: dict[str, list[str]] = {}
    tiff_channels_sorted: dict[str, list[dict[str, Any]]] = {}

    for path, channels in channels_by_tiff.items():
        ordered = sorted(channels, key=_channel_sort_key)
        tiff_channels_sorted[path] = ordered
        tiff_signatures[path] = build_panel_signature(
            ordered,
            marker_key="signature_marker",
            raw_name_key="raw_name",
            raw_fluor_key="raw_fluor",
            channel_sort_key=_channel_sort_key,
        )

    paths_by_signature: dict[tuple[str, ...], list[str]] = defaultdict(list)

    for path, signature in tiff_signatures.items():
        signature_key = tuple(signature)
        paths_by_signature[signature_key].append(path)

    groups: dict[str, dict[str, Any]] = {}

    for signature_key in sorted(paths_by_signature):
        serialisable_signature = list(signature_key)
        panel_id = build_panel_id(serialisable_signature)

        tiff_paths = sorted(paths_by_signature[signature_key], key=str.casefold)

        representative = tiff_channels_sorted[tiff_paths[0]]
        
        source_records = [
            channel
            for path in tiff_paths
            for channel in sorted(
                channels_by_tiff[path],
                key=_channel_sort_key,
            )
        ]

        # A rare hash collision should fail loudly instead of merging panels.
        if (
            panel_id in groups 
            and groups[panel_id]["signature"] != serialisable_signature
        ):
            raise RuntimeError(
                f"Panel ID hash collision detected for {panel_id}."
            )

        needs_review = any(
            channel.get("parse_status") != "parsed"
            for channel in representative
        )

        groups[panel_id] = {
            "panel_id": panel_id,
            "signature": serialisable_signature,
            "tiff_paths": tiff_paths,
            "channels": representative,
            "source_channel_records": source_records,
            "status": "needs_review" if needs_review else "candidate",
        }

    return groups


def _csv_safe(value: Any) -> Any:
    """Convert list/dict values to compact text for CSV output."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return str(value)
    return value


def write_image_panel_csv(
    output_path: Path,
    parsed_channels: list[dict[str, Any]],
    panel_by_tiff: dict[str, str] | None = None,
    signature_by_tiff: dict[str, str] | None = None,
) -> Path:
    """Write one row per image with its assigned panel."""
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    panel_by_tiff = panel_by_tiff or {}
    signature_by_tiff = signature_by_tiff or {}

    image_rows: dict[str, dict[str, Any]] = {}
    for source_record in parsed_channels:
        path = str(source_record.get("tiff_path", ""))
        if not path or path in image_rows:
            continue

        image_rows[path] = {
            "tiff_path": path,
            "image_name": _csv_safe(source_record.get("image_name", "")),
            "image_id": _csv_safe(source_record.get("image_id", "")),
            "panel_id": panel_by_tiff.get(path, ""),
            "panel_signature": signature_by_tiff.get(path, ""),
        }

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=IMAGE_PANEL_COLUMNS,
        )
        writer.writeheader()
        for path in sorted(image_rows, key=str.casefold):
            writer.writerow(image_rows[path])

    return output_path


def _build_panel_manifest(group: dict[str, Any]) -> dict[str, Any]:
    """Build a TOML-compatible panel manifest with source-level evidence."""
    representative_channels = group["channels"]
    channels = []

    for channel in representative_channels:
        channels.append({
            "channel_number": _toml_value(channel.get("channel_number")),
            "channel_id": str(channel.get("channel_id") or ""),
            "raw_name": str(channel.get("raw_name") or ""),
            "raw_fluor": str(channel.get("raw_fluor") or ""),
            "excitation_wavelength": str(
                channel.get("excitation_wavelength") or ""
            ),
            "emission_wavelength": str(
                channel.get("emission_wavelength") or ""
            ),
            "biological_marker": str(channel.get("biological_marker") or ""),
            "metal_ion": str(channel.get("metal_ion") or ""),
            "parser_rule_id": str(channel.get("parser_rule_id") or ""),
            "parse_status": str(channel.get("parse_status") or "needs_review"),
        })

    return {
        "manifest_version": MANIFEST_VERSION,
        "panel": {
            "id": group["panel_id"],
            "status": group["status"],
            "source_tiff_count": len(group["tiff_paths"]),
            "channel_count": len(representative_channels),
        },
        "source_tiffs": [{"path": path} for path in group["tiff_paths"]],
        "signature": group["signature"],
        "channels": channels,
    }


def _build_panel_channel_rows(
    group: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build editable channel/marker rows for one unique OME panel."""
    rows = []

    for channel in group["channels"]:
        raw_name = str(channel.get("raw_name") or "").strip()
        raw_fluor = str(channel.get("raw_fluor") or "").strip()
        biological_marker = str(
            channel.get("biological_marker") or ""
        ).strip()
        marker = (
            str(channel.get("panel_marker") or "").strip()
            or biological_marker
            or raw_name
            or raw_fluor
        )

        rows.append({
            "biological_marker": marker,
            "channel_number": channel.get("channel_number", ""),
            "metal_isotope": str(channel.get("metal_ion") or "").strip(),
        })

    return rows


def _write_panel_channel_csv(
    output_path: Path,
    group: dict[str, Any],
) -> Path:
    """Write one editable CSV containing the channels in a unique panel."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=PANEL_CHANNEL_COLUMNS,
        )
        writer.writeheader()
        writer.writerows(_build_panel_channel_rows(group))

    return output_path.resolve()


def _toml_value(value: Any) -> int | float | str | bool:
    """Return a TOML-supported scalar, avoiding unsupported None values."""
    if value is None:
        return ""
    if isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


def write_panel_reports(
    parsed_channels: list[dict[str, Any]],
    panel_groups: dict[str, dict[str, Any]],
    output_dir: Path,
    panels_dir: Path,
) -> tuple[Path, list[Path], list[Path]]:
    """Write parsed channels plus one CSV and manifest per candidate panel.

    Panel IDs are generated by ``assign_panels`` and reused unchanged in both
    output formats. The returned paths are absolute paths.
    """
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    panels_dir = panels_dir.expanduser().resolve()
    panels_dir.mkdir(parents=True, exist_ok=True)

    panel_by_tiff: dict[str, str] = {}
    signature_by_tiff: dict[str, str] = {}

    for panel_id, group in panel_groups.items():
        signature_text = format_panel_signature(group["signature"])

        for path in group["tiff_paths"]:
            panel_by_tiff[path] = panel_id
            signature_by_tiff[path] = signature_text

    parsed_csv = write_image_panel_csv(
        output_dir / "parsed_ome_channels.csv",
        parsed_channels,
        panel_by_tiff=panel_by_tiff,
        signature_by_tiff=signature_by_tiff,
    )

    manifests_dir = output_dir / "panel_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    panel_csv_paths: list[Path] = []
    manifest_paths: list[Path] = []

    for panel_id in sorted(panel_groups):
        panel_group = panel_groups[panel_id]

        panel_csv_paths.append(
            _write_panel_channel_csv(
                panels_dir / f"{panel_id}.csv",
                panel_group,
            )
        )

        manifest = _build_panel_manifest(panel_group)
        manifest_path = manifests_dir / f"{panel_id}.toml"
        with manifest_path.open("wb") as file:
            file.write(tomli_w.dumps(manifest).encode("utf-8"))
        manifest_paths.append(manifest_path)

    return parsed_csv, panel_csv_paths, manifest_paths
