
import json
from pathlib import Path

import pandas as pd

from imc_curator.config import load_search_config


REVIEW_COLUMN = "KEEP/REJECT [0/1]"
MAX_EXAMPLE_IMAGES = 6
IMAGE_EXTENSIONS = {".tif", ".tiff"}


def toml_string(value: str) -> str:
    """Encode a string as a valid TOML basic string."""
    return json.dumps(str(value), ensure_ascii=False)



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
        # The file is outside the project directory.
        return str(path)



def markers_csv_parser(
    markers_file_path: Path,
    review_csv_path: Path,
    project_dir: Path,
) -> str:
    """Create an editable marker review CSV and its TOML instructions."""
    marker_table = pd.read_csv(markers_file_path)

    marker_table[REVIEW_COLUMN] = 1

    review_csv_path.parent.mkdir(parents=True, exist_ok=True)
    marker_table.to_csv(review_csv_path, index=False)

    source_path = path_for_form(markers_file_path, project_dir)
    review_path = path_for_form(review_csv_path, project_dir)

    return f'''# IMC CURATION — MARKER PANEL FORM
#
# PURPOSE
# This form helps configure automatic parsing of a marker-panel table
# from the IMC repository currently being curated.
#
# Read these instructions before filling in the answers.
#
# STEP 1 — REVIEW THE LINKED CSV
# Open the review CSV specified below:
#
#     {review_path}
#
# The CSV contains the original marker-panel table and an additional
# column named "KEEP/REJECT [0/1]".
#
# Fill this column for each marker:
#   1 = keep this marker
#   0 = reject this marker
#
# Do not rename the review column. Keep the original table columns intact.
# Save the CSV after editing it.
#
# In the bottom part of this document named [marker_parsing]:
#
# STEP 2 — IDENTIFY THE MARKER COLUMN (REQUIRED)
# Enter the exact column name that contains the biological marker names.
# Copy the column name exactly as it appears in the CSV header.
#
# STEP 3 — OPTIONAL MARKER-NAME CLEANING
# If marker values contain extra text that must be removed, enter a regex
# pattern that extracts the desired marker name.
#
# STEP 4 — IDENTIFY OPTIONAL COLUMNS
# If the table has a column containing channel numbers, enter its exact
# column name. Otherwise, leave the answer as an empty string.
#
# If the table has a column containing metal isotopes, enter its exact
# column name. Otherwise, leave the answer as an empty string.
#
# STEP 5 — OPTIONAL METAL-NAME CLEANING
# If metal values contain extra text that must be removed, enter a regex
# pattern that extracts the desired marker name.
#
# Leave the regex empty if no cleaning is needed.
# The regex will be used by the parsing script; it is not applied here.
#
# IMPORTANT
#   - Keep this file in TOML format.
#   - Do not remove or rename the keys below.
#   - Answers must be TOML strings, including the quotation marks.
#   - Leave optional answers as '' if they are not applicable.
#   - The next parsing step will read this form and the linked review CSV.

[source]
# Original marker-panel table supplied in the populated project.
path = {toml_string(source_path)}

# Editable review CSV. This is where you mark markers as keep/reject.
review_csv = {toml_string(review_path)}

[marker_parsing]
# REQUIRED: exact column name containing biological marker names.
biological_marker_column = ''

# OPTIONAL: regex used to extract/clean the biological marker name.
biological_marker_regex = ''

# OPTIONAL: exact column name containing channel numbers.
channel_number_column = ''

# OPTIONAL: exact column name containing metal isotope names.
metal_isotope_column = ''

# OPTIONAL: regex used to extract/clean the metal isotope name.
metal_isotope_regex = ''
'''



def clinical_csv_parser(
    clinical_file_path: Path,
    review_csv_path: Path,
    example_image_paths: list[Path],
    project_dir: Path,
) -> str:
    """
    Create an editable clinical review CSV and its TOML instructions.

    The review CSV contains up to six example rows and a final selection
    row initialized to 1.
    """
    clinical_table = pd.read_csv(clinical_file_path).head(6).copy()

    # Add the feature-selection row.
    selection_row = pd.DataFrame(
        [[1] * len(clinical_table.columns)],
        columns=clinical_table.columns,
    )
    clinical_review = pd.concat(
        [clinical_table, selection_row],
        ignore_index=True,
    )

    # Zero-based index of the selection row.
    selection_row_index = len(clinical_table)
    review_csv_path.parent.mkdir(parents=True, exist_ok=True)
    clinical_review.to_csv(review_csv_path, index=False)

    source_path = path_for_form(clinical_file_path, project_dir)
    review_path = path_for_form(review_csv_path, project_dir)

    image_paths = [
        path_for_form(path, project_dir)
        for path in example_image_paths[:MAX_EXAMPLE_IMAGES]
    ]

    return f'''# IMC CURATION — CLINICAL FEATURE FORM
#
# PURPOSE
# This form configures how clinical information is selected and matched
# to the corresponding IMC images in the project being curated.
#
# STEP 1 — REVIEW THE LINKED CLINICAL CSV
# Open the review CSV specified below:
#
#     {review_path}
#
# The CSV contains up to six example rows from the original clinical table,
# followed by a final row initialized to 1.
#
# In the final row:
#   1 = keep this column as a clinical feature
#   0 = do not keep this column as a clinical feature
#
# Replace 1 with 0 for every column that is not a clinical feature or that
# you do not want to retain. Leave 1 for features you want to keep.
#
# Do not remove the final selection row or rename the table columns.
# Save the CSV after editing it.
#
# In the bottom part of this document named [clinical_matching]:
#
# STEP 2 — IDENTIFY THE CLINICAL ID COLUMN (REQUIRED)
# Enter the exact column name that contains the identifier used to connect
# a clinical-table row to an image. This may identify a patient, image,
# ROI, or another entity shared between the clinical data and image names.
#
# STEP 3 — DEFINE THE IMAGE-NAME REGEX (REQUIRED)
# Inspect the example image paths below (very bottom of the document). 
# Enter a regex that extracts the identifier from an image filename or path.
#
# STEP 4 — DEFINE THE CLINICAL-ID REGEX (REQUIRED)
# Enter a regex that extracts the corresponding identifier from values in
# the clinical ID column selected above.
#
# The parsing script will apply the two regexes and compare their extracted
# values for equality. The patterns must therefore return comparable IDs.
#
# IMPORTANT
#   - Keep this file in TOML format.
#   - Do not remove or rename the keys below.
#   - Answers must be TOML strings, including the quotation marks.
#   - The review CSV and this TOML form are both required for parsing.
#   - The image paths below are examples to help you design the regexes.

[source]
# Original clinical table supplied in the populated project.
path = {toml_string(source_path)}

# Editable review CSV containing sample rows and the feature-selection row.
review_csv = {toml_string(review_path)}

[clinical_matching]
# REQUIRED: exact column name containing the clinical identifiers.
identifier_column = ''

# REQUIRED: regex that extracts an identifier from an image filename/path.
image_name_regex = ''

# REQUIRED: regex that extracts the corresponding identifier from a
# value in the selected clinical identifier column.
id_value_regex = ''

[review]
# Zero-based row index of the final 1/0 feature-selection row in review_csv.
selection_row_index = {selection_row_index}

[examples]
# Example image paths from the populated images directory.
# Use these to determine how image names encode the clinical identifier.
image_paths = {toml_string_list(image_paths)}
'''


def create_form(text: str, output_path: Path) -> Path:
    """Write TOML form text to disk and return the output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return output_path



def examine_marker_and_clinical_tables(project_dir: Path) -> str:
    """
    Discover populated marker and clinical CSVs and generate review forms.

    Forms and review CSVs are saved in separate marker and clinical folders.
    The populate manifest is not read.
    """
    project_dir = project_dir.resolve()
    search_config = load_search_config()
    categories = search_config["categories"]

    def destination_path(category: str) -> Path:
        destination = Path(categories[category]["destination"])
        if destination.is_absolute():
            return destination
        return project_dir / destination

    images_path = destination_path("images")
    markers_path = destination_path("marker_metadata")
    clinical_path = destination_path("clinical_data")

    output_dir = project_dir / "curation_manifests" / "examine"
    markers_output_dir = output_dir / "markers"
    clinical_output_dir = output_dir / "clinical"

    markers_output_dir.mkdir(parents=True, exist_ok=True)
    clinical_output_dir.mkdir(parents=True, exist_ok=True)

    # Find up to six image examples for clinical matching.
    if images_path.is_dir():
        example_image_paths = sorted(
            (
                path
                for path in images_path.rglob("*")
                if path.is_file()
                and path.suffix.lower() in IMAGE_EXTENSIONS
            ),
            key=lambda path: str(path).lower(),
        )[:MAX_EXAMPLE_IMAGES]
    else:
        example_image_paths = []

    marker_table_forms: list[tuple[Path, Path]] = []
    clinical_table_forms: list[tuple[Path, Path]] = []

    # Generate marker forms.
    if markers_path.is_dir():
        marker_files = sorted(
            (
                path
                for path in markers_path.rglob("*")
                if path.is_file()
                and path.suffix.lower() == ".csv"
            ),
            key=lambda path: str(path).lower(),
        )

        for markers_file in marker_files:
            stem = markers_file.stem

            review_csv_path = (
                markers_output_dir / f"markers_review_{stem}.csv"
            )
            form_path = markers_output_dir / f"markers_form_{stem}.toml"

            form_text = markers_csv_parser(
                markers_file_path=markers_file,
                review_csv_path=review_csv_path,
                project_dir=project_dir,
            )
            form_path = create_form(form_text, form_path).resolve()
            marker_table_forms.append((markers_file.resolve(), form_path))

    # Generate clinical forms.
    if clinical_path.is_dir():
        clinical_files = sorted(
            (
                path
                for path in clinical_path.rglob("*")
                if path.is_file()
                and path.suffix.lower() == ".csv"
            ),
            key=lambda path: str(path).lower(),
        )

        for clinical_file in clinical_files:
            stem = clinical_file.stem

            review_csv_path = (
                clinical_output_dir / f"clinical_review_{stem}.csv"
            )
            form_path = clinical_output_dir / f"clinical_form_{stem}.toml"

            form_text = clinical_csv_parser(
                clinical_file_path=clinical_file,
                review_csv_path=review_csv_path,
                example_image_paths=example_image_paths,
                project_dir=project_dir,
            )
            form_path = create_form(form_text, form_path).resolve()
            clinical_table_forms.append((clinical_file.resolve(), form_path))

    # Build the terminal report.
    report_lines = [
        "",
        "Marker and clinical tables examination complete",
        "=" * 47,
        "",
        f"Found {len(marker_table_forms)} marker panel table(s):",
    ]

    if marker_table_forms:
        report_lines.extend(
            f"  {source_path}"
            for source_path, _ in marker_table_forms
        )
        report_lines.append(
            "Please fill the following forms to parse them automatically:"
        )
        report_lines.extend(
            f"  {form_path}"
            for _, form_path in marker_table_forms
        )
    else:
        report_lines.append("  No marker panel tables found.")

    report_lines.extend([
        "",
        f"Found {len(clinical_table_forms)} clinical feature table(s):",
    ])

    if clinical_table_forms:
        report_lines.extend(
            f"  {source_path}"
            for source_path, _ in clinical_table_forms
        )
        report_lines.append(
            "Please fill the following forms to parse them automatically:"
        )
        report_lines.extend(
            f"  {form_path}"
            for _, form_path in clinical_table_forms
        )
    else:
        report_lines.append("  No clinical feature tables found.")

    return "\n".join(report_lines)