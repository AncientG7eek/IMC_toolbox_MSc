from pathlib import Path

from imc_curator.config import load_config, get_manifests_dir
                                

CONFIG = load_config()


def write_manifest(
    project_dir: Path,
    project_name: str,
    suggestions: dict[str, list[dict]],
) -> Path:
    """Write a human-editable manifest.toml."""

    manifests_dir = get_manifests_dir(project_dir=project_dir, config=CONFIG)
    manifest_path = manifests_dir / "manifest.toml"

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
        category : ' '.join(word.capitalize() for word in category.split('_'))
        for category in suggestions.keys()
        if category != "unclassified"
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

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return manifest_path