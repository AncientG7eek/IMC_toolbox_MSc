"""Create marker panel review CSVs and TOML forms for panel curation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


REVIEW_COLUMN = "KEEP/REJECT [0/1]"


def _toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def create_panel_review(
    *,
    panel_id: str,
    panel_table: pd.DataFrame,
    source_path: str,
    markers_output_dir: Path,
    project_dir: Path,
    parsed_columns: bool,
) -> tuple[Path, Path]:
    """Write a panel review CSV and TOML form under markers/<panel_id>/."""
    review_dir = markers_output_dir / panel_id
    review_dir.mkdir(parents=True, exist_ok=True)

    review_csv_path = review_dir / f"markers_review_{panel_id}.csv"
    form_path = review_dir / f"markers_form_{panel_id}.toml"

    table = panel_table.copy()
    table[REVIEW_COLUMN] = 1
    table.to_csv(review_csv_path, index=False)

    review_csv_path = review_csv_path.resolve()
    project_dir = project_dir.resolve()
    if review_csv_path.is_relative_to(project_dir):
        review_reference = review_csv_path.relative_to(project_dir).as_posix()
    else:
        review_reference = str(review_csv_path)
    if parsed_columns:
        form_text = f'''# IMC CURATION — SELECTED PANEL REVIEW FORM
#
# PURPOSE
# Review the channels in a panel discovered from OME or MCD data.
#
# The linked CSV contains:
#   biological_marker, channel_number, metal_isotope
#
# Fill KEEP/REJECT [0/1]:
#   1 = keep this channel
#   0 = reject this channel

[source]
path = {_toml_string(source_path)}
review_csv = {_toml_string(review_reference)}

[marker_parsing]
# OPTIONAL: regex used to extract/clean the biological marker name.
biological_marker_regex = ''

# OPTIONAL: regex used to extract/clean the metal isotope name.
metal_isotope_regex = ''
'''
    else:
        form_text = f'''# IMC CURATION — MARKER PANEL FORM
#
# PURPOSE
# Review a standalone marker-panel table.

[source]
path = {_toml_string(source_path)}
review_csv = {_toml_string(review_reference)}

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

    form_path.write_text(form_text, encoding="utf-8")
    return review_csv_path.resolve(), form_path.resolve()
