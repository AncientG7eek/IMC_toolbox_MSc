from pathlib import Path

import pandas as pd

from imc_curator.commands_code.discovery.examine.mcd_parser import (
    toml_string_list,
)
from imc_curator.commands_code.discovery.examine.submodules.ome_panel_parser import (
    assign_panels,
    load_regex_rules,
    parse_channel,
)
from imc_curator.commands_code.discovery.examine.submodules.panel_assignment import (
    append_assignments,
)
from imc_curator.commands_code.discovery.examine.submodules.panel_review_form import (
    create_panel_review,
)
from imc_curator.commands_code.discovery.examine.submodules.extract_ome_channels import (
    CHANNEL_COLUMNS,
    SCAN_COLUMNS,
    extract_all_tiff_metadata,
    write_csv,
)
from imc_curator.progress_bar import ProgressManager


def create_ome_review_form(
    *,
    output_dir: Path,
    tiff_files: list[str],
    channel_labels: list[str],
) -> Path:
    """Create an editable OME channel-selection form."""
    form_path = output_dir / "ome_channel_form.toml"
    tiff_file_comments = "\n".join(
        f"#   - {path}" for path in tiff_files
    ) or "#   No OME-TIFF files found."

    form_text = f'''# IMC CURATION — OME CHANNEL SELECTION FORM
#
# PURPOSE
# Select OME channel labels to retain.
#
# STEP 1 — REVIEW THE AVAILABLE FILES
#
# Available OME-TIFF files:
{tiff_file_comments}
#
# STEP 2 — SELECT CHANNEL LABELS TO KEEP
#
# The channel_labels array contains the unique channel names found in the
# OME-TIFF files. Scroll down to see it.
#
# Remove labels that should not be retained. Keep the TOML array syntax and
# quotation marks. An empty array means that no channel labels are selected.
#
# IMPORTANT
#   - Keep this file in TOML format.
#   - Do not remove or rename the keys below.
#   - Use TOML strings, including quotation marks.

[source]
tiff_files = {toml_string_list(tiff_files)}

[channel_selection]
channel_labels = {toml_string_list(channel_labels)}
'''

    form_path.write_text(form_text, encoding="utf-8")
    return form_path.resolve()


def examine_ome_metadata(
    input_dir: Path,
    output_dir: Path,
    logs_dir: Path,
    project_dir: Path,
    markers_output_dir: Path,
    progress: ProgressManager,
) -> str:
    """Extract OME metadata and write a channel-selection form."""
    input_dir = input_dir.expanduser().resolve()
    logs_dir = logs_dir.expanduser().resolve()
    project_dir = project_dir.expanduser().resolve()
    markers_output_dir = markers_output_dir.expanduser().resolve()

    # 1. Extract raw OME metadata.
    with progress.stage("Extracting TIFF metadata from ome"):
        channels, scan_records = extract_all_tiff_metadata(
            input_dir,
            progress=progress,
        )

    scan_csv = write_csv(
        logs_dir / "tiff_metadata_scan.csv",
        SCAN_COLUMNS,
        scan_records,
    )

    if not channels:
        return (
            "OME metadata examination finished with a warning.\n"
            "No channel information was found in the TIFF files.\n"
            f"TIFF scan report: {scan_csv}\n"
            "Channel parsing and panel identification were skipped."
        )

    tiff_file_count = len({
        channel["tiff_path"]
        for channel in channels
        if channel.get("tiff_path")
    })

    rules = load_regex_rules()
    parsed_channels = [
        parse_channel(channel, rules)
        for channel in progress.track(
            channels,
            description="Parsing OME channel names",
            total=len(channels),
        )
    ]
    panel_groups = assign_panels(parsed_channels)

    panel_review_count = 0
    assignments_entries: dict[str, list[str]] = {}
    for panel_id, group in panel_groups.items():
        rows = []
        for channel in group["channels"]:
            rows.append(
                {
                    "biological_marker": (
                        channel.get("panel_marker")
                        or channel.get("raw_name")
                        or ""
                    ),
                    "channel_number": channel.get("channel_number", ""),
                    "metal_isotope": (
                        channel.get("metal_ion")
                        or channel.get("raw_fluor")
                        or ""
                    ),
                }
            )

        source_tiff = group["tiff_paths"][0] if group["tiff_paths"] else ""
        source_path = source_tiff
        if input_dir.is_relative_to(project_dir):
            source_path = (
                input_dir.relative_to(project_dir).as_posix()
                + "/"
                + source_tiff
            )

        create_panel_review(
            panel_id=panel_id,
            panel_table=pd.DataFrame(
                rows,
                columns=[
                    "biological_marker",
                    "channel_number",
                    "metal_isotope",
                ],
            ),
            source_path=source_path,
            markers_output_dir=markers_output_dir,
            project_dir=project_dir,
            parsed_columns=True,
        )
        if input_dir.is_relative_to(project_dir):
            images_root = input_dir.relative_to(project_dir).as_posix()
            assignments_entries[f"{panel_id}.csv"] = [
                f"{images_root}/{tiff_path}"
                for tiff_path in group["tiff_paths"]
            ]
        panel_review_count += 1

    append_assignments(
        markers_output_dir / "assign_images_to_panels.toml",
        assignments_entries,
    )

    report = [
        "",
        "OME metadata examination complete",
        "=" * 34,
        "",
        "Output files:",
        f"  TIFF metadata scan:     {scan_csv}",
        f"  Panel review forms:     {markers_output_dir}",
        "",
        "Summary:",
        f"  OME-TIFF files found:   {tiff_file_count}",
        f"  Candidate panels:       {panel_review_count}",
    ]

    return "\n".join(report)
