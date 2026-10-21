import re
import tomllib
from pathlib import Path

import pandas as pd


IMAGE_EXTENSIONS = {".tif", ".tiff"}


def _resolve_path(path: str, project_dir: Path) -> Path:
    """Resolve a path relative to the project unless it is absolute."""
    path = Path(path)

    if path.is_absolute():
        return path

    return project_dir / path


def _read_form(form_path: Path) -> dict:
    """Read a TOML form."""
    with form_path.open("rb") as form_file:
        return tomllib.load(form_file)


def _extract_id(value: object, pattern: str) -> str | None:
    """Extract an identifier using the first regex capture group."""
    if pd.isna(value):
        return None

    match = re.search(pattern, str(value))

    if match is None:
        return None

    if match.lastindex:
        return match.group(1)

    return match.group(0)


def extract_clinical_tables(
    project_dir: Path,
    forms_dir: Path,
    output_dir: Path,
) -> str:
    """
    Select clinical features and match clinical records to image names
    using the completed TOML forms.
    """
    project_dir = project_dir.resolve()
    forms_dir = _resolve_path(str(forms_dir), project_dir)
    output_dir = _resolve_path(str(output_dir), project_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images_dir = project_dir / "data" / "processed" / "images"

    form_paths = sorted(forms_dir.glob("*.toml"))

    if not form_paths:
        return f"No clinical TOML forms found in:\n  {forms_dir}"

    if not images_dir.is_dir():
        raise FileNotFoundError(
            f"Populated images directory was not found:\n  {images_dir}"
        )

    image_paths = sorted(
        (
            path
            for path in images_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
        ),
        key=lambda path: str(path).lower(),
    )

    if not image_paths:
        return f"No TIFF images found in:\n  {images_dir}"

    reports = [
        "",
        "CLINICAL EXTRACTION",
        f"Found {len(form_paths)} clinical form(s):",
        f"Images to match: {len(image_paths)}",
    ]

    for form_path in form_paths:
        form = _read_form(form_path)

        source_config = form.get("source", {})
        matching_config = form.get("clinical_matching", {})
        review_config = form.get("review", {})

        source_csv = _resolve_path(
            source_config["path"],
            project_dir,
        )
        review_csv = _resolve_path(
            source_config["review_csv"],
            project_dir,
        )

        identifier_column = matching_config.get(
            "identifier_column", ""
        )
        image_name_regex = matching_config.get(
            "image_name_regex", ""
        )
        id_value_regex = matching_config.get(
            "id_value_regex", ""
        )

        if not identifier_column:
            raise ValueError(
                f"{form_path}: identifier_column is required."
            )

        if not image_name_regex or not id_value_regex:
            raise ValueError(
                f"{form_path}: both image_name_regex and "
                "id_value_regex are required."
            )

        # Validate regex syntax before processing the data.
        try:
            re.compile(image_name_regex)
            re.compile(id_value_regex)
        except re.error as error:
            raise ValueError(
                f"{form_path}: invalid identifier regex: {error}"
            ) from error

        for csv_path in (source_csv, review_csv):
            if not csv_path.is_file():
                raise FileNotFoundError(
                    f"CSV specified by {form_path} was not found:\n"
                    f"  {csv_path}"
                )

        clinical_table = pd.read_csv(source_csv)
        review_table = pd.read_csv(review_csv)

        if identifier_column not in clinical_table.columns:
            raise ValueError(
                f"{form_path}: identifier column "
                f"{identifier_column!r} was not found in "
                f"{source_csv.name}. Available columns: "
                f"{list(clinical_table.columns)}"
            )

        selection_row_index = review_config.get(
            "selection_row_index"
        )

        if selection_row_index is None:
            raise ValueError(
                f"{form_path}: review.selection_row_index is required."
            )

        if not 0 <= selection_row_index < len(review_table):
            raise ValueError(
                f"{form_path}: selection_row_index "
                f"{selection_row_index} is outside the review CSV "
                f"data rows (0–{len(review_table) - 1})."
            )

        selection_row = review_table.iloc[selection_row_index]

        # Select columns marked 1 in the final review row.
        selected_columns = []

        for column in review_table.columns:
            value = pd.to_numeric(
                pd.Series([selection_row[column]]),
                errors="coerce",
            ).iloc[0]

            if pd.isna(value) or value not in (0, 1):
                raise ValueError(
                    f"{review_csv}: selection row value for "
                    f"column {column!r} must be 0 or 1."
                )

            if value == 1:
                selected_columns.append(column)

        # The identifier must remain available for matching.
        if identifier_column not in selected_columns:
            selected_columns.append(identifier_column)

        missing_columns = [
            column
            for column in selected_columns
            if column not in clinical_table.columns
        ]

        if missing_columns:
            raise ValueError(
                f"{form_path}: selected columns are missing from "
                f"the original clinical CSV: {missing_columns}"
            )

        selected_table = clinical_table[selected_columns].copy()

        # Extract identifiers from the complete clinical dataset.
        selected_table["_match_id"] = selected_table[
            identifier_column
        ].map(lambda value: _extract_id(value, id_value_regex))

        unmatched_clinical = selected_table["_match_id"].isna()

        # Save selected clinical data without the internal matching column.
        output_stem = form_path.stem.removesuffix("_form")

        selected_output = output_dir / f"{output_stem}_selected.csv"

        selected_table.drop(
            columns=["_match_id"]
        ).to_csv(selected_output, index=False)

        # Extract an identifier from each image filename.
        image_records = []

        for image_path in image_paths:
            image_id = _extract_id(
                image_path.name,
                image_name_regex,
            )

            image_records.append(
                {
                    "image_path": image_path.relative_to(
                        project_dir
                    ).as_posix(),
                    "image_name": image_path.name,
                    "image_id": image_id,
                }
            )

        image_table = pd.DataFrame(image_records)

        # Left join preserves images even when no clinical record matches.
        matches = image_table.merge(
            selected_table,
            left_on="image_id",
            right_on="_match_id",
            how="left",
            indicator=True,
        )

        matched_images = matches["_merge"] == "both"
        unmatched_images = matches["image_id"].isna() | ~matched_images

        matches = matches.drop(
            columns=["_match_id", "_merge"]
        )

        matches_output = output_dir / f"{output_stem}_image_clinical_matches.csv"
        matches.to_csv(matches_output, index=False)

        reports.extend(
            [
                f"Form: {form_path.resolve()}",
                f"Original clinical CSV: {source_csv.resolve()}",
                f"Selected features: {len(selected_columns)} columns",
                f"Clinical rows: {len(clinical_table)}",
                f"Images matched: {matched_images.sum()}",
                f"Images unmatched: {unmatched_images.sum()}",
                f"Clinical rows without an extracted ID: "
                f"{unmatched_clinical.sum()}",
                f"Selected clinical output: {selected_output.resolve()}",
                f"Image-clinical matches: {matches_output.resolve()}",
            ]
        )

    return "\n".join(reports)