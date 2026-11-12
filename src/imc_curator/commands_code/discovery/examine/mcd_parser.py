
import json
import logging
import re
from pathlib import Path

import pandas as pd
import tomli_w

from imc_curator.commands_code.discovery.examine.submodules.mcd_inspector import (
    inspect_mcd,
)
from imc_curator.commands_code.discovery.examine.submodules.panel_assignment import (
    append_assignments,
)
from imc_curator.commands_code.discovery.examine.submodules.panel_review_form import (
    create_panel_review,
)
from imc_curator.config import (
    get_unpacked_images_dir,
    load_config,
    load_search_config,
)
from imc_curator.commands_code.discovery.signature import (
    build_panel_id,
    build_panel_signature,
)
from imc_curator.progress_bar import ProgressManager


logger = logging.getLogger(__name__)


def toml_string(value: str) -> str:
    """Encode a string as a valid TOML basic string."""
    return json.dumps(str(value), ensure_ascii=False)


def toml_array(values: list[str]) -> str:
    """Encode a list of strings as a TOML array."""
    return "[" + ", ".join(toml_string(value) for value in values) + "]"


def toml_string_list(values: list[str]) -> str:
    """Format a TOML array with one string per line."""
    if not values:
        return "[]"

    items = ",\n".join(
        f"    {toml_string(value)}"
        for value in values
    )
    return f"[\n{items},\n]"


def path_for_form(path: Path, project_dir: Path) -> str:
    """Prefer project-relative paths in generated forms."""
    path = path.resolve()
    project_dir = project_dir.resolve()

    try:
        return path.relative_to(project_dir).as_posix()
    except ValueError:
        return str(path)


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "unnamed"


def create_mcd_review_form(
    *,
    output_dir: Path,
    project_dir: Path,
    mcd_files: list[Path],
    channel_labels: list[str],
) -> Path:
    """Create an editable MCD channel-selection form."""
    output_dir.mkdir(parents=True, exist_ok=True)

    form_path = output_dir / "mcd_channel_form.toml"

    mcd_paths = [
        path_for_form(path, project_dir)
        for path in mcd_files
    ]

    mcd_file_comments = "\n".join(
        f"#   - {path}" for path in mcd_paths
    ) or "#   No MCD files found."

    form_text = f'''# IMC CURATION — MCD CHANNEL SELECTION FORM
#
# PURPOSE
# Select MCD channel labels to retain.
#
# STEP 1 — REVIEW THE AVAILABLE FILES
#
# Available MCD files:
{mcd_file_comments}
#
# STEP 2 — SELECT CHANNEL LABELS TO KEEP
#
# The channel_labels array contains the unique labels found in the
# successfully inspected MCD acquisitions. Scroll down to see it.
#
# Remove labels that should not be retained. Below the array there
# is a place to input an optional regex to clean the label text into
# pure target marker name. Leave empty if there is no need to clean.
# Keep the TOML array syntax and quotation marks.
# An empty array means that no channel labels are selected.
#
# IMPORTANT
#   - Keep this file in TOML format.
#   - Do not remove or rename the keys below.
#   - Use TOML strings, including quotation marks.

[source]
mcd_files = {toml_string_list(mcd_paths)}

[channel_selection]
channel_labels = {toml_string_list(channel_labels)}

# OPTIONAL: clean/extract the target name from each MCD channel name.
# If blank, the original channel name is used.
# If the regex has a capture group, group 1 is used as the target name.
# Otherwise, the first complete regex match is used.
# Examples:
#   '^.*?_(CD\\d+)$'  -> extracts a target such as CD3
#   '^'               -> matches the beginning of the name (not useful for extraction)
[target_name_cleaning]
target_name_regex = ''
'''

    form_path.write_text(form_text, encoding="utf-8")
    return form_path.resolve()


def examine_mcd_files(
        project_dir: Path, 
        output_dir: Path,
        markers_output_dir: Path,
        logs_dir: Path,
        progress: ProgressManager,
) -> str:
    """Examine populated MCD files and write an IMC manifest and review form."""
    project_dir = project_dir.resolve()
    markers_output_dir = markers_output_dir.expanduser().resolve()
    logs_dir = logs_dir.expanduser().resolve()

    search_config = load_search_config()
    destination = Path(
        search_config["categories"]["raw_imc_data"]["destination"]
    )

    if not destination.is_absolute():
        destination = project_dir / destination

    if not destination.is_dir():
        return (
            "MCD examination skipped.\n"
            f"No raw IMC data directory found at: {destination}"
        )

    mcd_files = sorted(
        (
            path
            for path in destination.rglob("*")
            if path.is_file() and path.suffix.lower() == ".mcd"
        ),
        key=lambda path: str(path).casefold(),
    )

    if not mcd_files:
        return f"No MCD files found in: {destination}"

    inspected_files = []
    acquisition_log_records = []
    successful_count = 0
    acquisition_count = 0
    readable_image_count = 0

    for mcd_path in progress.track(
        mcd_files,
        description="Inspecting MCD files",
        total=len(mcd_files),
    ):
        try:
            records = inspect_mcd(mcd_path)
            acquisition_log_records.extend(
                record
                for record in records
                if record.get("record_type") == "acquisition"
            )

            # Only acquisition records belong in mcd_files.acquisitions.
            acquisitions = [
                record
                for record in records
                if record.get("record_type", "acquisition") == "acquisition"
            ]

            if not acquisitions:
                raise ValueError(
                    "No acquisition records were found in this MCD."
                )

            successful_count += 1
            acquisition_count += len(acquisitions)
            readable_image_count += sum(
                record.get("image_available") is True
                for record in acquisitions
            )

            inspected_files.append(
                {
                    "path": mcd_path,
                    "status": "success",
                    "acquisitions": acquisitions,
                    "error": None,
                }
            )

        except Exception as exc:
            logger.exception("Could not examine MCD file %s", mcd_path)
            inspected_files.append(
                {
                    "path": mcd_path,
                    "status": "failed",
                    "acquisitions": [],
                    "error": str(exc),
                }
            )

    log_path = logs_dir / "mcd_acquisition_log.toml"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    safe_records = [
        {
            key: ("" if value is None else value)
            for key, value in record.items()
        }
        for record in acquisition_log_records
    ]
    log_path.write_bytes(
        tomli_w.dumps({"acquisitions": safe_records}).encode("utf-8")
    )

    panel_review_count = 0
    panels_by_signature: dict[tuple[str, ...], dict] = {}
    images_output_dir = get_unpacked_images_dir(
        project_dir=project_dir,
        config=load_config(),
    )

    for item in inspected_files:
        if item["status"] != "success":
            continue

        for acquisition in item["acquisitions"]:
            labels = acquisition.get("channel_labels", [])
            names = acquisition.get("channel_names", [])
            rows = []

            for index, label in enumerate(labels):
                marker = (
                    str(label).strip()
                    if index < len(labels) and str(label).strip()
                    else str(names[index]).strip()
                )
                metal_isotope = str(names[index]).strip()
                rows.append(
                    {
                        "biological_marker": marker,
                        "channel_number": index,
                        "metal_isotope": metal_isotope,
                    }
                )

            signature_records = [
                {
                    "biological_marker": row["biological_marker"],
                    "raw_name": row["biological_marker"],
                    "raw_fluor": row["metal_isotope"],
                    "metal_ion": row["metal_isotope"],
                }
                for row in rows
            ]
            signature = build_panel_signature(
                signature_records,
                marker_key="biological_marker",
                raw_name_key="raw_name",
                raw_fluor_key="raw_fluor",
            )
            signature_key = tuple(signature)

            if signature_key not in panels_by_signature:
                source_path = item["path"].relative_to(
                    project_dir
                ).as_posix()
                panels_by_signature[signature_key] = {
                    "panel_id": build_panel_id(signature),
                    "rows": rows,
                    "source_path": source_path,
                    "image_paths": [],
                }

            output_name = (
                f"{_safe_stem(item['path'].stem)}"
                f"_slide{acquisition['slide_id']}"
                f"_acq{acquisition['acquisition_id']}.tiff"
            )
            tiff_path = (
                images_output_dir
                / _safe_stem(item["path"].parent.name)
                / output_name
            )
            if tiff_path.is_relative_to(project_dir):
                relative_image_path = tiff_path.relative_to(
                    project_dir
                ).as_posix()
            else:
                relative_image_path = str(tiff_path)

            panels_by_signature[signature_key]["image_paths"].append(
                relative_image_path
            )

    assignment_entries = {}
    for panel in panels_by_signature.values():
        create_panel_review(
            panel_id=panel["panel_id"],
            panel_table=pd.DataFrame(
                panel["rows"],
                columns=[
                    "biological_marker",
                    "channel_number",
                    "metal_isotope",
                ],
            ),
            source_path=panel["source_path"],
            markers_output_dir=markers_output_dir,
            project_dir=project_dir,
            parsed_columns=True,
        )
        assignment_entries[f"{panel['panel_id']}.csv"] = panel["image_paths"]
        panel_review_count += 1

    append_assignments(
        markers_output_dir / "assign_images_to_panels.toml",
        assignment_entries,
    )

    return "\n".join(
        [
            "",
            "MCD examination complete",
            "=" * 24,
            f"MCD files found: {len(mcd_files)}",
            f"MCD files inspected successfully: {successful_count}",
            f"MCD files that failed: {len(mcd_files) - successful_count}",
            f"Acquisitions found: {acquisition_count}",
            f"Acquisitions with readable image data: {readable_image_count}",
            f"MCD acquisition log: {log_path}",
            f"Panel review forms: {markers_output_dir}",
            f"Candidate panels: {panel_review_count}",
        ]
    )
