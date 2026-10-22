from pathlib import Path

from imc_curator.config import load_config, get_manifests_dir, load_search_config


CONFIG = load_config()


def write_manifest(
    project_dir: Path,
    project_name: str,
    suggestions: dict[str, list[dict]],
) -> Path:
    """Write a human-editable manifest.toml with all configured categories."""

    manifests_dir = get_manifests_dir(
        project_dir=project_dir,
        config=CONFIG,
    )
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

    # Include every configured category, even if no files were discovered.
    search_config = load_search_config()
    configured_categories = search_config["categories"]

    all_categories = list(configured_categories)

    # Also include categories present in the suggestions but absent from config,
    # such as image_or_clinical_data.
    for category in suggestions:
        if category != "unclassified" and category not in all_categories:
            all_categories.append(category)

    for category in all_categories:
        comment = " ".join(
            word.capitalize() for word in category.split("_")
        )
        lines.append(f"# {comment}")

        per_category_suggestions = suggestions.get(category, [])

        lines.append(f"{category} = [")

        for suggestion in per_category_suggestions:
            # Preserve the existing manifest entry representation.
            lines.append(f'    "{suggestion}",')

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
