"""Extract MCD TIFFs using panel review assignments instead of a channel form."""

from __future__ import annotations

import csv
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import tifffile
from readimc import MCDFile

from imc_curator.config import load_search_config

if TYPE_CHECKING:
    from imc_curator.progress_bar import ProgressManager


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "unnamed"


def _project_relative(path: Path, project_dir: Path) -> str:
    path = path.resolve()
    if path.is_relative_to(project_dir):
        return path.relative_to(project_dir).as_posix()
    return str(path)


def _load_assignments(markers_dir: Path) -> dict[str, list[str]]:
    path = markers_dir / "assign_images_to_panels.toml"
    if not path.is_file():
        return {}

    with path.open("rb") as file:
        data = tomllib.load(file)

    raw = data.get("images_by_marker", {})
    return {
        str(key): [str(value) for value in values]
        for key, values in raw.items()
    }


def _load_kept_metals(markers_dir: Path) -> dict[str, set[str]]:
    kept: dict[str, set[str]] = {}
    for panel_dir in markers_dir.iterdir():
        if not panel_dir.is_dir():
            continue

        review_csv = panel_dir / f"markers_review_{panel_dir.name}.csv"
        if not review_csv.is_file():
            continue

        kept_labels = set()
        with review_csv.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            for row in csv.DictReader(file):
                if str(row.get("KEEP/REJECT [0/1]", "")).strip() != "1":
                    continue
                label = str(row.get("metal_isotope", "")).strip()
                if label:
                    kept_labels.add(label)

        kept[panel_dir.name] = kept_labels

    return kept


def extract_raw_tiffs(
    project_dir: Path,
    markers_dir: Path,
    selected_images_dir: Path,
    progress: "ProgressManager | None" = None,
) -> str:
    """Write MCD TIFFs for kept panel channels."""
    project_dir = project_dir.resolve()
    markers_dir = markers_dir.expanduser().resolve()
    selected_images_dir = selected_images_dir.expanduser().resolve()

    assignments = _load_assignments(markers_dir)
    panel_by_image: dict[str, str] = {}
    for panel_file, image_paths in assignments.items():
        if not panel_file.endswith(".csv"):
            continue
        panel_id = panel_file[:-4]
        for image_path in image_paths:
            panel_by_image[image_path] = panel_id

    kept_metals_by_panel = _load_kept_metals(markers_dir)

    search_config = load_search_config()
    destination = Path(
        search_config["categories"]["raw_imc_data"]["destination"]
    )
    if not destination.is_absolute():
        destination = project_dir / destination

    if not destination.is_dir():
        return f"No raw IMC data directory found at: {destination}"

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

    tiff_count = 0
    acquisition_count = 0
    errors: list[str] = []

    iterable = (
        progress.track(
            mcd_files,
            description="Extracting MCD TIFFs",
            total=len(mcd_files),
            item_description=lambda path: path.name,
        )
        if progress
        else mcd_files
    )

    for mcd_path in iterable:
        try:
            with MCDFile(mcd_path) as mcd:
                for slide in mcd.slides:
                    for acquisition in slide.acquisitions:
                        acquisition_count += 1

                        output_name = (
                            f"{_safe_stem(mcd_path.stem)}"
                            f"_slide{slide.id}"
                            f"_acq{acquisition.id}.tiff"
                        )
                        tiff_path = (
                            selected_images_dir
                            / _safe_stem(mcd_path.parent.name)
                            / output_name
                        )
                        relative_tiff_path = _project_relative(
                            tiff_path,
                            project_dir,
                        )
                        panel_id = panel_by_image.get(relative_tiff_path)
                        if panel_id is None:
                            continue

                        kept_labels = kept_metals_by_panel.get(
                            panel_id,
                            set(),
                        )
                        labels = list(acquisition.channel_labels)
                        names = list(acquisition.channel_names)
                        selected_indices = [
                            index
                            for index, label in enumerate(labels)
                            if label in kept_labels
                        ]

                        if not selected_indices:
                            continue

                        image = mcd.read_acquisition(acquisition)
                        if image is None or image.ndim != 3:
                            raise ValueError(
                                f"Unexpected image shape for acquisition "
                                f"{acquisition.id}."
                            )
                        if image.shape[0] != len(labels):
                            raise ValueError(
                                f"Image channel count {image.shape[0]} "
                                f"does not match metadata count {len(labels)}."
                            )

                        selected_image = image[selected_indices, :, :]
                        tiff_path.parent.mkdir(parents=True, exist_ok=True)
                        tifffile.imwrite(
                            tiff_path,
                            selected_image,
                            metadata={
                                "axes": "CYX",
                                "channel_labels": [
                                    labels[index]
                                    for index in selected_indices
                                ],
                                "channel_names": [
                                    names[index]
                                    if index < len(names)
                                    else ""
                                    for index in selected_indices
                                ],
                            },
                        )
                        tiff_count += 1

        except Exception as exc:
            errors.append(f"{mcd_path}: {exc}")

    report = [
        "",
        "RAW IMC EXTRACTION",
        f"MCD files found: {len(mcd_files)}",
        f"Acquisitions visited: {acquisition_count}",
        f"TIFF images written: {tiff_count}",
        f"TIFF output directory: {selected_images_dir.resolve()}",
    ]
    if errors:
        report.append(f"Errors: {len(errors)}")
        report.extend(f"  - {error}" for error in errors)

    return "\n".join(report)
