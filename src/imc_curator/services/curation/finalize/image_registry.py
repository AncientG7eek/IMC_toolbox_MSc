from __future__ import annotations

from pathlib import Path

import tifffile

from imc_curator.services.curation.finalize.common import (
    ensure_csv,
    read_csv,
    write_csv,
)


IMAGE_REGISTER_COLUMNS = [
    "global_path",
    "relative_path",
    "shape",
    "panel_name",
    "cohort_name",
    "project_name",
]


def update_global_image_register(
    register_path: Path,
    all_images_dir: Path,
    project_dir: Path,
    selected_images_dir: Path,
    panel_map_path: Path,
    image_clinical_path: Path,
    project_name: str,
    relative_images_dir: str,
) -> None:
    headers, rows = ensure_csv(register_path, IMAGE_REGISTER_COLUMNS)

    existing_by_relative = {
        row.get("relative_path", "").strip(): row
        for row in rows
        if row.get("relative_path", "").strip()
    }
    existing_by_global = {
        row.get("global_path", "").strip(): row
        for row in rows
        if row.get("global_path", "").strip()
    }

    used_ordinals = {
        int(Path(row.get("global_path", "")).stem)
        for row in rows
        if row.get("global_path", "").strip()
        and Path(row.get("global_path", "")).stem.isdigit()
    }
    next_ordinal = max(used_ordinals, default=0) + 1

    _, panel_map_rows = read_csv(panel_map_path)
    panel_by_image = {
        row.get("tiff_file", "").strip(): Path(
            row.get("panel_file", "")
        ).stem
        for row in panel_map_rows
        if row.get("tiff_file", "").strip()
    }

    _, image_clinical_rows = read_csv(image_clinical_path)
    cohort_by_image = {}
    for row in image_clinical_rows:
        image = row.get("image", "").strip()
        cohort = row.get("Cohort", "").strip()
        if image and cohort:
            cohort_by_image.setdefault(image, cohort)

    all_images_dir.mkdir(parents=True, exist_ok=True)
    image_paths = sorted(
        (
            path
            for path in selected_images_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".tif", ".tiff"}
        ),
        key=lambda path: str(path).casefold(),
    )

    for image_path in image_paths:
        project_image_path = image_path.relative_to(
            selected_images_dir
        ).as_posix()
        relative_path = (
            f"{project_name}/{relative_images_dir}/{project_image_path}"
        )

        existing_row = existing_by_relative.get(relative_path)
        if existing_row:
            global_path = existing_row.get("global_path", "").strip()
        else:
            global_path = (
                f"{all_images_dir.as_posix()}/{next_ordinal}.tiff"
            )
            next_ordinal += 1

            selected_key = image_path.relative_to(project_dir).as_posix()

            shape = []
            try:
                with tifffile.TiffFile(image_path) as tif:
                    if tif.series:
                        shape = list(tif.series[0].shape)
            except Exception:
                shape = []

            row = {
                "global_path": global_path,
                "relative_path": relative_path,
                "shape": str(shape),
                "panel_name": panel_by_image.get(
                    selected_key,
                    "",
                ),
                "cohort_name": cohort_by_image.get(
                    selected_key,
                    "",
                ),
                "project_name": project_name,
            }
            rows.append(row)
            existing_by_relative[relative_path] = row
            existing_by_global[global_path] = row

        symlink_path = all_images_dir / Path(global_path).name
        if symlink_path.is_symlink() or symlink_path.exists():
            continue
        symlink_path.symlink_to(image_path.resolve())

    rows.sort(
        key=lambda row: (
            row.get("project_name", "").strip().casefold(),
            row.get("cohort_name", "").strip().casefold(),
            row.get("panel_name", "").strip().casefold(),
            row.get("relative_path", "").strip().casefold(),
        )
    )
    write_csv(register_path, headers, rows)
