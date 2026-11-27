from __future__ import annotations

from pathlib import Path

import typer

from imc_curator.services.curation.finalize.common import (
    ensure_csv,
    read_csv,
    write_csv,
)
from imc_curator.services.curation.finalize.mapping import _final_clinical_mapping


CLINICAL_COLUMNS = [
    "Standardized Feature",
    "Standardized Value",
    "Cohort",
    "Original Feature",
    "Original Value",
]


IMAGE_CLINICAL_COLUMNS = [
    "global_path",
    "relative_path",
    "Cohort",
    "Standardized Feature",
    "Standardized Value",
]


def update_global_clinical_values(
    path: Path,
    manifest_rows: list[dict[str, str]],
    cohort: str,
    proceed: bool,
) -> None:
    headers, rows = ensure_csv(path, CLINICAL_COLUMNS)
    existing = {
        tuple(row.get(column, "").strip() for column in CLINICAL_COLUMNS)
        for row in rows
    }
    existing_cohorts = {
        row.get("Cohort", "").strip().casefold()
        for row in rows
        if row.get("Cohort", "").strip()
    }
    reused_cohorts: list[str] = []

    for review in manifest_rows:
        original_feature = review.get("original_feature", "").strip()
        original_value = review.get("original_value", "").strip()
        review_cohort = review.get("cohort", "").strip() or cohort
        if (
            review_cohort.casefold() in existing_cohorts
            and review_cohort not in reused_cohorts
        ):
            reused_cohorts.append(review_cohort)
        standardized_feature, standardized_value = (
            _final_clinical_mapping(review, proceed)
        )

        if not all(
            [
                original_feature,
                original_value,
                standardized_feature,
                standardized_value,
            ]
        ):
            continue

        record = (
            standardized_feature,
            standardized_value,
            review_cohort,
            original_feature,
            original_value,
        )
        if record in existing:
            continue

        rows.append(dict(zip(headers, record)))
        existing.add(record)

    rows.sort(
        key=lambda row: (
            row.get("Standardized Feature", "").strip().casefold(),
            row.get("Standardized Value", "").strip().casefold(),
            row.get("Cohort", "").strip().casefold(),
        )
    )
    write_csv(path, headers, rows)

    if reused_cohorts:
        typer.echo(
            "Following clinical cohort names were already taken by "
            "existing cohorts in the curated database:"
        )
        typer.echo(", ".join(reused_cohorts))
        typer.echo(
            "Please go back to the examine manifest, rename the cohort "
            "and redo the following steps."
        )


def update_global_image_clinical(
    path: Path,
    match_files: list[Path],
    clinical_sources: list[tuple[Path, list[dict[str, str]]]],
    project_name: str,
    relative_images_dir: str,
    proceed: bool,
) -> None:
    headers, rows = ensure_csv(path, IMAGE_CLINICAL_COLUMNS)
    headers = list(IMAGE_CLINICAL_COLUMNS)
    rows = [
        {column: row.get(column, "") for column in headers}
        for row in rows
    ]
    existing = {
        tuple(row.get(column, "").strip() for column in IMAGE_CLINICAL_COLUMNS)
        for row in rows
    }

    reviews_by_source: dict[str, list[dict[str, str]]] = {}
    for _, review_rows in clinical_sources:
        for review in review_rows:
            source_file = review.get("source_file", "").strip()
            if source_file:
                reviews_by_source.setdefault(source_file, []).append(review)

    for match_file in match_files:
        cohort = match_file.stem.removesuffix("_image_clinical_matches")
        review_rows = reviews_by_source.get(match_file.name, [])
        review_map = {}

        for review in review_rows:
            feature, value = _final_clinical_mapping(review, proceed)
            original_feature = review.get("original_feature", "").strip()
            original_value = review.get("original_value", "").strip()
            if not feature or not value or not original_feature:
                continue
            key = (original_feature.casefold(), original_value.casefold())
            review_map[key] = (feature, value)

        _, match_rows = read_csv(match_file)
        for match_row in match_rows:
            image = match_row.get("image_path", "").strip()
            if not image:
                continue

            for column, value in match_row.items():
                if column in {"image_path", "image_name", "image_id"}:
                    continue
                value = value.strip()
                if not value:
                    continue
                key = (column.casefold(), value.casefold())
                mapping = review_map.get(key)
                if mapping is None:
                    continue

                record = {
                    "global_path": "",
                    "relative_path": f"{project_name}/{image}",
                    "Cohort": cohort,
                    "Standardized Feature": mapping[0],
                    "Standardized Value": mapping[1],
                }
                record_key = tuple(
                    record[column] for column in IMAGE_CLINICAL_COLUMNS
                )
                if record_key not in existing:
                    rows.append(record)
                    existing.add(record_key)

    rows.sort(
        key=lambda row: (
            row.get("Cohort", "").strip().casefold(),
            row.get("relative_path", "").strip().casefold(),
            row.get("Standardized Feature", "").strip().casefold(),
            row.get("Standardized Value", "").strip().casefold(),
        )
    )
    write_csv(path, headers, rows)


def add_paths_to_image_clinical(
    image_clinical_path: Path,
    image_register_path: Path,
) -> None:
    """Populate global_path/relative_path in the image-clinical file."""
    headers, rows = ensure_csv(
        image_clinical_path,
        IMAGE_CLINICAL_COLUMNS,
    )
    headers = list(IMAGE_CLINICAL_COLUMNS)
    rows = [
        {column: row.get(column, "") for column in headers}
        for row in rows
    ]

    register_headers, register_rows = read_csv(image_register_path)
    register_by_image = {
        row.get("relative_path", "").strip(): row
        for row in register_rows
        if row.get("relative_path", "").strip()
    }

    for row in rows:
        relative_path = row.get("relative_path", "").strip()
        register_row = register_by_image.get(relative_path)
        if register_row is not None:
            row["global_path"] = register_row.get(
                "global_path",
                "",
            ).strip()
            row["relative_path"] = register_row.get(
                "relative_path",
                "",
            ).strip()

    write_csv(image_clinical_path, headers, rows)
