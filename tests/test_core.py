from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

from imc_curator.services.curation.finalize.common import (
    ensure_csv,
    read_csv,
    write_csv,
)
from imc_curator.services.discovery.extract.panel_map import (
    append_panel_map_rows,
    init_panel_map,
    remap_tiff_files,
)
from imc_curator.services.discovery.extract.subset_tiffs import (
    _read_tiff_stack,
)
from imc_curator.services.discovery.signature import (
    build_panel_signature,
    format_panel_signature,
)


class SignatureTests(unittest.TestCase):
    def test_signature_is_marker_set_and_sorted(self) -> None:
        channels = [
            {
                "biological_marker": "CD3",
                "raw_name": "CD3(Nd143)",
                "raw_fluor": "Nd143",
            },
            {
                "biological_marker": "SMA",
                "raw_name": "SMA(In115)",
                "raw_fluor": "In115",
            },
        ]
        signature = build_panel_signature(channels)
        self.assertEqual(signature, ["cd3", "sma"])
        self.assertEqual(format_panel_signature(signature), "cd3; sma")


class PanelMapTests(unittest.TestCase):
    def test_init_append_and_remap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            map_path = init_panel_map(root / "map.csv")
            append_panel_map_rows(
                map_path,
                [
                    {
                        "tiff_file": "data/raw/unpacked/a.tiff",
                        "panel_id": "panel_a",
                        "panel_signature": "a",
                        "panel_file": "metadata/markers/selected/panel_a.csv",
                    }
                ],
            )
            remap_tiff_files(
                map_path,
                root / "data/raw/unpacked",
                root / "data/raw/selected",
                root,
            )
            headers, rows = read_csv(map_path)
            self.assertEqual(headers[0], "tiff_file")
            self.assertEqual(rows[0]["tiff_file"], "data/raw/selected/a.tiff")


class CsvIOTests(unittest.TestCase):
    def test_ensure_and_write_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "table.csv"
            ensure_csv(path, ["a", "b"])
            write_csv(path, ["a", "b"], [{"a": "1", "b": "2"}])
            headers, rows = read_csv(path)
            self.assertEqual(headers, ["a", "b"])
            self.assertEqual(rows, [{"a": "1", "b": "2"}])


class TiffStackTests(unittest.TestCase):
    def test_single_page_and_page_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            single = root / "single.tiff"
            tifffile.imwrite(
                single,
                np.zeros((3, 2, 2), dtype="uint16"),
                photometric="minisblack",
                planarconfig="separate",
            )
            self.assertEqual(_read_tiff_stack(single).shape, (3, 2, 2))

            stacked = root / "stacked.tiff"
            with tifffile.TiffWriter(stacked) as writer:
                for _ in range(4):
                    writer.write(np.zeros((2, 2), dtype="uint16"))
            self.assertEqual(_read_tiff_stack(stacked).shape, (4, 2, 2))


if __name__ == "__main__":
    unittest.main()
