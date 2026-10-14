
from pathlib import Path
import ast
import tomllib

from imc_curator.config import load_config, get_manifests_dir

CONFIG = load_config()


def load_manifest(project_dir: Path) -> dict:
    """Load a project's manifest.toml."""

    manifests_dir = get_manifests_dir(
        project_dir=project_dir,
        config=CONFIG,
    )
    manifest_path = manifests_dir / "manifest.toml"

    if not manifest_path.exists():
        raise RuntimeError(
            f"Manifest not found: {manifest_path}"
        )

    with manifest_path.open("rb") as f:
        manifest = tomllib.load(f)

    inputs = manifest.get("inputs", {})

    for category, entries in inputs.items():
        normalized_entries = []

        for entry in entries:
            if isinstance(entry, str):
                try:
                    parsed = ast.literal_eval(entry)
                except (ValueError, SyntaxError):
                    # Preserve ordinary string paths.
                    normalized_entries.append(entry)
                    continue

                if isinstance(parsed, dict):
                    normalized_entries.append(parsed)
                else:
                    normalized_entries.append(entry)

            elif isinstance(entry, dict):
                normalized_entries.append(entry)

            else:
                raise ValueError(
                    f"Invalid entry in category {category!r}: {entry!r}"
                )

        inputs[category] = normalized_entries

    return manifest
