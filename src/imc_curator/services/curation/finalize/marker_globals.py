from __future__ import annotations

from pathlib import Path

import typer

from imc_curator.services.curation.finalize.common import (
    MARKER_MANIFEST_SUFFIX,
    ensure_csv,
    read_csv,
    write_csv,
)
from imc_curator.services.curation.finalize.mapping import (
    _append_alias,
    _final_marker_name,
)


MARKER_COLUMNS = ["Marker Name", "Comment", "Aliases"]


def update_global_marker_names(
    path: Path,
    manifest_rows: list[dict[str, str]],
) -> None:
    headers, rows = ensure_csv(path, MARKER_COLUMNS)
    by_name = {
        row.get("Marker Name", "").strip(): row
        for row in rows
        if row.get("Marker Name", "").strip()
    }

    for review in manifest_rows:
        original = review.get("original_marker", "").strip()
        standardized = _final_marker_name(review, proceed=True)

        if not original or not standardized:
            continue

        if standardized not in by_name:
            new_row = {header: "" for header in headers}
            new_row["Marker Name"] = standardized
            new_row["Aliases"] = original
            rows.append(new_row)
            by_name[standardized] = new_row
        else:
            target = by_name[standardized]
            target["Aliases"] = _append_alias(
                target.get("Aliases", ""), original
            )

    rows.sort(
        key=lambda row: row.get("Marker Name", "").strip().casefold()
    )
    write_csv(path, headers, rows)


def _panel_name_from_filename(path: Path) -> str:
    """Handle current parsed names and the older marker-parser convention."""
    name = path.name

    if name.endswith("_parsed.csv"):
        return name[:-len("_parsed.csv")]

    prefix = "markers_form_"
    suffix = "_panel_parsed.csv"
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix):-len(suffix)]

    if name.endswith(".csv"):
        return name[:-4]

    raise ValueError(f"Cannot determine panel from filename: {name}")


def _source_key(value: str) -> str:
    """Normalize a source filename/path for manifest matching."""
    return Path(value.strip().replace("\\", "/")).name.casefold()


def _rows_for_panel(
    marker_sources: list[tuple[Path, list[dict[str, str]]]],
    extracted_path: Path,
) -> list[dict[str, str]]:
    """Find the manifest rows belonging to this extracted marker table."""
    target_name = extracted_path.name.casefold()
    target_panel = _panel_name_from_filename(extracted_path).casefold()

    explicit_matches = []
    legacy_candidates = []

    for manifest_path, rows in marker_sources:
        for row in rows:
            source_file = _source_key(row.get("source_file", ""))
            panel_id = row.get("panel_id", "").strip().casefold()

            if source_file:
                if source_file == target_name:
                    explicit_matches.append(row)
                continue

            # New per-panel manifests may be named after the panel.
            if (
                manifest_path.stem.casefold()
                in {
                    f"{target_panel}_mapping_review",
                    f"{target_panel}_marker_mapping_review",
                }
            ):
                explicit_matches.append(row)
            else:
                legacy_candidates.append(row)

    if explicit_matches:
        return explicit_matches

    # Backward compatibility: a single legacy manifest can be matched by
    # original marker + channel. Multiple legacy manifests are ambiguous.
    legacy_manifests = [
        (path, rows)
        for path, rows in marker_sources
        if path.parent == path.parents[0]
        and path.name.endswith(MARKER_MANIFEST_SUFFIX)
    ]
    if len(legacy_manifests) == 1:
        return legacy_candidates

    raise ValueError(
        f"No marker review rows found for {extracted_path.name}. "
        "Ensure the manifest contains source_file/panel_id, or is a "
        "single legacy marker_mapping_review.csv."
    )


def update_global_marker_channels(
    channel_path: Path,
    marker_names_path: Path,
    extracted_marker_files: list[Path],
    marker_sources: list[tuple[Path, list[dict[str, str]]]],
) -> None:
    panel_by_file = {
        path: _panel_name_from_filename(path)
        for path in extracted_marker_files
    }

    headers, rows = ensure_csv(
        channel_path, ["Marker Name"]
    )
    headers = [
        header
        for header in headers
        if header not in {"Comment", "Aliases"}
    ]
    rows = [
        {header: row.get(header, "") for header in headers}
        for row in rows
    ]

    reused_columns: list[str] = []
    for panel in sorted(set(panel_by_file.values())):
        if panel not in headers:
            headers.append(panel)
            for row in rows:
                row[panel] = ""
        else:
            reused_columns.append(panel)

    if reused_columns:
        typer.echo(
            "Following panel names were already taken by "
            "existing panels in the curated database:\n"
            f"{', '.join(reused_columns)}\n"
            "Please go back to the examine manifest, rename "
            "the file and redo the following steps."
        )

    by_name = {
        row.get("Marker Name", "").strip(): row
        for row in rows
        if row.get("Marker Name", "").strip()
    }

    for extracted_path, panel in panel_by_file.items():
        _, extracted_rows = read_csv(extracted_path)
        reviews = _rows_for_panel(marker_sources, extracted_path)

        for extracted in extracted_rows:
            original_marker = extracted.get("biological_marker", "").strip()
            channel_number = extracted.get("channel_number", "").strip()

            if not original_marker or not channel_number:
                continue

            matches = [
                review for review in reviews
                if review.get("original_marker", "").strip() == original_marker
                and review.get("channel_number", "").strip() == channel_number
            ]

            if len(matches) > 1:
                raise ValueError(
                    f"Ambiguous review rows for {extracted_path.name}: "
                    f"marker {original_marker!r}, channel {channel_number!r}."
                )
            if not matches:
                continue

            standardized = _final_marker_name(matches[0], proceed=True)
            if not standardized:
                continue

            if standardized not in by_name:
                new_row = {header: "" for header in headers}
                new_row["Marker Name"] = standardized
                rows.append(new_row)
                by_name[standardized] = new_row

            target = by_name[standardized]
            target[panel] = channel_number

    rows.sort(
        key=lambda row: row.get("Marker Name", "").strip().casefold()
    )
    write_csv(channel_path, headers, rows)
