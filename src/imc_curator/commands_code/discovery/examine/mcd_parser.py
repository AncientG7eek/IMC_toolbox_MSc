
import json
import logging
from pathlib import Path

from imc_curator.commands_code.discovery.examine.submodules.mcd_inspector import (
    inspect_mcd,
)
from imc_curator.config import load_search_config


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


def create_mcd_review_form(
    *,
    output_dir: Path,
    project_dir: Path,
    mcd_files: list[Path],
    txt_files: list[Path],
    channel_labels: list[str],
) -> tuple[Path, Path | None]:
    """Create an editable MCD channel-selection and TXT-matching form."""
    output_dir.mkdir(parents=True, exist_ok=True)

    form_path = output_dir / "mcd_channel_form.toml"
    preview_path: Path | None = None

    # Write a separate preview containing at most 1,000 lines.
    if txt_files:
        preview_path = output_dir / "txt_preview_1000_lines.txt"

        with txt_files[0].open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as source:
            with preview_path.open("w", encoding="utf-8") as preview:
                for line_number, line in enumerate(source):
                    if line_number >= 1000:
                        break
                    preview.write(line)

    mcd_paths = [
        path_for_form(path, project_dir)
        for path in mcd_files
    ]
    txt_paths = [
        path_for_form(path, project_dir)
        for path in txt_files
    ]

    preview_reference = (
        path_for_form(preview_path, project_dir)
        if preview_path is not None
        else ""
    )

    mcd_file_comments = "\n".join(
        f"#   - {path}" for path in mcd_paths
    ) or "#   No MCD files found."

    txt_file_comments = "\n".join(
        f"#   - {path}" for path in txt_paths
    ) or "#   No TXT files found."

    form_text = f'''# IMC CURATION — MCD CHANNEL AND TXT MATCHING FORM
#
# PURPOSE
# Select MCD channel labels to retain and, when TXT files are available,
# identify the relationship between the MCD and TXT data.
#
# STEP 1 — REVIEW THE AVAILABLE FILES
#
# Available MCD files:
{mcd_file_comments}
#
# Available TXT files:
{txt_file_comments}
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
# ##### ONLY IF MCD AND TXT FILES PRESENT #####
#
# STEP 3 — IDENTIFY THE MCD/TXT CONNECTION (IF APPLICABLE)
#
# Inspect the TXT preview:
#
#     {preview_reference or "No TXT preview was generated."}
#
# Select the exact MCD and TXT paths from the lists above.
# Enter the exact TXT column names for the X and Y coordinates.
# Leave coordinate fields empty if they cannot be identified.
#
# IMPORTANT
#   - Keep this file in TOML format.
#   - Do not remove or rename the keys below.
#   - Use TOML strings, including quotation marks.
#   - The preview contains at most the first 1,000 lines of one TXT file.
#   - The preview does not modify the original TXT file.
#   - TXT matching fields can remain empty when TXT files are unavailable.

[source]
mcd_files = {toml_string_list(mcd_paths)}
txt_files = {toml_string_list(txt_paths)}
txt_preview = {toml_string(preview_reference)}

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

##### ONLY IF STEP 3 APPLICABLE #####

[txt_mcd_connection]
# mcd file name cleaning regex to extract ID on witch 
# corresponding mcd and txt files will be mapped.
mcd_name_regex = ''

# txt file name cleaning regex to extract ID on witch 
# corresponding mcd and txt files will be mapped.
txt_name_regex = ''

# Exact TXT header for the X coordinate.
x_coordinate_column = ''

# Exact TXT header for the Y coordinate.
y_coordinate_column = ''
'''

    form_path.write_text(form_text, encoding="utf-8")
    return form_path.resolve(), (
        preview_path.resolve() if preview_path is not None else None
    )


def examine_mcd_files(project_dir: Path, output_dir: Path) -> str:
    """Examine populated MCD files and write an IMC manifest and review form."""
    project_dir = project_dir.resolve()
    output_dir = output_dir.resolve()

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

    # Discover TXT files associated with the raw IMC data directory.
    txt_files = sorted(
        (
            path
            for path in destination.rglob("*")
            if path.is_file() and path.suffix.lower() == ".txt"
        ),
        key=lambda path: str(path).casefold(),
    )

    inspected_files = []
    successful_count = 0
    acquisition_count = 0
    readable_image_count = 0

    for mcd_path in mcd_files:
        try:
            records = inspect_mcd(mcd_path)

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

    manifest_message = (
        "No valid MCD acquisitions were inspected; "
        "no IMC manifest was created."
    )

    if successful_count:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "imc_manifest.toml"

        lines = [
            "schema_version = 1",
            "",
        ]

        for item in inspected_files:
            relative_path = item["path"].relative_to(
                project_dir
            ).as_posix()

            lines.extend(
                [
                    "[[mcd_files]]",
                    f"path = {toml_string(relative_path)}",
                    (
                        "inspection_status = "
                        f"{toml_string(item['status'])}"
                    ),
                ]
            )

            if item["error"] is not None:
                lines.append(
                    f"error = {toml_string(item['error'])}"
                )

            lines.append("")

            for acquisition in item["acquisitions"]:
                lines.extend(
                    [
                        "[[mcd_files.acquisitions]]",
                        f"slide_id = {acquisition['slide_id']}",
                        (
                            "acquisition_id = "
                            f"{acquisition['acquisition_id']}"
                        ),
                        (
                            "acquisition_name = "
                            f"{toml_string(acquisition.get('acquisition_name', ''))}"
                        ),
                        f"width_px = {acquisition['width_px']}",
                        f"height_px = {acquisition['height_px']}",
                        (
                            "channel_names = "
                            f"{toml_array(acquisition.get('channel_names', []))}"
                        ),
                        (
                            "channel_labels = "
                            f"{toml_array(acquisition.get('channel_labels', []))}"
                        ),
                    ]
                )

                if "image_available" in acquisition:
                    lines.append(
                        "image_available = "
                        + (
                            "true"
                            if acquisition["image_available"]
                            else "false"
                        )
                    )

                if acquisition.get("image_shape") is not None:
                    shape = acquisition["image_shape"]
                    lines.append(
                        "image_shape = ["
                        + ", ".join(str(int(value)) for value in shape)
                        + "]"
                    )

                if acquisition.get("image_error"):
                    lines.append(
                        "image_error = "
                        f"{toml_string(acquisition['image_error'])}"
                    )

                lines.append("")

        manifest_path.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        manifest_message = f"IMC manifest: {manifest_path}"

    # Collect unique channel labels in their original discovery order.
    all_channel_labels = list(
        dict.fromkeys(
            label
            for item in inspected_files
            if item["status"] == "success"
            for acquisition in item["acquisitions"]
            for label in acquisition.get("channel_labels", [])
        )
    )

    form_path, preview_path = create_mcd_review_form(
        output_dir=output_dir,
        project_dir=project_dir,
        mcd_files=mcd_files,
        txt_files=txt_files,
        channel_labels=all_channel_labels,
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
            manifest_message,
            f"MCD channel-selection form: {form_path}",
            (
                f"TXT preview (first 1,000 lines): {preview_path}"
                if preview_path is not None
                else "TXT preview: not generated (no TXT files found)"
            ),
        ]
    )
