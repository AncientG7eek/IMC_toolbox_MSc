import re
import tomllib
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import tifffile
from readimc import MCDFile


logger = logging.getLogger(__name__)


def _resolve_path(value: str | Path, project_dir: Path) -> Path:
    """Resolve a path relative to the project unless it is absolute."""
    path = Path(value)
    return path if path.is_absolute() else project_dir / path


def _read_form(form_path: Path) -> dict:
    with form_path.open("rb") as form_file:
        return tomllib.load(form_file)


def _extract_id(value: str, pattern: str, field_name: str) -> str:
    """Extract an ID with the first capture group, or the whole match."""
    if not pattern.strip():
        raise ValueError(f"{field_name} regex is empty.")

    try:
        match = re.search(pattern, value)
    except re.error as exc:
        raise ValueError(f"Invalid {field_name} regex {pattern!r}: {exc}") from exc

    if match is None:
        raise ValueError(
            f"Could not extract an ID from {value!r} using {field_name} "
            f"regex {pattern!r}."
        )

    return match.group(1) if match.lastindex else match.group(0)


def _safe_stem(value: str) -> str:
    """Make a readable, filesystem-safe filename component."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "unnamed"


def _clean_target_name(
    channel_name: str,
    pattern: str,
) -> str:
    """Return a cleaned target name using an optional regex.

    If the regex contains a capture group, return group 1.
    Otherwise, return the full match.
    If the regex is blank, preserve the original channel name.
    """
    name = str(channel_name or "").strip()

    if not pattern.strip():
        return name

    try:
        match = re.search(pattern, name)
    except re.error as exc:
        raise ValueError(
            f"Invalid target_name_regex {pattern!r}: {exc}"
        ) from exc

    if match is None:
        logger.warning(
            "Target-name regex %r did not match channel name %r; "
            "preserving the original name.",
            pattern,
            name,
        )
        return name

    if match.lastindex:
        return (match.group(1) or "").strip()

    return match.group(0).strip()


def _read_txt_table(path: Path) -> pd.DataFrame:
    """Read a delimited text file with delimiter inference."""
    try:
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(
            path,
            sep=None,
            engine="python",
            encoding="latin-1",
        )


def _resolve_form_files(
    values: list[str],
    project_dir: Path,
    fallback_dir: Path,
    extension: str,
) -> list[Path]:
    """Resolve form paths and fall back to recursive discovery if necessary."""
    paths = [
        _resolve_path(value, project_dir)
        for value in values
        if str(value).strip()
    ]
    existing = [path.resolve() for path in paths if path.is_file()]
    if existing:
        return sorted(set(existing), key=lambda p: str(p).casefold())

    if fallback_dir.is_dir():
        return sorted(
            (
                path.resolve()
                for path in fallback_dir.rglob("*")
                if path.is_file() and path.suffix.lower() == extension
            ),
            key=lambda p: str(p).casefold(),
        )
    return []


def extract_raw_imc(
    project_dir: Path,
    form_path: Path,
    output_dir: Path,
) -> str:
    """Extract selected MCD channels as TIFFs, panel metadata, and optional TXT tables."""
    project_dir = project_dir.resolve()
    form_path = _resolve_path(form_path, project_dir).resolve()
    output_dir = _resolve_path(output_dir, project_dir).resolve()

    if not form_path.is_file():
        return f"No raw IMC examination form found:\n  {form_path}"

    form = _read_form(form_path)
    source = form.get("source", {})
    selection = form.get("channel_selection", {})
    connection = form.get("txt_mcd_connection", {})
    target_cleaning = form.get("target_name_cleaning", {})

    target_name_regex = str(
        target_cleaning.get("target_name_regex", "") or ""
    ).strip()

    # Validate the configured regex even if some acquisitions have no selected channels.
    if target_name_regex:
        try:
            re.compile(target_name_regex)
        except re.error as exc:
            raise ValueError(
                f"{form_path}: invalid target_name_cleaning.target_name_regex: {exc}"
            ) from exc

    selected_labels = selection.get("channel_labels", [])
    if not isinstance(selected_labels, list) or not all(
        isinstance(label, str) for label in selected_labels
    ):
        raise ValueError(
            f"{form_path}: channel_selection.channel_labels must be "
            "an array of strings."
        )
    selected_label_set = set(selected_labels)

    # Resolve the raw-data root from the MCD paths in the form.
    raw_root: Path | None = None
    for value in source.get("mcd_files", []):
        candidate = _resolve_path(value, project_dir)
        if candidate.is_file():
            raw_root = candidate.parent
            break
    if raw_root is None:
        raw_root = project_dir / "data" / "raw"

    mcd_files = _resolve_form_files(
        source.get("mcd_files", []),
        project_dir,
        raw_root,
        ".mcd",
    )
    txt_files = _resolve_form_files(
        source.get("txt_files", []),
        project_dir,
        raw_root,
        ".txt",
    )

    if not mcd_files:
        return (
            "Raw IMC extraction skipped: no MCD files from the form "
            f"could be found.\nForm: {form_path}"
        )

    tiff_dir = output_dir / "images"
    txt_output_dir = output_dir / "txt"
    tiff_dir.mkdir(parents=True, exist_ok=True)

    panel_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    tiff_count = 0
    acquisition_count = 0

    for mcd_path in mcd_files:
        try:
            with MCDFile(mcd_path) as mcd:
                for slide in mcd.slides:
                    for acquisition in slide.acquisitions:
                        acquisition_count += 1
                        labels = list(acquisition.channel_labels)
                        names = list(acquisition.channel_names)

                        selected_indices = [
                            i for i, label in enumerate(labels)
                            if label in selected_label_set
                        ]

                        for index in selected_indices:
                            panel_rows.append(
                                {
                                    "mcd_file": mcd_path.relative_to(
                                        project_dir
                                    ).as_posix()
                                    if mcd_path.is_relative_to(project_dir)
                                    else str(mcd_path),
                                    "slide_id": slide.id,
                                    "acquisition_id": acquisition.id,
                                    "acquisition_name": (
                                        acquisition.description or ""
                                    ),
                                    "channel_index": index,
                                    "channel_label": labels[index],
                                    "channel_name": (
                                        names[index] if index < len(names) else ""
                                    ),
                                }
                            )

                        if not selected_indices:
                            logger.warning(
                                "No selected channels in %s, acquisition %s",
                                mcd_path,
                                acquisition.id,
                            )
                            continue

                        image = mcd.read_acquisition(acquisition)
                        if image is None:
                            raise ValueError(
                                f"Acquisition {acquisition.id} returned no image."
                            )

                        # readimc acquisition images are channel-first (C, Y, X).
                        if image.ndim != 3:
                            raise ValueError(
                                f"Unexpected image shape {image.shape} for "
                                f"acquisition {acquisition.id}; expected (C, Y, X)."
                            )

                        if image.shape[0] != len(labels):
                            raise ValueError(
                                f"Image has {image.shape[0]} channels but metadata "
                                f"has {len(labels)} labels in acquisition "
                                f"{acquisition.id}."
                            )

                        selected_image = image[selected_indices, :, :]
                        output_name = (
                            f"{_safe_stem(mcd_path.stem)}"
                            f"_slide{slide.id}"
                            f"_acq{acquisition.id}.tiff"
                        )
                        tiff_path = tiff_dir / output_name

                        tifffile.imwrite(
                            tiff_path,
                            selected_image,
                            metadata={
                                "axes": "CYX",
                                "channel_labels": [
                                    labels[i] for i in selected_indices
                                ],
                                "channel_names": [
                                    names[i] if i < len(names) else ""
                                    for i in selected_indices
                                ],
                            },
                        )
                        tiff_count += 1

        except Exception as exc:
            logger.exception("Failed to extract MCD file %s", mcd_path)
            errors.append(f"{mcd_path}: {exc}")

    # Build one marker table per unique selected-channel panel.
    # Different acquisitions with identical channel metadata share one panel CSV.
    panels_dir = output_dir / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)

    marker_columns = [
        "channel",
        "name",
        "keep",
        "KEEP/REJECT [0/1]",
        "biological_marker",
        "channel_number",
        "metal_isotope",
    ]

    # Group the existing per-acquisition channel rows into panel definitions.
    acquisition_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    for row in panel_rows:
        acquisition_key = (
            row["mcd_file"],
            str(row["slide_id"]),
            str(row["acquisition_id"]),
        )
        acquisition_groups.setdefault(acquisition_key, []).append(row)

    panel_ids_by_signature: dict[tuple, str] = {}
    panel_output_rows: dict[str, list[dict[str, Any]]] = {}
    acquisition_panel_rows: list[dict[str, Any]] = []

    for acquisition_key, rows in acquisition_groups.items():
        # Keep channels in the order they occur in the acquisition.
        rows = sorted(rows, key=lambda row: row["channel_index"])

        signature = tuple(
            (
                int(row["channel_index"]),
                str(row["channel_label"]),
                str(row["channel_name"]),
                _clean_target_name(
                    str(row["channel_name"]),
                    target_name_regex,
                ),
            )
            for row in rows
        )

        if signature not in panel_ids_by_signature:
            panel_id = f"panel_{len(panel_ids_by_signature) + 1:03d}"
            panel_ids_by_signature[signature] = panel_id

            marker_rows = []
            for row in rows:
                channel_label = str(row["channel_label"])
                original_name = str(row["channel_name"])
                target_name = _clean_target_name(
                    original_name,
                    target_name_regex,
                )

                marker_rows.append(
                    {
                        "channel": channel_label,
                        "name": target_name,
                        "keep": 1,
                        "KEEP/REJECT [0/1]": 1,
                        "biological_marker": target_name,
                        "channel_number": int(row["channel_index"]) + 1,
                        "metal_isotope": channel_label,
                    }
                )

            panel_output_rows[panel_id] = marker_rows

        panel_id = panel_ids_by_signature[signature]

        mcd_file, slide_id, acquisition_id = acquisition_key
        tiff_name = (
            f"{_safe_stem(Path(mcd_file).stem)}"
            f"_slide{slide_id}"
            f"_acq{acquisition_id}.tiff"
        )

        acquisition_panel_rows.append(
            {
                "tiff_file": f"images/{tiff_name}",
                "mcd_file": mcd_file,
                "slide_id": slide_id,
                "acquisition_id": acquisition_id,
                "panel_id": panel_id,
                "panel_file": f"panels/{panel_id}.csv",
            }
        )

    # Write each unique panel once.
    for panel_id, rows in panel_output_rows.items():
        panel_path = panels_dir / f"{panel_id}.csv"
        pd.DataFrame(rows, columns=marker_columns).to_csv(
            panel_path,
            index=False,
        )

    # Map each extracted acquisition TIFF to its unique panel definition.
    panel_map_path = output_dir / "acquisition_panel_map.csv"
    pd.DataFrame(
        acquisition_panel_rows,
        columns=[
            "tiff_file",
            "mcd_file",
            "slide_id",
            "acquisition_id",
            "panel_id",
            "panel_file",
        ],
    ).to_csv(panel_map_path, index=False)

    # TXT matching is optional: blank regex/coordinate fields mean skip TXT parsing.
    mcd_regex = str(connection.get("mcd_name_regex", "") or "").strip()
    txt_regex = str(connection.get("txt_name_regex", "") or "").strip()
    x_column = str(connection.get("x_coordinate_column", "") or "").strip()
    y_column = str(connection.get("y_coordinate_column", "") or "").strip()

    txt_processed = 0
    txt_skip_reason = ""

    if not txt_files:
        txt_skip_reason = "No TXT files were listed/found."
    elif not all([mcd_regex, txt_regex, x_column, y_column]):
        txt_skip_reason = (
            "TXT extraction skipped because one or more TXT-specific form "
            "fields are blank (filename regexes and X/Y coordinate columns)."
        )
    else:
        txt_output_dir.mkdir(parents=True, exist_ok=True)
        mcd_ids: dict[str, list[Path]] = {}
        for mcd_path in mcd_files:
            try:
                mcd_id = _extract_id(
                    mcd_path.stem,
                    mcd_regex,
                    "mcd_name",
                )
                mcd_ids.setdefault(mcd_id, []).append(mcd_path)
            except ValueError as exc:
                errors.append(str(exc))

        for txt_path in txt_files:
            try:
                txt_id = _extract_id(
                    txt_path.stem,
                    txt_regex,
                    "txt_name",
                )
                matching_mcds = mcd_ids.get(txt_id, [])
                if not matching_mcds:
                    logger.warning(
                        "No MCD filename matched TXT file %s (ID %r)",
                        txt_path,
                        txt_id,
                    )
                    continue

                table = _read_txt_table(txt_path)
                missing = [
                    column for column in (x_column, y_column)
                    if column not in table.columns
                ]
                if missing:
                    raise ValueError(
                        f"{txt_path}: coordinate column(s) {missing} not found. "
                        f"Available columns: {list(table.columns)}"
                    )

                table["x_coordinate"] = pd.to_numeric(
                    table[x_column], errors="coerce"
                )
                table["y_coordinate"] = pd.to_numeric(
                    table[y_column], errors="coerce"
                )
                table["matched_mcd_files"] = ";".join(
                    str(path.relative_to(project_dir))
                    if path.is_relative_to(project_dir)
                    else str(path)
                    for path in matching_mcds
                )
                table["match_id"] = txt_id

                output_path = (
                    txt_output_dir
                    / f"{_safe_stem(txt_path.stem)}_coordinates.csv"
                )
                table.to_csv(output_path, index=False)
                txt_processed += 1

            except Exception as exc:
                logger.exception("Failed to process TXT file %s", txt_path)
                errors.append(f"{txt_path}: {exc}")

    report = [
        "",
        "RAW IMC EXTRACTION",
        f"Form: {form_path}",
        f"MCD files found: {len(mcd_files)}",
        f"Acquisitions visited: {acquisition_count}",
        f"Selected channel labels: {selected_labels}",
        f"TIFF images written: {tiff_count}",
        f"Unique panel tables: {len(panel_output_rows)}",
        f"Panel tables directory: {panels_dir.resolve()}",
        f"Acquisition-to-panel map: {panel_map_path.resolve()}",
        f"TIFF output directory: {tiff_dir.resolve()}",
        f"TXT files found: {len(txt_files)}",
        f"TXT tables processed: {txt_processed}",
    ]

    if txt_skip_reason:
        report.append(txt_skip_reason)
    elif txt_files and txt_processed == 0:
        report.append(
            "TXT files were configured, but no matched TXT coordinate tables "
            "were written. Check the filename regexes and coordinate columns."
        )

    if errors:
        report.append(f"Errors: {len(errors)}")
        report.extend(f"  - {error}" for error in errors)

    return "\n".join(report)