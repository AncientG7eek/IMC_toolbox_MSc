from pathlib import Path, PurePosixPath
import shutil
from zipfile import ZipFile

from imc_curator.config import load_search_config


SEARCH_CONFIG = load_search_config()


def materialize_file(
    source: Path,
    destination: Path,
) -> Path:
    """Copy a file into the curated project structure."""

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(source, destination)

    return destination


def materialize_directory(
    source: Path,
    destination: Path,
) -> Path:
    """Copy a directory into the curated project structure."""

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
    )

    return destination


def materialize_archive_member(
    archive: Path,
    member_path: str,
    destination: Path,
) -> Path:
    """Extract one file from a ZIP archive into the curated structure.

    The entire archive is not extracted.
    """

    member = PurePosixPath(member_path)

    if member.is_absolute() or ".." in member.parts:
        raise ValueError(
            f"Unsafe archive member path: {member_path}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with ZipFile(archive, "r") as zip_file:
            try:
                with zip_file.open(member_path, "r") as source:
                    with destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
            except KeyError as exc:
                raise RuntimeError(
                    f"Member {member_path!r} not found in archive "
                    f"{archive}"
                ) from exc

    except (OSError, Exception) as exc:
        # Re-raise with archive context; preserve the original cause.
        raise RuntimeError(
            f"Could not extract {member_path!r} from {archive}: {exc}"
        ) from exc

    return destination


def get_category_config(category: str) -> dict:
    return SEARCH_CONFIG["categories"][category]


def materialize_category(
    project_dir: Path,
    raw_dir: Path,
    category: str,
    entries: list[dict],
):
    config = SEARCH_CONFIG["categories"][category]
    destination_dir = project_dir / config["destination"]

    for entry in entries:
        # Support both string entries and structured manifest entries.
        if isinstance(entry, dict):
            relative_path = entry["path"]
            source_type = entry.get("source_type")
            archive_path = entry.get("archive_path")
            member_path = entry.get("member_path")


        # Support archive paths even when explicit metadata is absent.
        if source_type == "archive_member" or "::" in relative_path:
            if archive_path is None or member_path is None:
                if "::" not in relative_path:
                    raise ValueError(
                        f"Archive entry is missing archive_path or "
                        f"member_path: {entry!r}"
                    )

                archive_path, member_path = relative_path.split("::", 1)

            archive = raw_dir / archive_path

            if not archive.is_file():
                raise RuntimeError(
                    f"ZIP archive does not exist: {archive}"
                )

            member_name = PurePosixPath(member_path).name
            target = destination_dir / member_name

            materialize_archive_member(
                archive=archive,
                member_path=member_path,
                destination=target,
            )
            continue

        # Ordinary filesystem input.
        source = raw_dir / relative_path

        if not source.exists():
            raise RuntimeError(
                f"Input does not exist: {source}"
            )

        target = destination_dir / source.name

        if source.is_dir():
            materialize_directory(source, target)
        else:
            materialize_file(source, target)