from __future__ import annotations

import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from imc_curator.config import (
    PACKAGED_CONFIG_DIR,
    _apply_env_overrides,
    _normalise_curation_config,
    get_curated_database_dir,
    get_global_files_dir,
    get_workspace_dir,
)


class PackagedConfigTests(unittest.TestCase):
    def test_packaged_defaults_are_valid_and_complete(self) -> None:
        required_files = {
            "imc_curator_config.toml",
            "imc_curator_search_config.toml",
            "imc_curator_ome_parser_config.toml",
        }
        present = {
            path.name
            for path in PACKAGED_CONFIG_DIR.iterdir()
            if path.is_file()
        }
        self.assertTrue(required_files.issubset(present))

        config = tomllib.loads(
            (
                PACKAGED_CONFIG_DIR / "imc_curator_config.toml"
            ).read_text(encoding="utf-8")
        )
        for key in (
            "workspace_dir",
            "projects_dir",
            "project_file_system",
            "curation",
            "logging",
        ):
            self.assertIn(key, config)

        search = tomllib.loads(
            (
                PACKAGED_CONFIG_DIR
                / "imc_curator_search_config.toml"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("categories", search)
        self.assertIn("limits", search)

        parser = tomllib.loads(
            (
                PACKAGED_CONFIG_DIR
                / "imc_curator_ome_parser_config.toml"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(parser["rules"])

    def test_workspace_paths_are_relative_to_cwd(self) -> None:
        config = {
            "workspace_dir": ".",
            "curation": {"curated_database_dir": "curated_database"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            previous = Path.cwd()
            os.chdir(tmp)
            try:
                self.assertEqual(
                    get_workspace_dir(config),
                    Path(tmp).resolve(),
                )
                self.assertEqual(
                    get_curated_database_dir(config),
                    Path(tmp).resolve() / "curated_database",
                )
            finally:
                os.chdir(previous)

    def test_environment_overrides(self) -> None:
        config = {
            "workspace_dir": ".",
            "projects_dir": "projects",
            "curation": {"curated_database_dir": "curated_database"},
        }

        with mock.patch.dict(
            os.environ,
            {
                "IMC_CURATOR_WORKSPACE": "/tmp/workspace",
                "IMC_CURATOR_PROJECTS_DIR": "/tmp/projects",
                "IMC_CURATOR_CURATED_DATABASE_DIR": "/tmp/curated",
            },
        ):
            updated = _apply_env_overrides(config)

        self.assertEqual(updated["workspace_dir"], "/tmp/workspace")
        self.assertEqual(updated["projects_dir"], "/tmp/projects")
        self.assertEqual(
            updated["curation"]["curated_database_dir"],
            "/tmp/curated",
        )

    def test_legacy_env_var_is_supported(self) -> None:
        config = {"curation": {}}

        with mock.patch.dict(
            os.environ,
            {"IMC_CURATOR_GLOBAL_FILES_DIR": "/tmp/legacy"},
            clear=False,
        ):
            os.environ.pop("IMC_CURATOR_CURATED_DATABASE_DIR", None)
            updated = _apply_env_overrides(config)

        self.assertEqual(
            updated["curation"]["curated_database_dir"],
            "/tmp/legacy",
        )

    def test_legacy_config_key_is_normalised(self) -> None:
        config = {
            "curation": {"global_files_dir": "/tmp/legacy"},
        }

        normalised = _normalise_curation_config(config)

        self.assertEqual(
            normalised["curation"]["curated_database_dir"],
            "/tmp/legacy",
        )

    def test_legacy_folder_is_detected(self) -> None:
        config = {
            "workspace_dir": ".",
            "curation": {"curated_database_dir": "curated_database"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "global_files"
            legacy.mkdir()
            previous = Path.cwd()
            os.chdir(tmp)
            try:
                self.assertEqual(
                    get_curated_database_dir(config),
                    legacy.resolve(),
                )
            finally:
                os.chdir(previous)

    def test_deprecated_function_alias(self) -> None:
        config = {
            "workspace_dir": ".",
            "curation": {"curated_database_dir": "curated_database"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            previous = Path.cwd()
            os.chdir(tmp)
            try:
                self.assertEqual(
                    get_global_files_dir(config),
                    get_curated_database_dir(config),
                )
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
