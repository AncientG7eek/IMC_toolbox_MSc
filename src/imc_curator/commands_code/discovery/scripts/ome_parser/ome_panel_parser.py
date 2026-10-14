"""Parse OME channel names and group TIFFs into candidate imaging panels.

This module operates on metadata records produced by ``extract_ome_channels.py``.
It does not read TIFF pixel data or make irreversible curation decisions.
Unmatched channel names are retained and marked for review.
"""

from __future__ import annotations

import csv
import hashlib
import re
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any

import tomli_w


PARSED_CHANNEL_COLUMNS = [
    "tiff_path",
    "image_name",
    "image_id",
    "channel_number",
    "channel_id",
    "raw_name",
    "raw_fluor",
    "excitation_wavelength",
    "emission_wavelength",
    "color",
    "samples_per_pixel",
    "biological_marker",
    "metal_ion",
    "parser_rule_id",
    "parse_status",
    "panel_id",
    "panel_signature",
]

MANIFEST_VERSION = 1


def load_regex_rules(rules_path: Path) -> list[dict[str, Any]]:
    """Load enabled regex rules from TOML and compile each pattern once.

    Expected format:
        [[rules]]
        id = "ome_parentheses_v1"
        description = "Marker followed by isotope in parentheses"
        source = "raw_name"
        pattern = '^(?P<biological_marker>.*?)\\s*\\((?P<metal_ion>[^()]+)\\)\\s*$'
        enabled = true
    """
    rules_path = rules_path.expanduser().resolve()
    if not rules_path.is_file():
        raise FileNotFoundError(f"OME parser rules file does not exist: {rules_path}")

    with rules_path.open("rb") as file:
        config = tomllib.load(file)

    configured_rules = config.get("rules", [])
    if not isinstance(configured_rules, list):
        raise ValueError("The rules TOML must contain an array of [[rules]] tables.")

    rules: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, rule in enumerate(configured_rules, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule {index} must be a TOML table.")

        if not rule.get("enabled", True):
            continue

        rule_id = rule.get("id")
        pattern = rule.get("pattern")
        source = rule.get("source", "raw_name")

        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError(f"Enabled rule {index} must have a non-empty 'id'.")
        if rule_id in seen_ids:
            raise ValueError(f"Duplicate OME parser rule id: {rule_id}")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"Enabled rule {rule_id!r} must have a non-empty pattern.")
        if source not in {"raw_name", "raw_fluor"}:
            raise ValueError(
                f"Rule {rule_id!r} has unsupported source {source!r}; "
                "use 'raw_name' or 'raw_fluor'."
            )

        try:
            compiled_pattern = re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"Invalid regex in OME parser rule {rule_id!r}: {exc}"
            ) from exc

        group_names = compiled_pattern.groupindex
        missing_groups = {
            "biological_marker",
            "metal_ion",
        } - set(group_names)
        if missing_groups:
            raise ValueError(
                f"Rule {rule_id!r} must define named capture groups: "
                f"{', '.join(sorted(missing_groups))}"
            )

        rules.append({
            "id": rule_id,
            "description": str(rule.get("description", "")),
            "source": source,
            "pattern": pattern,
            "compiled_pattern": compiled_pattern,
        })
        seen_ids.add(rule_id)

    return rules


def parse_channel(
    channel: dict[str, Any],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Parse a channel record with the first matching enabled rule.

    The returned record preserves all input fields and adds parsed fields.
    Matching is attempted in the order rules appear in the TOML file.
    """
    parsed = dict(channel)
    parsed.update({
        "biological_marker": "",
        "metal_ion": "",
        "parser_rule_id": "",
        "parse_status": "needs_review",
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
        })
        break

    return parsed


def _normalise_signature_value(value: Any) -> str:
    """Normalise a signature component without changing the source record."""
    return str(value or "").strip().casefold()


def _channel_signature(channel: dict[str, Any]) -> tuple[str, str]:
    """Return the identity used to compare panel channel compositions.

    Parsed channels use marker + isotope. Unparsed channels use their raw
    name/fluor label, so unknown channels remain visible in grouping rather
    than silently disappearing.
    """
    marker = _normalise_signature_value(channel.get("biological_marker"))
    metal = _normalise_signature_value(channel.get("metal_ion"))
    if marker and metal:
        return marker, metal

    raw_name = _normalise_signature_value(channel.get("raw_name"))
    raw_fluor = _normalise_signature_value(channel.get("raw_fluor"))
    fallback = raw_name or raw_fluor or "<unnamed-channel>"
    return f"unparsed:{fallback}", ""


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
    """Group TIFFs by their ordered channel signatures.

    Returns a mapping keyed by stable ``panel_id``. Each group contains:
      - ``panel_id``: stable ID derived from the channel signature
      - ``signature``: ordered, serialisable channel signature
      - ``tiff_paths``: sorted unique TIFF paths in the group
      - ``channels``: representative channel records in channel order
      - ``source_channel_records``: all parsed channel records for group TIFFs
      - ``status``: review-needed if any channel is unparsed

    A TIFF's panel signature is based on channel order and composition, not
    its filename. Identical signatures get the same panel ID.
    """
    channels_by_tiff: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for channel in parsed_channels:
        channels_by_tiff[_tiff_path(channel)].append(channel)

    tiff_signatures: dict[str, tuple[tuple[str, str], ...]] = {}
    tiff_channels_sorted: dict[str, list[dict[str, Any]]] = {}

    for path, channels in channels_by_tiff.items():
        ordered = sorted(channels, key=_channel_sort_key)
        tiff_channels_sorted[path] = ordered
        tiff_signatures[path] = tuple(_channel_signature(item) for item in ordered)

    paths_by_signature: dict[
        tuple[tuple[str, str], ...], list[str]
    ] = defaultdict(list)
    for path, signature in tiff_signatures.items():
        paths_by_signature[signature].append(path)

    groups: dict[str, dict[str, Any]] = {}

    for signature in sorted(paths_by_signature):
        # Hash a stable textual representation; IDs don't change merely
        # because a newly discovered, unrelated panel sorts earlier.
        signature_text = "\n".join(f"{marker}\t{metal}" for marker, metal in signature)
        digest = hashlib.sha1(signature_text.encode("utf-8")).hexdigest()[:10]
        panel_id = f"panel_{digest}"

        tiff_paths = sorted(paths_by_signature[signature], key=str.casefold)
        representative = tiff_channels_sorted[tiff_paths[0]]
        source_records = [
            channel
            for path in tiff_paths
            for channel in tiff_channels_sorted[path]
        ]

        # A rare hash collision should fail loudly instead of merging panels.
        if panel_id in groups and groups[panel_id]["signature"] != [
            {"biological_marker": marker, "metal_ion": metal}
            for marker, metal in signature
        ]:
            raise RuntimeError(f"Panel ID hash collision detected for {panel_id}.")

        serialisable_signature = [
            {"biological_marker": marker, "metal_ion": metal}
            for marker, metal in signature
        ]
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


def write_parsed_channel_csv(
    output_path: Path,
    parsed_channels: list[dict[str, Any]],
    panel_by_tiff: dict[str, str] | None = None,
    signature_by_tiff: dict[str, str] | None = None,
) -> Path:
    """Write parsed channel records, optionally including panel assignments."""
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    panel_by_tiff = panel_by_tiff or {}
    signature_by_tiff = signature_by_tiff or {}

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=PARSED_CHANNEL_COLUMNS,
            extrasaction="ignore",
        )
        writer.writeheader()

        for source_record in parsed_channels:
            record = dict(source_record)
            path = str(record.get("tiff_path", ""))
            record["panel_id"] = panel_by_tiff.get(path, "")
            record["panel_signature"] = signature_by_tiff.get(path, "")
            writer.writerow({
                key: _csv_safe(record.get(key, ""))
                for key in PARSED_CHANNEL_COLUMNS
            })

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
) -> tuple[Path, list[Path]]:
    """Write parsed-channel CSV and one TOML manifest per candidate panel.

    Panel IDs are generated by ``assign_panels`` and reused unchanged in both
    output formats. The returned paths are absolute paths.
    """
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    panel_by_tiff: dict[str, str] = {}
    signature_by_tiff: dict[str, str] = {}

    for panel_id, group in panel_groups.items():
        signature_text = "; ".join(
            f"{item['biological_marker']} ({item['metal_ion']})"
            for item in group["signature"]
        )
        for path in group["tiff_paths"]:
            panel_by_tiff[path] = panel_id
            signature_by_tiff[path] = signature_text

    parsed_csv = write_parsed_channel_csv(
        output_dir / "parsed_ome_channels.csv",
        parsed_channels,
        panel_by_tiff=panel_by_tiff,
        signature_by_tiff=signature_by_tiff,
    )

    manifests_dir = output_dir / "panel_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_paths: list[Path] = []

    for panel_id in sorted(panel_groups):
        manifest = _build_panel_manifest(panel_groups[panel_id])
        manifest_path = manifests_dir / f"{panel_id}.toml"
        with manifest_path.open("wb") as file:
            file.write(tomli_w.dumps(manifest).encode("utf-8"))
        manifest_paths.append(manifest_path)

    return parsed_csv, manifest_paths