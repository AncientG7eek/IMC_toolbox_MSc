
from pathlib import Path
import tomllib
from ast import literal_eval

from imc_curator.config import load_config, get_manifests_dir

CONFIG = load_config()


def load_manifest(project_dir: Path, command: str) -> dict:
    """Load a project's manifest.toml."""

    manifests_dir = get_manifests_dir(
        project_dir=project_dir,
        config=CONFIG,
    )
    manifest_path = manifests_dir / command / "manifest.toml"

    if not manifest_path.exists():
        raise RuntimeError(
            f"Manifest not found: {manifest_path}"
        )

    with manifest_path.open("rb") as f:
        manifest = tomllib.load(f)

    manifest_parser = select_manifest_parser(command=command)

    parsed_manifest = manifest_parser(
        manifest=manifest, 
        manifest_path=manifest_path
    )

    return parsed_manifest


def select_manifest_parser(command: str):
    parsers={
        "inspect" : parse_inspect_manifest
    }
    try:
        return parsers[command]
    except KeyError:
        raise ValueError(
            f"The manifest parser selector got an unexpected command name: {command}"
        )
    


def parse_inspect_manifest(manifest, manifest_path) -> dict:

    if "inputs" not in manifest:
        raise ValueError(
            f"Missing [inputs] section in manifest: {manifest_path}"
        )
    inputs = manifest.get("inputs", {})

    if not isinstance(inputs, dict):
        raise ValueError(
            "The manifest's [inputs] section must be a table like:\n"
            "category = [\n"
            "   dict, \n"
            "   ...\n"
            "]\n"
        )

    for category, entries in inputs.items():
        if not isinstance(entries, list):
            raise ValueError(
                f"Inputs for {category!r} category must be a list.\n"
                f"Check the {manifest_path}"
            )

        parsed_entries = []

        for entry in entries:
            if isinstance(entry, str):
                try:
                    parsed = literal_eval(entry)
                except (ValueError, SyntaxError):
                    continue

                if isinstance(parsed, dict):
                    if not isinstance(parsed.get("path"), str):
                        raise ValueError(
                            f"Manifest entry in {category!r} must have a string 'path' field.\n"
                            f"The following entry is invalid:\n"
                            f"{entry!r}"
                        )
                    parsed_entries.append(parsed)
            elif isinstance(entry, dict):
                parsed_entries.append(entry)
            else:
                raise ValueError(
                    f"Invalid entry in category {category!r}: {entry!r}"
                )

        inputs[category] = parsed_entries

    return inputs