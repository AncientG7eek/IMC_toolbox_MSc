import os
from pathlib import Path
import tomllib
import warnings


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
PACKAGED_CONFIG_DIR = PACKAGE_DIR / "_defaults" / "configs"

CURATED_DATABASE_DIR_KEY = "curated_database_dir"
LEGACY_DATABASE_DIR_KEY = "global_files_dir"

_WARNED: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    """Emit a deprecation warning a single time per process."""
    if key in _WARNED:
        return
    _WARNED.add(key)
    warnings.warn(message, DeprecationWarning, stacklevel=3)


def _config_dir() -> Path:
    """Return the directory containing the active configuration files.

    Resolution order:

    1. ``IMC_CURATOR_CONFIG_DIR`` environment variable.
    2. The repository ``configs/`` directory (source/editable installs).
    3. The portable defaults shipped inside the installed package.
    """
    override = os.environ.get("IMC_CURATOR_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()

    repository_configs = PROJECT_ROOT / "configs"
    if (repository_configs / "imc_curator_config.toml").is_file():
        return repository_configs

    return PACKAGED_CONFIG_DIR


CONFIG_DIR = _config_dir()

CONFIG_FILE = CONFIG_DIR / "imc_curator_config.toml"

SEARCH_CONFIG_FILE = CONFIG_DIR / "imc_curator_search_config.toml"

OME_PARSER_CONFIG_FILE = CONFIG_DIR / "imc_curator_ome_parser_config.toml"



def load_config() -> dict:
    """Load the main IMC Curator configuration."""

    if not CONFIG_FILE.exists():
        raise RuntimeError(
            f"Configuration file not found: {CONFIG_FILE}"
        )

    with CONFIG_FILE.open("rb") as f:
        config = tomllib.load(f)

    config = _apply_env_overrides(config)
    return _normalise_curation_config(config)


def _apply_env_overrides(config: dict) -> dict:
    """Allow tests and deployments to redirect hard-coded paths.

    Environment variables take precedence over the values in
    ``imc_curator_config.toml``. This keeps the config file as the
    single source of truth for normal use while letting automated
    tests run against temporary directories.
    """
    projects_dir = os.environ.get("IMC_CURATOR_PROJECTS_DIR")
    if projects_dir:
        config["projects_dir"] = projects_dir

    curated_database_dir = os.environ.get(
        "IMC_CURATOR_CURATED_DATABASE_DIR"
    )
    if not curated_database_dir:
        curated_database_dir = os.environ.get(
            "IMC_CURATOR_GLOBAL_FILES_DIR"
        )
        if curated_database_dir:
            _warn_once(
                "env:IMC_CURATOR_GLOBAL_FILES_DIR",
                "IMC_CURATOR_GLOBAL_FILES_DIR is deprecated; use "
                "IMC_CURATOR_CURATED_DATABASE_DIR instead.",
            )
    if curated_database_dir:
        config.setdefault("curation", {})[
            CURATED_DATABASE_DIR_KEY
        ] = curated_database_dir

    workspace_dir = os.environ.get("IMC_CURATOR_WORKSPACE")
    if workspace_dir:
        config["workspace_dir"] = workspace_dir

    return config


def _normalise_curation_config(config: dict) -> dict:
    """Map the legacy ``global_files_dir`` key to its new name."""
    curation = config.setdefault("curation", {})

    if (
        CURATED_DATABASE_DIR_KEY not in curation
        and LEGACY_DATABASE_DIR_KEY in curation
    ):
        curation[CURATED_DATABASE_DIR_KEY] = curation[
            LEGACY_DATABASE_DIR_KEY
        ]
        _warn_once(
            "config:global_files_dir",
            "The [curation] global_files_dir setting is deprecated; "
            "rename it to curated_database_dir.",
        )

    return config


def get_workspace_dir(config: dict) -> Path:
    """Return the directory against which relative paths are resolved.

    The repository configuration keeps its historical behaviour and uses
    the repository root. A pip-installed package defaults to the current
    working directory, so running ``imc-curator`` in a folder keeps that
    folder self-contained.
    """
    value = config.get("workspace_dir") or PROJECT_ROOT
    workspace = Path(str(value)).expanduser()

    if not workspace.is_absolute():
        workspace = Path.cwd() / workspace

    return workspace.resolve()


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


def get_curated_database_dir(config: dict) -> Path:
    """Return the configured curated database directory.

    New configurations use ``[curation] curated_database_dir``. The
    legacy ``global_files_dir`` key and a legacy sibling ``global_files``
    folder are still accepted so existing workspaces keep working.
    """
    curation = config.get("curation", {})
    configured = curation.get(CURATED_DATABASE_DIR_KEY)

    if configured is None:
        configured = curation.get(LEGACY_DATABASE_DIR_KEY)

    if configured is None:
        raise RuntimeError(
            "Missing 'curated_database_dir' in the [curation] section "
            f"of {CONFIG_FILE}"
        )

    base = Path(str(configured)).expanduser()
    if not base.is_absolute():
        base = get_workspace_dir(config) / base

    if not base.exists() and base.name == "curated_database":
        legacy = base.parent / "global_files"
        if legacy.is_dir():
            _warn_once(
                "folder:global_files",
                "Using the legacy 'global_files' folder because "
                "'curated_database' does not exist yet. Rename the "
                "folder when convenient.",
            )
            return legacy

    return base


def get_curated_file_path(config: dict, key: str) -> Path:
    """Return the full path to a configured curated database file."""
    return get_curated_database_dir(config) / config["curation"][key]


def get_curated_subdir(config: dict, key: str) -> Path:
    """Return the full path to a curated database subdirectory."""
    return get_curated_database_dir(config) / config["curation"][key]


def get_global_files_dir(config: dict) -> Path:
    """Deprecated alias for :func:`get_curated_database_dir`."""
    _warn_once(
        "function:get_global_files_dir",
        "get_global_files_dir() is deprecated; use "
        "get_curated_database_dir().",
    )
    return get_curated_database_dir(config)


def get_global_file_path(config: dict, key: str) -> Path:
    """Deprecated alias for :func:`get_curated_file_path`."""
    _warn_once(
        "function:get_global_file_path",
        "get_global_file_path() is deprecated; use "
        "get_curated_file_path().",
    )
    return get_curated_file_path(config, key)


def get_global_subdir(config: dict, key: str) -> Path:
    """Deprecated alias for :func:`get_curated_subdir`."""
    _warn_once(
        "function:get_global_subdir",
        "get_global_subdir() is deprecated; use get_curated_subdir().",
    )
    return get_curated_subdir(config, key)


def resolve_projects_dir(config: dict) -> Path:
    """Resolve the projects directory from an in-memory configuration."""
    try:
        projects_dir = Path(
            str(config["projects_dir"])
        ).expanduser()
    except KeyError:
        raise RuntimeError(
            f"'projects_dir' is missing from {CONFIG_FILE}"
        )

    if not projects_dir.is_absolute():
        projects_dir = get_workspace_dir(config) / projects_dir

    return projects_dir


def get_projects_dir() -> Path:
    """Return the configured directory for cohort projects."""

    config = load_config()
    projects_dir = resolve_projects_dir(config)
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

def get_unpacked_images_dir(project_dir: Path, config: dict) -> Path:
    return project_dir / config["project_file_system"]["unpacked_images_dir"]

def get_raw_source_dir(project_dir: Path, config: dict) -> Path:
    return project_dir / config["project_file_system"]["raw_source_dir"]

def get_selected_images_dir(project_dir: Path, config: dict) -> Path:
    return project_dir / config["project_file_system"]["selected_images_dir"]

def get_selected_clinical_dir(project_dir: Path, config: dict) -> Path:
    return project_dir / config["project_file_system"]["selected_clinical_dir"]

def get_panels_dir(project_dir: Path, config: dict) -> Path:
    return project_dir / config["project_file_system"]["panels_dir"]
