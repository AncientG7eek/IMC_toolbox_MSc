
from io import BytesIO
from pathlib import Path, PurePosixPath
import shutil
from zipfile import BadZipFile, ZipFile

from imc_curator.config import load_search_config


SEARCH_CONFIG = load_search_config()


def materialize_file(source: Path, destination: Path) -> Path:
    """Copy a file into the curated project structure."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def materialize_directory(source: Path, destination: Path) -> Path:
    """Copy a directory into the curated project structure."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return destination


def materialize_archive_member(
    archive: Path,
    member_path: str,
    destination: Path,
    archive_chain: list[str] | None = None,
) -> Path:
    """Extract one file from an outer ZIP or a nested ZIP."""
    archive_chain = archive_chain or []

    for path in [*archive_chain, member_path]:
        member = PurePosixPath(path)
        if member.is_absolute() or ".." in member.parts:
            raise ValueError(f"Unsafe archive member path: {path}")

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        if not archive_chain:
            # Extract directly from the outer ZIP.
            with ZipFile(archive, "r") as zip_file:
                with zip_file.open(member_path, "r") as source:
                    with destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
            return destination

        # Read the first nested ZIP from the outer archive.
        with ZipFile(archive, "r") as zip_file:
            with zip_file.open(archive_chain[0], "r") as source:
                current_bytes = source.read()

        # Descend through any additional nested ZIPs.
        for nested_member in archive_chain[1:]:
            with ZipFile(BytesIO(current_bytes), "r") as zip_file:
                with zip_file.open(nested_member, "r") as source:
                    current_bytes = source.read()

        # Extract the requested file from the innermost ZIP.
        with ZipFile(BytesIO(current_bytes), "r") as zip_file:
            with zip_file.open(member_path, "r") as source:
                with destination.open("wb") as target:
                    shutil.copyfileobj(source, target)

    except (OSError, KeyError, BadZipFile, RuntimeError) as exc:
        raise RuntimeError(
            f"Could not extract member {member_path!r} from "
            f"{archive} through nested archives {archive_chain}: {exc}"
        ) from exc

    return destination


def get_category_config(category: str) -> dict:
    return SEARCH_CONFIG["categories"][category]


def materialize_category(
    project_dir: Path,
    raw_dir: Path,
    category: str,
    entries: list[dict],
) -> None:
    """Materialize approved inputs into their configured category."""
    config = get_category_config(category)
    destination_dir = project_dir / config["destination"]

    # Create the category directory even when no files were selected.
    destination_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        if isinstance(entry, dict):
            relative_path = entry["path"]
            source_type = entry.get("source_type")
            archive_path = entry.get("archive_path")
            archive_chain = entry.get("archive_chain", [])
            member_path = entry.get("member_path")
        elif isinstance(entry, str):
            relative_path = entry
            source_type = None
            archive_path = None
            archive_chain = []
            member_path = None
        else:
            raise ValueError(f"Unsupported manifest entry: {entry!r}")

        # Handle regular and nested archive members.
        if source_type in {"archive_member", "nested_archive_member"} or "::" in relative_path:
            if archive_path is None or member_path is None:
                parts = relative_path.split("::")
                if len(parts) < 2:
                    raise ValueError(
                        f"Archive entry is missing archive metadata: {entry!r}"
                    )

                archive_path = parts[0]
                archive_chain = parts[1:-1]
                member_path = parts[-1]

            archive = raw_dir / archive_path

            if not archive.is_file():
                raise RuntimeError(f"ZIP archive does not exist: {archive}")

            target = destination_dir / PurePosixPath(member_path).name

            materialize_archive_member(
                archive=archive,
                member_path=member_path,
                destination=target,
                archive_chain=archive_chain,
            )
            continue

        # Handle ordinary filesystem inputs.
        source = raw_dir / relative_path

        if not source.exists():
            raise RuntimeError(f"Input does not exist: {source}")

        target = destination_dir / source.name

        if source.is_dir():
            materialize_directory(source, target)
        else:
            materialize_file(source, target)
