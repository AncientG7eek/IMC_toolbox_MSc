from pathlib import Path

from imc_curator.discovery.classifier import classify_file


def scan_directory(source_dir: Path) -> list[Path]:
    """Return all files in the source dataset."""

    return [
        path
        for path in source_dir.rglob("*")
        if path.is_file()
    ]


def discover(source_dir: Path) -> dict[str, list[str]]:
    """Scan and classify files in a source dataset."""

    files = scan_directory(source_dir)

    suggestions = {}

    for path in files:
        category = classify_file(path)

        if category is None:
            category = "unclassified"

        relative_path = path.relative_to(source_dir)

        suggestions.setdefault(category, [])
        suggestions[category].append(
            str(relative_path)
        )

    return suggestions