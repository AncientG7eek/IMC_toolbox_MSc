from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from readimc import MCDFile

from imc_curator.services.discovery.examine.submodules.extract_ome_channels import (
    extract_tiff_metadata,
)
from imc_curator.services.discovery.examine.csv_parser import (
    clinical_csv_parser,
    markers_csv_parser,
)


FIXTURES = Path(__file__).parent / "fixtures"


class FixtureScenarioTests(unittest.TestCase):
    def test_ome_all_channels_single_page(self) -> None:
        path = FIXTURES / "ome" / "2021_52_ROI9_fullstacks.tiff"
        self.assertTrue(path.is_file())
        channels, scan = extract_tiff_metadata(path, path.parent)
        self.assertEqual(scan["status"], "ok")
        self.assertGreater(len(channels), 1)

    def test_ome_channels_per_page(self) -> None:
        path = FIXTURES / "ome" / "S00T1_ROI2.ome.tiff"
        self.assertTrue(path.is_file())
        channels, scan = extract_tiff_metadata(path, path.parent)
        self.assertEqual(scan["status"], "ok")
        self.assertGreater(len(channels), 1)

    def test_csv_panel_form(self) -> None:
        path = FIXTURES / "panels" / "Melanoma_panel.csv"
        self.assertTrue(path.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            form = markers_csv_parser(
                path,
                Path(tmp) / "markers_review_Melanoma_panel.csv",
                FIXTURES.parent,
            )
            self.assertIn("[marker_parsing]", form)
            self.assertIn("biological_marker_column", form)

    def test_xlsx_panel_form(self) -> None:
        path = FIXTURES / "panels" / "marker_panel_info.xlsx"
        self.assertTrue(path.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            form = markers_csv_parser(
                path,
                Path(tmp) / "markers_review_marker_panel_info.csv",
                FIXTURES.parent,
            )
            self.assertIn("[marker_parsing]", form)

    def test_clinical_xlsx_form(self) -> None:
        path = FIXTURES / "clinical" / "metadata.xlsx"
        self.assertTrue(path.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            form = clinical_csv_parser(
                path,
                Path(tmp) / "clinical_review_metadata.csv",
                FIXTURES.parent,
            )
            self.assertIn("[clinical_matching]", form)

    def test_mcd_fixture_is_readable(self) -> None:
        path = FIXTURES / "mcd" / "20210305_NE_mockData1.mcd"
        self.assertTrue(path.is_file())
        with MCDFile(path) as mcd:
            self.assertEqual(len(mcd.slides), 1)
            self.assertEqual(len(mcd.slides[0].acquisitions), 3)
            acquisition = mcd.slides[0].acquisitions[0]
            self.assertGreater(len(acquisition.channel_names), 0)
            self.assertEqual(mcd.read_acquisition(acquisition).ndim, 3)


if __name__ == "__main__":
    unittest.main()
