from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_FILE = (
    PROJECT_ROOT
    / "configs"
    / "imc_curator_config.toml"
)

SEARCH_CONFIG_FILE = (
    PROJECT_ROOT
    / "configs"
    / "imc_curator_search_config.toml"
)


def load_config() -> dict:
    """Load the main IMC Curator configuration."""

    if not CONFIG_FILE.exists():
        raise RuntimeError(
            f"Configuration file not found: {CONFIG_FILE}"
        )

    with CONFIG_FILE.open("rb") as f:
        return tomllib.load(f)


def load_search_config() -> dict:
    """Load file discovery and classification configuration."""

    if not SEARCH_CONFIG_FILE.exists():
        raise RuntimeError(
            f"Search configuration file not found: "
            f"{SEARCH_CONFIG_FILE}"
        )

    with SEARCH_CONFIG_FILE.open("rb") as f:
        return tomllib.load(f)


def get_projects_dir() -> Path:
    """Return the configured directory for cohort projects."""

    config = load_config()

    try:
        projects_dir = Path(config["projects_dir"])
    except KeyError:
        raise RuntimeError(
            f"'projects_dir' is missing from {CONFIG_FILE}"
        )

    if not projects_dir.is_absolute():
        projects_dir = PROJECT_ROOT / projects_dir

    projects_dir.mkdir(parents=True, exist_ok=True)

    return projects_dir

def get_archive_extensions() -> set[str]:
    """Return supported archive extensions."""

    config = load_search_config()

    try:
        extensions = config["archives"]["extensions"]
    except KeyError:
        raise RuntimeError(
            f"'archives.extensions' is missing from {SEARCH_CONFIG_FILE}"
        )

    return {
        extension.lower()
        for extension in extensions
    }