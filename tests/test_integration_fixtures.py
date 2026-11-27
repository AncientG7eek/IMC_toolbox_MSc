from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from imc_curator.services.discovery.examine.submodules.extract_ome_channels import (
    extract_tiff_metadata,
)


FIXTURES = Path(__file__).parent / "fixtures"


class IntegrationFixtureTests(unittest.TestCase):
    def test_ome_metadata_fixture(self) -> None:
        candidates = list((FIXTURES / "ome").glob("*.ome.tiff"))
        if not candidates:
            self.skipTest("No OME fixture provided.")

        channels, scan = extract_tiff_metadata(
            candidates[0],
            candidates[0].parent,
        )
        self.assertEqual(scan["status"], "ok")
        self.assertGreater(len(channels), 0)

    def test_clinical_xlsx_fixture(self) -> None:
        candidates = list((FIXTURES / "clinical").glob("*.xlsx"))
        if not candidates:
            self.skipTest("No clinical XLSX fixture provided.")

        table = pd.read_excel(candidates[0], engine="openpyxl")
        self.assertGreater(len(table.columns), 0)


if __name__ == "__main__":
    unittest.main()
