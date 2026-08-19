from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "configs" / "imc_curator_config.toml"


def get_projects_dir() -> Path:
    """Return the configured directory for cohort projects."""

    if not CONFIG_FILE.exists():
        raise RuntimeError(
            f"Configuration file not found: {CONFIG_FILE}"
        )

    with CONFIG_FILE.open("rb") as f:
        config = tomllib.load(f)
    

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