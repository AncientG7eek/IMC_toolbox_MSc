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

OME_PARSER_CONFIG_FILE = (
    PROJECT_ROOT
    / "configs"
    / "imc_curator_ome_parser_config.toml"
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

def get_category_config(category: str) -> dict:
    search_config = load_search_config()
    return search_config["categories"][category]
    

def load_ome_parser_config() -> dict:
    """Load ome parsing rules."""

    if not OME_PARSER_CONFIG_FILE.exists():
        raise RuntimeError(
            f"OME parsing rules configuration file not found: "
            f"{OME_PARSER_CONFIG_FILE}"
        )

    with OME_PARSER_CONFIG_FILE.open("rb") as f:
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

def get_search_limits() -> dict[str, int]:
    """Return memory limits for repository search."""

    required_keys = {
        "max_nested_zip_depth",
        "max_nested_archive_size", 
        "max_total_uncompressed_size", 
        "max_archive_members",
    }
    size_keys = {
        "max_nested_archive_size", 
        "max_total_uncompressed_size", 
    }
    
    config = load_search_config()

    limits = config["limits"]
    if not isinstance(limits, dict):
        raise RuntimeError(
            f"Missing or invalid [limits] section in {SEARCH_CONFIG_FILE}"
        )

    missing_keys = required_keys - limits.keys()

    if missing_keys:
        raise RuntimeError(
            f"The [limits] section in {SEARCH_CONFIG_FILE} "
            f"is missing the following fields:\n"
            f"{', '.join(sorted(missing_keys))}."
        )

    unexpected_keys = limits.keys() - required_keys

    if unexpected_keys:
        raise RuntimeWarning(
            f"The [limits] section in {SEARCH_CONFIG_FILE} "
            f"contains the following unexpected fields:\n"
            f"{', '.join(sorted(missing_keys))}.\n"
            f"They won't be used in the program."
        )

    validated_limits = {}

    for key in required_keys:
        value = limits[key]

        try:
            validated_value = int(value)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid value for {key} in [limits] section of {SEARCH_CONFIG_FILE}:\n"
                f"{value}"
                f"Integer is expected"
            ) from exc

        if validated_value < 0:
            raise RuntimeError(
                f"Search limit {key} cannot be negative: {validated_value} was given.\n"
                f"Please, correct this in the [limits] section of {SEARCH_CONFIG_FILE}"
            )

        if key in size_keys:
            validated_value *= 1024**3

        validated_limits[key] = validated_value

    return validated_limits


def get_manifests_dir(project_dir: Path, config: dict) -> Path:
    return project_dir / config["curation"]["curation_manifests_subdir"]

# def get_manifest_paths(project_dir: Path, command: str) -> list[Path]:

#     config = load_config()
#     manifests_dir = get_manifests_dir(project_dir=project_dir, config=config)

#     try:
#         manifest_section = config["manifests"]
#     except KeyError:
#         raise ValueError(
#             "The imc_curator_config.toml has to contain the 'manifests' section."
#         )
    
#     try:
#         manifest_names = manifest_section[command]
#     except KeyError:
#         raise ValueError(
#             f"The imc_curator_config.toml has to contain "
#             f"the {command} field in the 'manifests' section."
#         )

#     manifest_paths = [
#         manifests_dir / manifest_name 
#         for manifest_name in config["manifests"][command]
#     ]

#     return manifest_paths

def get_logs_dir(project_dir: Path, config: dict) -> Path:
    return project_dir / config["logging"]["logs_subdir"]

def get_processed_images_dir(project_dir: Path, config: dict) -> Path:
    return project_dir / config["project_file_system"]["processed_images_dir"]

