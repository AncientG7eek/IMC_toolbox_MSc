from __future__ import annotations

import unittest

from typer.testing import CliRunner

from imc_curator.cli import app


class CliCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_generate_command_is_visible(self) -> None:
        result = self.runner.invoke(app, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("generate", result.output)
        self.assertNotIn("generate-experiment", result.output)

    def test_generate_help_works(self) -> None:
        result = self.runner.invoke(app, ["generate", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--output", result.output)

    def test_legacy_generate_experiment_alias_works(self) -> None:
        result = self.runner.invoke(
            app,
            ["generate-experiment", "--help"],
        )

        self.assertEqual(result.exit_code, 0)

    def test_preprocess_command_is_visible(self) -> None:
        result = self.runner.invoke(app, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("preprocess", result.output)

    def test_preprocess_help_works(self) -> None:
        result = self.runner.invoke(app, ["preprocess", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--dataset", result.output)
        self.assertIn("--force", result.output)


if __name__ == "__main__":
    unittest.main()
