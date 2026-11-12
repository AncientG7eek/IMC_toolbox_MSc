"""Shared image-to-panel assignment TOML writer."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path


def _toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _toml_string_list(values: list[str]) -> str:
    if not values:
        return "[]"

    items = ",\n".join(
        f"    {_toml_string(value)}"
        for value in values
    )
    return f"[\n{items},\n]"


def load_assignments(path: Path) -> dict[str, list[str]]:
    if not path.is_file():
        return {}

    with path.open("rb") as file:
        data = tomllib.load(file)

    raw = data.get("images_by_marker", {})
    return {
        str(key): [str(value) for value in values]
        for key, values in raw.items()
    }


def append_assignments(
    path: Path,
    entries: dict[str, list[str]],
) -> Path:
    """Merge entries into the assignment file and rewrite it."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    assignments = load_assignments(path)
    for panel_file, image_paths in entries.items():
        existing = assignments.setdefault(str(panel_file), [])
        seen = set(existing)
        for image_path in image_paths:
            image_path = str(image_path)
            if image_path not in seen:
                existing.append(image_path)
                seen.add(image_path)

    lines = [
        "# IMC CURATION — IMAGE TO MARKER PANEL ASSIGNMENTS",
        "",
        "# Each key is a marker CSV filename.",
        "# Each value lists the images assigned to that marker panel.",
        "",
        "[images_by_marker]",
        "",
    ]
    for panel_file, image_paths in assignments.items():
        lines.append(
            f"{_toml_string(panel_file)} = "
            f"{_toml_string_list(image_paths)}"
        )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
