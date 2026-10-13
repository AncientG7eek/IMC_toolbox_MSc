from pathlib import Path


def write_manifest(
    project_dir: Path,
    project_name: str,
    suggestions: dict[str, list[dict]],
) -> Path:
    """Write a human-editable manifest.toml."""

    manifest_path = project_dir / "manifest.toml"

    lines = [
        "# IMC Curator project manifest",
        "#",
        "# Review and edit the paths below before running curation.",
        "# Paths are relative to the project root.",
        "",
        "[project]",
        f'name = "{project_name}"',
        "",
        "[inputs]",
        "",
    ]

    categories = {
        "images": "Image data",
        "marker_metadata": "Marker/channel metadata",
        "clinical_data": "Clinical information",
        "sample_metadata": "Sample metadata",
    }

    for category, comment in categories.items():
        lines.append(f"# {comment}")

        paths = suggestions.get(category, [])

        lines.append(f"{category} = [")

        for path in paths:
            lines.append(f'    "{path}",')

        lines.append("]")
        lines.append("")

    # Files that the classifier could not assign.
    lines.append("# Files that could not be classified automatically")
    lines.append("unclassified = [")

    for path in suggestions.get("unclassified", []):
        lines.append(f'    "{path}",')

    lines.append("]")
    lines.append("")

    manifest_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return manifest_path