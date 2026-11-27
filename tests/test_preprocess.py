from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

from imc_curator.services.processing.preprocess import (
    PreprocessConfig,
    PreprocessOutputConfig,
    load_preprocess_config,
    preprocess_registered_images,
    preprocess_signature,
    write_default_preprocess_config,
)
from imc_curator.services.processing.preprocessing import (
    PreprocessingConfig,
)


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


def _write_config(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PreprocessConfigTests(unittest.TestCase):
    def test_default_config_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preprocessing.toml"
            write_default_preprocess_config(path)
            config = load_preprocess_config(path)

        self.assertEqual(config.preprocessing.preprocessing, "arcsinh")
        self.assertEqual(config.preprocessing.arcsinh_scale, 5.0)
        self.assertEqual(config.preprocessing.denoising, "butterworth")
        self.assertEqual(config.preprocessing.butterworth_cutoff, 0.2)
        self.assertEqual(config.output.directory, "preprocessed")
        self.assertEqual(config.output.compression, "zlib")

    def test_dataset_override_inherits_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preprocessing.toml"
            _write_config(
                path,
                """
[preprocessing]
method = "arcsinh"
arcsinh_scale = 5.0

[denoising]
method = "butterworth"
butterworth_cutoff = 0.2

[datasets.panelA.preprocessing]
arcsinh_scale = 3.0

[datasets.panelA.denoising]
method = "none"
""",
            )
            config = load_preprocess_config(path)

        panel_a = config.for_dataset("panela")
        panel_b = config.for_dataset("panelB")

        self.assertEqual(panel_a.arcsinh_scale, 3.0)
        self.assertEqual(panel_a.denoising, "none")
        self.assertEqual(panel_b.arcsinh_scale, 5.0)
        self.assertEqual(panel_b.denoising, "butterworth")

    def test_invalid_method_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preprocessing.toml"
            _write_config(
                path,
                """
[preprocessing]
method = "not-a-method"
""",
            )

            with self.assertRaises(ValueError):
                load_preprocess_config(path)

    def test_signature_describes_pipeline(self) -> None:
        config = PreprocessConfig(
            preprocessing=PreprocessingConfig(
                preprocessing="arcsinh",
                arcsinh_scale=5.0,
                denoising="butterworth",
                butterworth_cutoff=0.2,
            )
        )

        self.assertEqual(
            preprocess_signature(config),
            "arcsinh(scale=5)+butterworth(cutoff=0.2,high_pass=false)",
        )


class PreprocessExecutionTests(unittest.TestCase):
    def _build_project(self, root: Path) -> dict:
        curated = root / "curated"
        projects = root / "projects"
        selected = projects / "demo" / "data" / "raw" / "selected"
        selected.mkdir(parents=True)

        for name in ("a.tiff", "b.tiff"):
            tifffile.imwrite(
                selected / name,
                np.full((2, 8, 8), 5.0, dtype=np.float32),
                photometric="minisblack",
                planarconfig="separate",
            )

        _write_csv(
            curated / "global_marker_channels.csv",
            ["Marker Name", "panelA", "panelB"],
            [["CD3", "0", "0"], ["SMA", "1", "1"]],
        )
        _write_csv(
            curated / "global_register_of_images.csv",
            [
                "global_path",
                "relative_path",
                "shape",
                "panel_name",
                "cohort_name",
                "project_name",
            ],
            [
                [
                    "",
                    "demo/data/raw/selected/a.tiff",
                    "[2, 8, 8]",
                    "panelA",
                    "",
                    "demo",
                ],
                [
                    "",
                    "demo/data/raw/selected/b.tiff",
                    "[2, 8, 8]",
                    "panelB",
                    "",
                    "demo",
                ],
            ],
        )

        return {
            "workspace_dir": str(root),
            "projects_dir": str(projects),
            "curation": {
                "curated_database_dir": str(curated),
                "global_image_register_file": (
                    "global_register_of_images.csv"
                ),
                "global_marker_channels_file": (
                    "global_marker_channels.csv"
                ),
            },
        }

    def _preprocess_config(self) -> PreprocessConfig:
        return PreprocessConfig(
            preprocessing=PreprocessingConfig(
                preprocessing="arcsinh",
                arcsinh_scale=5.0,
                denoising="none",
            ),
            output=PreprocessOutputConfig(
                directory="preprocessed",
                register_file=(
                    "global_register_of_preprocessed_images.csv"
                ),
                compression="none",
            ),
            dataset_overrides={
                "panelB": PreprocessingConfig(
                    preprocessing="arcsinh",
                    arcsinh_scale=1.0,
                    denoising="none",
                )
            },
        )

    def test_preprocess_writes_images_and_register(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self._build_project(root)

            result = preprocess_registered_images(
                config,
                self._preprocess_config(),
            )

            output_a = (root / "curated" / "preprocessed" / "a.tiff")
            output_b = (root / "curated" / "preprocessed" / "b.tiff")
            self.assertTrue(output_a.is_file())
            self.assertTrue(output_b.is_file())
            self.assertEqual(result.processed, 2)
            self.assertEqual(result.skipped, 0)
            self.assertEqual(result.failed, 0)
            self.assertTrue(result.output_register.is_file())
            self.assertTrue(result.report_path.is_file())

            np.testing.assert_allclose(
                tifffile.imread(output_a),
                np.full((2, 8, 8), np.arcsinh(1.0), dtype=np.float32),
                rtol=1e-6,
            )
            np.testing.assert_allclose(
                tifffile.imread(output_b),
                np.full((2, 8, 8), np.arcsinh(5.0), dtype=np.float32),
                rtol=1e-6,
            )

            _, register = self._read_csv(result.output_register)
            self.assertEqual(
                {row["panel_name"] for row in register},
                {"panelA", "panelB"},
            )
            self.assertEqual(
                {row["status"] for row in register},
                {"processed"},
            )

    def test_existing_outputs_are_skipped_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self._build_project(root)
            preprocess_config = self._preprocess_config()

            first = preprocess_registered_images(
                config,
                preprocess_config,
            )
            second = preprocess_registered_images(
                config,
                preprocess_config,
            )
            forced = preprocess_registered_images(
                config,
                preprocess_config,
                force=True,
            )

        self.assertEqual(first.processed, 2)
        self.assertEqual(second.processed, 0)
        self.assertEqual(second.skipped, 2)
        self.assertEqual(forced.processed, 2)
        self.assertEqual(forced.skipped, 0)

    def test_dataset_filter_only_processes_requested_panel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self._build_project(root)

            result = preprocess_registered_images(
                config,
                self._preprocess_config(),
                datasets=["panelA"],
            )

            self.assertEqual(result.processed, 1)
            self.assertTrue(
                (root / "curated" / "preprocessed" / "a.tiff").is_file()
            )
            self.assertFalse(
                (root / "curated" / "preprocessed" / "b.tiff").exists()
            )

    def test_dataset_filter_preserves_other_register_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self._build_project(root)
            preprocess_config = self._preprocess_config()

            preprocess_registered_images(config, preprocess_config)
            filtered = preprocess_registered_images(
                config,
                preprocess_config,
                datasets=["panelA"],
                force=True,
            )

            _, register = self._read_csv(filtered.output_register)

        self.assertEqual(
            {row["panel_name"] for row in register},
            {"panelA", "panelB"},
        )
        self.assertEqual(len(register), 2)

    @staticmethod
    def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            return list(reader.fieldnames or []), list(reader)


if __name__ == "__main__":
    unittest.main()
