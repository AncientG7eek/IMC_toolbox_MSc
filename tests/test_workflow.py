"""End-to-end workflow tests that manually fill generated TOML forms.

These tests exercise the real service functions for the ``examine`` and
``extract`` stages against a throw-away project directory. They intentionally
do not touch the user's global reference files.
"""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import tifffile
import tomli_w

from imc_curator.progress_bar import ProgressManager
from imc_curator.services.curation.curate.input_loader import (
    load_extracted_clinical,
    load_extracted_markers,
)
from imc_curator.services.curation.curate.manifest_writer import (
    write_curation_manifests,
)
from imc_curator.services.curation.curate.standardize import (
    load_clinical_mapping,
    load_marker_mapping,
)
from imc_curator.services.curation.finalize.finalize import finalizer
from imc_curator.services.discovery.examine.csv_parser import (
    examine_marker_and_clinical_tables,
)
from imc_curator.services.discovery.examine.mcd_parser import (
    examine_mcd_files,
)
from imc_curator.services.discovery.examine.ome_parser import (
    examine_ome_metadata,
)
from imc_curator.services.discovery.extract.clinical_parser import (
    extract_clinical_tables,
)
from imc_curator.services.discovery.extract.marker_parser import (
    extract_marker_tables,
)
from imc_curator.services.discovery.extract.panel_map import (
    init_panel_map,
)
from imc_curator.services.discovery.extract.raw_tiff_extractor import (
    extract_raw_tiffs,
)
from imc_curator.services.discovery.extract.subset_tiffs import (
    _read_tiff_stack,
    subset_images,
)


MCD_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "mcd"
    / "20210305_NE_mockData1.mcd"
)


def _write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


def _ome_xml_single_page(
    channels: list[tuple[str, str]],
) -> str:
    channel_xml = []
    for index, (name, fluor) in enumerate(channels):
        channel_xml.append(
            f'<Channel ID="Channel:{index}" Name="{name}" '
            f'Fluor="{fluor}" SamplesPerPixel="1"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06">'
        '<Image ID="Image:0" Name="img">'
        '<Pixels ID="Pixels:0" DimensionOrder="XYCZT" Type="uint16" '
        'SizeX="2" SizeY="2" SizeC="%d" SizeZ="1" SizeT="1">'
        '%s</Pixels></Image></OME>'
    ) % (len(channels), "".join(channel_xml))


def _ome_xml_page(index: int, name: str, fluor: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06">'
        f'<Image ID="Image:{index}" Name="img{index}">'
        f'<Pixels ID="Pixels:{index}" DimensionOrder="XYCZT" Type="uint16" '
        'SizeX="2" SizeY="2" SizeC="1" SizeZ="1" SizeT="1">'
        f'<Channel ID="Channel:{index}" Name="{name}" Fluor="{fluor}" '
        'SamplesPerPixel="1"/></Pixels></Image></OME>'
    )


def _write_single_page_ome(
    path: Path,
    channels: list[tuple[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.zeros((len(channels), 2, 2), dtype="uint16")
    tifffile.imwrite(
        path,
        data,
        metadata={"axes": "CYX"},
        description=_ome_xml_single_page(channels),
        photometric="minisblack",
        planarconfig="separate",
    )


def _write_page_per_channel_ome(
    path: Path,
    channels: list[tuple[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tifffile.TiffWriter(path) as writer:
        for index, (name, fluor) in enumerate(channels):
            writer.write(
                np.zeros((2, 2), dtype="uint16"),
                description=_ome_xml_page(index, name, fluor),
            )


def _write_blank_tiff(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(
        path,
        np.zeros((1, 2, 2), dtype="uint16"),
        photometric="minisblack",
        planarconfig="separate",
    )


def _deep_update(target: dict, updates: dict) -> dict:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
    return target


def _edit_toml(path: Path, updates: dict) -> None:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    _deep_update(data, updates)
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [dict(row) for row in csv.DictReader(file)]


def _set_review_keep(
    review_csv_path: Path,
    reject_markers: set[str] | None = None,
) -> None:
    rows = _read_csv_rows(review_csv_path)
    reject_markers = reject_markers or set()
    for row in rows:
        marker = row.get("biological_marker", "") or row.get(
            "marker", ""
        )
        row["KEEP/REJECT [0/1]"] = "0" if marker in reject_markers else "1"

    fieldnames = list(rows[0].keys()) if rows else []
    review_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with review_csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class WorkflowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _project(self, name: str) -> Path:
        project = self.root / name
        project.mkdir(parents=True, exist_ok=True)
        return project

    def _run_ome_extract(
        self,
        project: Path,
        reject_markers: set[str],
    ) -> tuple[Path, Path]:
        unpacked = project / "data" / "raw" / "unpacked"
        output_dir = project / "curation_manifests" / "examine"
        markers_dir = output_dir / "markers"
        logs_dir = project / "logs"
        selected_panels_dir = project / "metadata" / "markers" / "selected"
        selected_images_dir = project / "data" / "raw" / "selected"
        extract_dir = project / "curation_manifests" / "extract"
        panel_map_path = init_panel_map(extract_dir / "image_panel_map.csv")

        with ProgressManager() as progress:
            examine_ome_metadata(
                input_dir=unpacked,
                output_dir=output_dir,
                logs_dir=logs_dir,
                project_dir=project,
                markers_output_dir=markers_dir,
                progress=progress,
            )

        form_paths = sorted(markers_dir.glob("*/*.toml"))
        self.assertEqual(len(form_paths), 1)
        review_csv = form_paths[0].with_name(
            form_paths[0].name.replace("markers_form_", "markers_review_")
        ).with_suffix(".csv")
        self.assertTrue(review_csv.is_file())
        _set_review_keep(review_csv, reject_markers)

        extract_marker_tables(
            project_dir=project,
            forms_dir=markers_dir,
            selected_panels_dir=selected_panels_dir,
            panel_map_path=panel_map_path,
        )
        subset_images(
            project_dir=project,
            images_output_dir=unpacked,
            selected_images_dir=selected_images_dir,
            panel_map_path=panel_map_path,
            selected_panels_dir=selected_panels_dir,
        )
        return selected_panels_dir, selected_images_dir

    def test_ome_single_page_end_to_end(self) -> None:
        project = self._project("ome_single")
        image_path = project / "data" / "raw" / "unpacked" / "panel_a" / "img1.ome.tiff"
        _write_single_page_ome(
            image_path,
            [("CD3", "Nd143"), ("SMA", "In115"), ("Ki67", "Pr141")],
        )

        selected_panels, selected_images = self._run_ome_extract(
            project,
            reject_markers={"SMA"},
        )

        panel_csv = next(selected_panels.glob("*.csv"))
        rows = _read_csv_rows(panel_csv)
        self.assertEqual(
            sorted(row["biological_marker"] for row in rows),
            ["CD3", "Ki67"],
        )
        self.assertEqual([row["channel_number"] for row in rows], ["0", "1"])

        selected_tiff = next(selected_images.rglob("*.ome.tiff"))
        self.assertEqual(_read_tiff_stack(selected_tiff).shape[0], 2)

    def test_ome_page_per_channel_end_to_end(self) -> None:
        project = self._project("ome_pages")
        image_path = project / "data" / "raw" / "unpacked" / "panel_b" / "img2.ome.tiff"
        _write_page_per_channel_ome(
            image_path,
            [("CD3", "Nd143"), ("SMA", "In115"), ("Ki67", "Pr141")],
        )

        selected_panels, selected_images = self._run_ome_extract(
            project,
            reject_markers={"CD3"},
        )

        panel_csv = next(selected_panels.glob("*.csv"))
        rows = _read_csv_rows(panel_csv)
        self.assertEqual(
            sorted(row["biological_marker"] for row in rows),
            ["Ki67", "SMA"],
        )
        selected_tiff = next(selected_images.rglob("*.ome.tiff"))
        self.assertEqual(_read_tiff_stack(selected_tiff).shape[0], 2)

    def test_mcd_end_to_end(self) -> None:
        project = self._project("mcd")
        raw_imc_dir = project / "metadata" / "raw_imc_data"
        raw_imc_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MCD_FIXTURE, raw_imc_dir / MCD_FIXTURE.name)

        output_dir = project / "curation_manifests" / "examine"
        markers_dir = output_dir / "markers"
        logs_dir = project / "logs"
        unpacked = project / "data" / "raw" / "unpacked"
        selected_images_dir = project / "data" / "raw" / "selected"
        selected_panels_dir = project / "metadata" / "markers" / "selected"
        extract_dir = project / "curation_manifests" / "extract"

        with ProgressManager() as progress:
            examine_mcd_files(
                project_dir=project,
                output_dir=output_dir,
                markers_output_dir=markers_dir,
                logs_dir=logs_dir,
                progress=progress,
            )

        form_paths = sorted(markers_dir.glob("*/*.toml"))
        self.assertEqual(len(form_paths), 1)
        review_csv = form_paths[0].with_name(
            form_paths[0].name.replace("markers_form_", "markers_review_")
        ).with_suffix(".csv")
        self.assertTrue(review_csv.is_file())
        _set_review_keep(review_csv, reject_markers={"107Ag"})

        extract_raw_tiffs(
            project_dir=project,
            markers_dir=markers_dir,
            images_output_dir=unpacked,
            selected_images_dir=selected_images_dir,
        )
        extract_marker_tables(
            project_dir=project,
            forms_dir=markers_dir,
            selected_panels_dir=selected_panels_dir,
            panel_map_path=init_panel_map(extract_dir / "image_panel_map.csv"),
        )

        panel_csv = next(selected_panels_dir.glob("*.csv"))
        rows = _read_csv_rows(panel_csv)
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [row["channel_number"] for row in rows],
            ["0", "1", "2", "3"],
        )

        selected_tiffs = sorted(selected_images_dir.rglob("*.tiff"))
        self.assertEqual(len(selected_tiffs), 3)
        for tiff_path in selected_tiffs:
            self.assertEqual(_read_tiff_stack(tiff_path).shape[0], 4)

    def test_csv_panel_end_to_end(self) -> None:
        project = self._project("csv_panel")
        marker_dir = project / "metadata" / "markers" / "unpacked"
        _write_csv(
            marker_dir / "my_panel.csv",
            ["marker_name", "channel_idx", "isotope"],
            [
                ["CD3", "0", "Nd143"],
                ["SMA", "1", "In115"],
                ["Ki67", "2", "Pr141"],
            ],
        )
        output_dir = project / "curation_manifests" / "examine"

        examine_marker_and_clinical_tables(
            project_dir=project,
            output_dir=output_dir,
        )

        markers_dir = output_dir / "markers"
        form_path = next(markers_dir.glob("*/*.toml"))
        _edit_toml(
            form_path,
            {
                "panel": {"name": "mycohort"},
                "marker_parsing": {
                    "biological_marker_column": "marker_name",
                    "channel_number_column": "channel_idx",
                    "metal_isotope_column": "isotope",
                },
            },
        )

        selected_panels_dir = project / "metadata" / "markers" / "selected"
        extract_dir = project / "curation_manifests" / "extract"
        extract_marker_tables(
            project_dir=project,
            forms_dir=markers_dir,
            selected_panels_dir=selected_panels_dir,
            panel_map_path=init_panel_map(extract_dir / "image_panel_map.csv"),
        )

        panel_csv = selected_panels_dir / "mycohort.csv"
        self.assertTrue(panel_csv.is_file())
        rows = _read_csv_rows(panel_csv)
        self.assertEqual(
            [row["biological_marker"] for row in rows],
            ["CD3", "Ki67", "SMA"],
        )
        self.assertEqual(
            [row["channel_number"] for row in rows],
            ["0", "1", "2"],
        )

    def test_clinical_csv_end_to_end(self) -> None:
        project = self._project("clinical_csv")
        clinical_dir = project / "metadata" / "clinical" / "unpacked"
        _write_csv(
            clinical_dir / "meta.csv",
            ["Sample_ID", "Indication", "Response"],
            [
                ["P1", "CRC", "Responder"],
                ["P2", "NSCLC", "NonResponder"],
                ["P3", "CRC", "Responder"],
            ],
        )
        images_dir = project / "data" / "raw" / "unpacked"
        for name in ("P1_img.tiff", "P2_img.tiff", "P3_img.tiff"):
            _write_blank_tiff(images_dir / name)

        output_dir = project / "curation_manifests" / "examine"
        examine_marker_and_clinical_tables(
            project_dir=project,
            output_dir=output_dir,
        )

        clinical_forms = output_dir / "clinical"
        form_path = next(clinical_forms.rglob("*.toml"))
        _edit_toml(
            form_path,
            {
                "cohort": {"name": "clin1"},
                "clinical_matching": {
                    "identifier_column": "Sample_ID",
                    "image_name_regex": "(P\\d+)_img",
                    "id_value_regex": "",
                },
            },
        )

        # Mark the identifier column 0 in the selection row to confirm it is
        # still retained as the left-most column for matching.
        review_csv = next(clinical_forms.rglob("clinical_review_*.csv"))
        table = pd.read_csv(review_csv)
        selection_index = int(
            tomllib.loads(form_path.read_text())["review"]["selection_row_index"]
        )
        table.loc[selection_index, "Sample_ID"] = "0"
        table.to_csv(review_csv, index=False)

        selected_dir = project / "metadata" / "clinical" / "selected"
        info_dir = project / "curation_manifests" / "extract" / "clinical"
        extract_clinical_tables(
            project_dir=project,
            forms_dir=clinical_forms,
            output_dir=selected_dir,
            info_output_dir=info_dir,
            images_dir=images_dir,
        )

        selected_csv = selected_dir / "clin1_selected.csv"
        matches_csv = selected_dir / "clin1_image_clinical_matches.csv"
        self.assertTrue(selected_csv.is_file())
        self.assertTrue(matches_csv.is_file())

        selected = pd.read_csv(selected_csv)
        self.assertEqual(selected.columns[0], "Sample_ID")
        self.assertEqual(
            list(selected.columns),
            ["Sample_ID", "Indication", "Response"],
        )

        matches = pd.read_csv(matches_csv)
        self.assertEqual(len(matches), 3)
        self.assertEqual(set(matches["image_id"]), {"P1", "P2", "P3"})


class FullPipelineTestCase(unittest.TestCase):
    """Exercise curate and finalize against a temporary global files dir."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.projects_root = self.root / "projects"
        self.global_root = self.root / "global"
        self.projects_root.mkdir(parents=True)
        self.global_root.mkdir(parents=True)

        self.env = mock.patch.dict(
            os.environ,
            {
                "IMC_CURATOR_PROJECTS_DIR": str(self.projects_root),
                "IMC_CURATOR_CURATED_DATABASE_DIR": str(self.global_root),
            },
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self._tmp.cleanup()

    def _build_project(self) -> Path:
        project = self.projects_root / "fullpipe"
        project.mkdir(parents=True, exist_ok=True)

        unpacked = project / "data" / "raw" / "unpacked"
        _write_single_page_ome(
            unpacked / "P1_roi.ome.tiff",
            [("CD3", "Nd143"), ("SMA", "In115")],
        )
        _write_single_page_ome(
            unpacked / "P2_roi.ome.tiff",
            [("CD3", "Nd143"), ("SMA", "In115")],
        )

        clinical_dir = project / "metadata" / "clinical" / "unpacked"
        _write_csv(
            clinical_dir / "meta.csv",
            ["Sample_ID", "Indication"],
            [["P1", "CRC"], ["P2", "NSCLC"]],
        )
        return project

    def test_full_curate_and_finalize(self) -> None:
        project = self._build_project()
        name = project.name

        output_dir = project / "curation_manifests" / "examine"
        with ProgressManager() as progress:
            examine_ome_metadata(
                input_dir=project / "data" / "raw" / "unpacked",
                output_dir=output_dir,
                logs_dir=project / "logs",
                project_dir=project,
                markers_output_dir=output_dir / "markers",
                progress=progress,
            )

        markers_dir = output_dir / "markers"
        ome_form = next(markers_dir.glob("*/*.toml"))
        ome_review = ome_form.with_name(
            ome_form.name.replace("markers_form_", "markers_review_")
        ).with_suffix(".csv")
        _set_review_keep(ome_review, reject_markers=set())

        examine_marker_and_clinical_tables(
            project_dir=project,
            output_dir=output_dir,
        )

        clinical_forms = output_dir / "clinical"
        clinical_form = next(clinical_forms.rglob("*.toml"))
        _edit_toml(
            clinical_form,
            {
                "cohort": {"name": "clin1"},
                "clinical_matching": {
                    "identifier_column": "Sample_ID",
                    "image_name_regex": "(P\\d+)_roi",
                    "id_value_regex": "",
                },
            },
        )

        selected_panels = project / "metadata" / "markers" / "selected"
        selected_images = project / "data" / "raw" / "selected"
        extract_dir = project / "curation_manifests" / "extract"
        panel_map_path = init_panel_map(extract_dir / "image_panel_map.csv")
        extract_marker_tables(
            project_dir=project,
            forms_dir=markers_dir,
            selected_panels_dir=selected_panels,
            panel_map_path=panel_map_path,
        )
        subset_images(
            project_dir=project,
            images_output_dir=project / "data" / "raw" / "unpacked",
            selected_images_dir=selected_images,
            panel_map_path=panel_map_path,
            selected_panels_dir=selected_panels,
        )
        extract_clinical_tables(
            project_dir=project,
            forms_dir=clinical_forms,
            output_dir=project / "metadata" / "clinical" / "selected",
            info_output_dir=extract_dir / "clinical",
            images_dir=selected_images,
        )

        # Curate: generate editable review manifests.
        marker_mapping = load_marker_mapping()
        clinical_mapping = load_clinical_mapping()
        marker_inputs = load_extracted_markers(
            project_name=str(project),
            marker_mapping=marker_mapping,
        )
        clinical_inputs = [
            load_extracted_clinical(
                path=path,
                clinical_mapping=clinical_mapping,
            )
            for path in sorted(
                (project / "metadata" / "clinical" / "selected").glob(
                    "*_image_clinical_matches.csv"
                )
            )
        ]
        write_curation_manifests(
            project_dir=project,
            marker_input=marker_inputs,
            clinical_input=clinical_inputs,
        )

        # Approve every suggested mapping.
        for review_csv in project.rglob("*_mapping_review.csv"):
            rows = _read_csv_rows(review_csv)
            for row in rows:
                row["approved"] = "1"
            fieldnames = list(rows[0].keys())
            with review_csv.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        # Finalize writes to the temporary global files directory.
        with mock.patch(
            "imc_curator.services.curation.finalize.finalize.typer.prompt",
            return_value="no",
        ):
            finalizer(name=name)

        self.assertTrue(
            (self.global_root / "global_marker_names.csv").is_file()
        )
        self.assertTrue(
            (self.global_root / "global_register_of_images.csv").is_file()
        )
        register_rows = _read_csv_rows(
            self.global_root / "global_register_of_images.csv"
        )
        self.assertTrue(register_rows)


if __name__ == "__main__":
    unittest.main()
