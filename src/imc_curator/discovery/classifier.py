from pathlib import Path
import tomllib

from imc_curator.config import load_search_config


SEARCH_CONFIG = load_search_config()


def classify_file(path: Path) -> str | None:
    """Classify a file using the configured categories."""

    name = path.name.lower()
    suffix = path.suffix.lower()

    categories = SEARCH_CONFIG.get("categories", {})

    for category, rules in categories.items():

        extensions = {
            extension.lower()
            for extension in rules.get("extensions", [])
        }

        keywords = [
            keyword.lower()
            for keyword in rules.get("keywords", [])
        ]

        if extensions and suffix not in extensions:
            continue

        if keywords and not any(
            keyword in name
            for keyword in keywords
        ):
            continue

        return category

    return None