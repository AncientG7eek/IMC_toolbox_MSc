
from __future__ import annotations

import ast
import tomllib
from collections import Counter
from itertools import cycle
from pathlib import Path, PurePosixPath

from rich.console import Console
from rich.text import Text
from rich.tree import Tree

from imc_curator.config import load_search_config


CATEGORY_PALETTE = [
    "bright_cyan",
    "bright_green",
    "bright_magenta",
    "bright_yellow",
    "bright_blue",
    "bright_red",
    "cyan",
    "green",
    "magenta",
    "yellow",
    "blue",
    "red",
    "turquoise2",
    "spring_green3",
    "deep_pink3",
    "orange3",
    "dodger_blue2",
    "medium_purple",
    "chartreuse3",
    "gold3",
]


def assign_category_styles(categories: list[str]) -> dict[str, str]:
    """Assign deterministic colors to category names."""
    ordered_categories = sorted(set(categories))

    return {
        category: color
        for category, color in zip(
            ordered_categories,
            cycle(CATEGORY_PALETTE),
        )
    }


def parse_manifest_entry(entry: str | dict) -> dict:
    """Support both dictionary entries and legacy stringified dictionaries."""
    if isinstance(entry, dict):
        return entry

    if isinstance(entry, str):
        parsed = ast.literal_eval(entry)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError(f"Invalid manifest entry: {entry!r}")


def get_path_parts(path_string: str) -> tuple[str, ...]:
    """Split a path into components, including ZIP archive members."""
    if "::" in path_string:
        archive_path, member_path = path_string.split("::", 1)

        return (
            *PurePosixPath(archive_path).parts,
            *PurePosixPath(member_path).parts,
        )

    return PurePosixPath(path_string).parts


def build_manifest_tree(
    manifest_path: Path,
    category_styles: dict[str, str],
) -> Tree:
    """Build a collapsed tree grouped by directory and category."""
    with manifest_path.open("rb") as file:
        manifest = tomllib.load(file)

    project_name = manifest.get(
        "project", {}
    ).get("name", manifest_path.parent.name)

    root = Tree(f"[bold]{project_name}/[/bold]")

    # Count files by their containing directory and category.
    counts: Counter[tuple[tuple[str, ...], str]] = Counter()

    for category, entries in manifest.get("inputs", {}).items():
        for entry in entries:
            item = parse_manifest_entry(entry)
            path_string = item.get("path")

            if not path_string:
                continue

            parts = get_path_parts(path_string)
            if not parts:
                continue

            directory = parts[:-1]
            counts[(directory, category)] += 1

    # Create each directory only once.
    directory_nodes: dict[tuple[str, ...], Tree] = {
        (): root
    }

    directories = {
        directory
        for directory, _category in counts
    }

    for directory in sorted(
        directories,
        key=lambda parts: (len(parts), parts),
    ):
        for depth in range(1, len(directory) + 1):
            prefix = directory[:depth]

            if prefix in directory_nodes:
                continue

            parent = directory_nodes[prefix[:-1]]
            directory_nodes[prefix] = parent.add(prefix[-1])

    # Add category/count leaves beneath the appropriate directories.
    for (directory, category), count in sorted(counts.items()):
        label = Text()
        label.append(
            category,
            style=category_styles.get(category, "white"),
        )
        label.append(f" [{count}]", style="dim")

        directory_nodes[directory].add(label)

    return root


def save_manifest_tree(
    manifest_path: Path,
    project_dir: Path,
    *,
    output_name: str = "manifest_tree.html",
) -> Path:
    """Build and save the color-coded manifest tree as HTML."""
    search_config = load_search_config()
    categories = list(search_config.get("categories", {}).keys())
    category_styles = assign_category_styles(categories)

    tree = build_manifest_tree(
        manifest_path=manifest_path,
        category_styles=category_styles,
    )

    output_dir = project_dir / "curation_process_manifests"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / output_name

    console = Console(
        record=True,
        width=120,
        color_system="truecolor",
    )
    console.print(tree)
    console.save_html(
        str(output_path),
        inline_styles=True,
    )

    return output_path
