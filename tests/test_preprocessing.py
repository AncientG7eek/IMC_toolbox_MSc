from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import tifffile
import yaml
from skimage.filters import butterworth

from imc_curator.services.adapt import immuvis
from imc_curator.services.processing.clip_limits import (
    ClipLimitConfig,
    build_dataset_image_map,
    compute_clip_limit,
)
from imc_curator.services.processing.preprocessing import (
    PreprocessingConfig,
    apply_preprocessing,
)


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


class PreprocessingTests(unittest.TestCase):
    def test_arcsinh_matches_immuvis_default(self) -> None:
        image = np.array([[0.0, 5.0], [10.0, 20.0]], dtype=np.float32)
        config = PreprocessingConfig(
            preprocessing="arcsinh",
            arcsinh_scale=5.0,
            denoising="none",
        )

        result = apply_preprocessing(image, config)

        np.testing.assert_allclose(
            result[0],
            np.arcsinh(image / 5.0),
        )

    def test_log1p_matches_immuvis_option(self) -> None:
        image = np.array([[0.0, 1.0], [5.0, 10.0]], dtype=np.float32)
        config = PreprocessingConfig(
            preprocessing="log1p",
            denoising="none",
        )

        result = apply_preprocessing(image, config)

        np.testing.assert_allclose(result[0], np.log1p(image))

    def test_2d_input_becomes_single_channel(self) -> None:
        image = np.ones((4, 4), dtype=np.float32)
        config = PreprocessingConfig(
            preprocessing="none",
            denoising="none",
        )

        result = apply_preprocessing(image, config)

        self.assertEqual(result.shape, (1, 4, 4))

    def test_butterworth_matches_skimage_per_channel(self) -> None:
        rng = np.random.default_rng(0)
        image = rng.random((2, 16, 16), dtype=np.float32)
        config = PreprocessingConfig(
            preprocessing="none",
            denoising="butterworth",
            butterworth_cutoff=0.2,
            butterworth_high_pass=False,
        )

        result = apply_preprocessing(image, config)
        expected = np.stack(
            [
                butterworth(
                    channel,
                    cutoff_frequency_ratio=0.2,
                    high_pass=False,
                )
                for channel in image
            ]
        )

        np.testing.assert_allclose(result, expected, rtol=1e-5, atol=1e-5)


class ClipLimitTests(unittest.TestCase):
    def _config(self) -> ClipLimitConfig:
        return ClipLimitConfig(
            percentile=99.0,
            max_images_per_dataset=8,
            max_pixels_per_image=100_000,
            max_total_pixels=100_000,
            decimals=6,
            fallback=5.0,
            preprocessing=PreprocessingConfig(
                preprocessing="arcsinh",
                arcsinh_scale=5.0,
                denoising="none",
            ),
        )

    def test_constant_image_limit_is_arcsinh_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.tiff"
            tifffile.imwrite(
                path,
                np.full((2, 8, 8), 5.0, dtype=np.float32),
                photometric="minisblack",
                planarconfig="separate",
            )

            limit = compute_clip_limit([path], self._config())

        self.assertAlmostEqual(limit, float(np.arcsinh(1.0)), places=5)

    def test_missing_images_use_fallback(self) -> None:
        self.assertEqual(
            compute_clip_limit([], self._config()),
            5.0,
        )

    def test_dataset_image_map_uses_register(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = (
                root
                / "projects"
                / "demo"
                / "data"
                / "raw"
                / "selected"
                / "image.tiff"
            )
            image_path.parent.mkdir(parents=True)
            tifffile.imwrite(image_path, np.ones((1, 4, 4), dtype="uint16"))

            register = (
                root
                / "curated"
                / "global_register_of_images.csv"
            )
            _write_csv(
                register,
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
                        "demo/data/raw/selected/image.tiff",
                        "[1, 4, 4]",
                        "panelA",
                        "",
                        "demo",
                    ]
                ],
            )

            config = {
                "workspace_dir": str(root),
                "projects_dir": str(root / "projects"),
                "curation": {
                    "curated_database_dir": str(root / "curated"),
                    "global_image_register_file": (
                        "global_register_of_images.csv"
                    ),
                },
            }

            images, diagnostics = build_dataset_image_map(
                config,
                ["panela"],
            )

        self.assertEqual(len(images["panela"]), 1)
        self.assertEqual(diagnostics, {})


class AdaptImmuvisTests(unittest.TestCase):
    def _build_adapt_project(
        self,
        root: Path,
    ) -> tuple[Path, Path, ClipLimitConfig]:
        curated = root / "curated"
        projects = root / "projects"
        curated.mkdir()

        _write_csv(
            curated / "global_marker_names.csv",
            ["Marker Name", "Comment", "Aliases"],
            [["CD3", "", "CD3"], ["SMA", "", "SMA"]],
        )
        _write_csv(
            curated / "global_marker_channels.csv",
            ["Marker Name", "panelA", "panelB"],
            [["CD3", "0", "0"], ["SMA", "1", ""]],
        )

        image_path = (
            projects
            / "demo"
            / "data"
            / "raw"
            / "selected"
            / "image.tiff"
        )
        image_path.parent.mkdir(parents=True)
        tifffile.imwrite(
            image_path,
            np.full((2, 8, 8), 5.0, dtype=np.float32),
            photometric="minisblack",
            planarconfig="separate",
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
                    "demo/data/raw/selected/image.tiff",
                    "[2, 8, 8]",
                    "panelA",
                    "",
                    "demo",
                ]
            ],
        )

        clip_config = ClipLimitConfig(
            percentile=99.0,
            max_images_per_dataset=8,
            max_pixels_per_image=100_000,
            max_total_pixels=100_000,
            decimals=6,
            fallback=5.0,
            preprocessing=PreprocessingConfig(
                preprocessing="arcsinh",
                arcsinh_scale=5.0,
                denoising="none",
            ),
        )
        return curated, projects, clip_config

    def _run_adapt(
        self,
        root: Path,
        curated: Path,
        projects: Path,
        clip_config: ClipLimitConfig,
    ) -> tuple[str, dict]:
        with mock.patch.dict(
            os.environ,
            {
                "IMC_CURATOR_WORKSPACE": str(root),
                "IMC_CURATOR_PROJECTS_DIR": str(projects),
                "IMC_CURATOR_CURATED_DATABASE_DIR": str(curated),
            },
        ), mock.patch.object(
            immuvis,
            "CLIP_LIMIT_CONFIG",
            clip_config,
        ):
            report = immuvis.adapt_immuvis()

        panel_config = yaml.safe_load(
            (root / "all_panels_config.yaml").read_text(
                encoding="utf-8"
            )
        )
        return report, panel_config

    def test_clip_limit_method_uses_computed_value(self) -> None:
        config = immuvis.ImmuvisConfig({"panelA": 2.5})

        self.assertEqual(config.clip_limit("panelA"), 2.5)
        self.assertEqual(config.clip_limit("panelB"), 5.0)

    def test_adapt_computes_clip_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            curated, projects, clip_config = self._build_adapt_project(
                root
            )
            report, panel_config = self._run_adapt(
                root,
                curated,
                projects,
                clip_config,
            )

        self.assertAlmostEqual(
            panel_config["clip_limits"]["panelA"],
            float(np.arcsinh(1.0)),
            places=5,
        )
        self.assertEqual(panel_config["clip_limits"]["panelB"], 5.0)
        self.assertEqual(panel_config["markers"]["panelA"], ["CD3", "SMA"])
        self.assertIn("Clip limits:", report)
        self.assertIn("panelA", report)
        self.assertIn("fallback", report)

    def test_adapt_uses_preprocessing_config_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            curated, projects, clip_config = self._build_adapt_project(
                root
            )
            (curated / "preprocessing.toml").write_text(
                """
[preprocessing]
method = "arcsinh"
arcsinh_scale = 5.0

[denoising]
method = "none"

[datasets.panelA.preprocessing]
arcsinh_scale = 1.0
""",
                encoding="utf-8",
            )

            report, panel_config = self._run_adapt(
                root,
                curated,
                projects,
                clip_config,
            )

        self.assertAlmostEqual(
            panel_config["clip_limits"]["panelA"],
            float(np.arcsinh(5.0)),
            places=5,
        )
        self.assertIn("arcsinh(scale=1)", report)


if __name__ == "__main__":
    unittest.main()
