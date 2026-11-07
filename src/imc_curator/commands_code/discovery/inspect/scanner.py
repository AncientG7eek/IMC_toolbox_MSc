
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile, is_zipfile
from dataclasses import dataclass
import logging
from rich.progress import (
    Progress, 
    SpinnerColumn, 
    TextColumn, 
    BarColumn,
    TaskProgressColumn,
)

from imc_curator.commands_code.discovery.inspect.classifier import classify_file
from imc_curator.config import load_search_config, get_search_limits
from imc_curator.logging_utils import get_action_logger


search_limits = get_search_limits()

@dataclass(frozen=True)
class ArchiveScanLimits:
    max_nested_zip_depth: int = search_limits["max_nested_zip_depth"]
    max_nested_archive_size: int = search_limits["max_nested_archive_size"]
    max_total_uncompressed_size: int = search_limits["max_total_uncompressed_size"]
    max_archive_members: int = search_limits["max_archive_members"]

@dataclass
class ArchiveScanState:
    members_seen: int = 0
    total_uncompressed_size: int = 0
    stopped: bool = False


def scan_directory(
        source_dir: Path,
        progress_callback=None,
) -> list[dict]:
    """Return files from a source directory, including ZIP contents."""

    limits = ArchiveScanLimits()
    state = ArchiveScanState()

    source_dir = source_dir.resolve()

    if not source_dir.is_dir():
        raise NotADirectoryError(
            f"Source dataset directory not found: {source_dir}"
        )

    discovered = []

    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue

        relative_path = path.relative_to(source_dir).as_posix()

        if path.suffix.lower() == ".zip":
            discovered.extend(
                scan_zip(
                    outer_archive_path=path,
                    archive_relative_path=relative_path,
                    progress_callback=progress_callback,
                    limits=limits,
                    state=state,
                )
            )
        else:
            discovered.append({
                "path": relative_path,
                "classification_path": path,
                "source_type": "filesystem",
                "outer_archive_path": None,
                "archive_chain": [],
                "member_path": None,
                "size_bytes": path.stat().st_size,
            })

            if progress_callback:
                progress_callback()

    return discovered


def read_in_chunks(stream, max_size: int) -> bytes:
    chunks = []
    total_size = 0

    while True:
        chunk = stream.read(1024 * 1024)  # 1 MiB

        if not chunk:
            break

        total_size += len(chunk)

        if total_size > max_size:
            raise ValueError("Nested ZIP exceeds size limit")

        chunks.append(chunk)

    return b"".join(chunks)


def scan_zip(
    outer_archive_path: Path,
    archive_relative_path: str,
    archive_chain: list[str] | None = None,
    archive_bytes: bytes | None = None,
    progress_callback = None,
    limits: ArchiveScanLimits | None = None,
    state: ArchiveScanState | None = None,
) -> list[dict]:
    """Recursively list files in a ZIP and any nested ZIPs."""

    if archive_chain is None:
        archive_chain = []

    if limits is None:
        limits = ArchiveScanLimits()

    if state is None:
        state = ArchiveScanState()


    logger = logging.getLogger(__name__)

    if len(archive_chain) >= limits.max_nested_zip_depth:
        logger.warning(
            "Maximum nested ZIP depth reached for %s",
            "::".join([archive_relative_path, *archive_chain]),
        )
        return []

    discovered = []
    current_archive = "::".join([archive_relative_path, *archive_chain])

    try:
        archive_context = (
            ZipFile(outer_archive_path)
            if archive_bytes is None
            else ZipFile(BytesIO(archive_bytes))
        )

        with archive_context as archive:
            for member in archive.infolist():
                if state.stopped:
                    break

                if member.is_dir():
                    continue

                member_path = member.filename
                member_name = PurePosixPath(member_path).name

                # Ignore macOS metadata and resource-fork files.
                if (
                    member_path.startswith("__MACOSX/")
                    or member_name == ".DS_Store"
                    or member_name.startswith("._")
                ):
                    continue

                # state update
                state.members_seen += 1
                if state.members_seen > limits.max_archive_members:
                    logger.warning(
                        "Maximum number of archive members reached (%d)",
                        limits.max_archive_members,
                    )
                    state.stopped = True
                    break


                member_suffix = PurePosixPath(member_path).suffix.lower()

                # Recursively inspect valid nested ZIP archives.
                if member_suffix == ".zip":
                    if member.file_size > limits.max_nested_archive_size:
                        logger.warning(
                            """
                            Skipping nested ZIP archive:\n 
                            %s\n
                            because it's uncompressed size:\n 
                            %d\n
                            exceeded the limit:\n
                            %d
                            """,
                            member.filename,
                            member.file_size,
                            limits.max_nested_archive_size 
                        )
                        continue

                    try:
                        with archive.open(member, "r") as stream:
                            nested_bytes = read_in_chunks(
                                stream,
                                limits.max_nested_archive_size,
                            )
                    except ValueError:
                        logger.warning(
                            "Skipping nested ZIP because it exceeds the size limit: %s",
                            member.filename,
                        )
                        continue

                    if not is_zipfile(BytesIO(nested_bytes)):
                        logger.warning(
                            "Skipping ZIP-named member that is not a valid ZIP: %s::%s",
                            current_archive,
                            member_path,
                        )
                        continue

                    discovered.extend(
                        scan_zip(
                            outer_archive_path=outer_archive_path,
                            archive_relative_path=archive_relative_path,
                            archive_chain=[*archive_chain, member_path],
                            archive_bytes=nested_bytes,
                            progress_callback=progress_callback,
                            limits=limits,
                            state=state,
                        )
                    )
                    continue

                full_path = "::".join([
                    archive_relative_path,
                    *archive_chain,
                    member_path,
                ])

                # check the memory limit
                if (state.total_uncompressed_size + member.file_size
                    > limits.max_total_uncompressed_size
                ):
                    logger.warning(
                        """
                        Maximum total uncompressed archive size reached.\n
                        Stopping archive scan
                        """
                    )
                    state.stopped = True
                    break
                state.total_uncompressed_size += member.file_size

                discovered.append({
                    "path": full_path,
                    "classification_path": PurePosixPath(member_path),
                    "source_type": (
                        "nested_archive_member"
                        if archive_chain
                        else "archive_member"
                    ),
                    "outer_archive_path": archive_relative_path,
                    "archive_chain": list(archive_chain),
                    "member_path": member_path,
                    "size_bytes": member.file_size,
                })

                if progress_callback:
                    progress_callback()

    except (BadZipFile, OSError) as exc:
        logger.warning(
            "Could not inspect ZIP archive %s: %s",
            current_archive,
            exc,
        )

    return discovered


def discover(
    source_dir: Path,
    project_dir: Path,
) -> dict[str, list[dict]]:
    """Scan and classify files in a source dataset."""

    config = load_search_config()
    logger = get_action_logger(
        project_dir=project_dir,
        action="file_classification",
    )


    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}")
    ) as progress:

        task = progress.add_task("Scanning repository...")
        file_count = 0

        def update_scan_progress():
            nonlocal file_count
            file_count += 1

            progress.update(
                task,
                description=(
                    f"Scanning repository... "
                    f"{file_count} files discovered."
                ),
            )

        files = scan_directory(
            source_dir,
            progress_callback=update_scan_progress,
        )

    
    suggestions: dict[str, list[dict]] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:  

        task = progress.add_task(
            "Classifying files...",
            total=len(files),
        )

        for file in files:
            classification_result = classify_file(
                file["classification_path"],
                config=config,
                logger=logger,
            )

            category = classification_result.category

            suggestion = {
                "path": file["path"],
                "source_type": file["source_type"],
                "outer_archive_path": file["outer_archive_path"],
                "archive_chain": file["archive_chain"],
                "member_path": file["member_path"],
                "size_bytes": file["size_bytes"],
                "suggested_category": category,
                "score": classification_result.score,
                "evidence": classification_result.evidence,
            }

            suggestions.setdefault(category, []).append(suggestion)

            progress.advance(task)

    for category_files in suggestions.values():
        category_files.sort(
            key=lambda item: (
                -item["score"],
                item["path"].casefold(),
            )
        )

    logger.info(
        "Discovered %d files across %d categories in %s",
        len(files),
        len(suggestions),
        source_dir,
    )

    preferred_order = [
        "images",
        "raw_imc_data",
        "marker_metadata",
        "clinical_data",
    ]

    ordered_suggestions = {}

    for category in preferred_order:
        if category in suggestions:
            ordered_suggestions[category] = suggestions[category]

    for category in suggestions:
        if category not in preferred_order and category != "unclassified":
            ordered_suggestions[category] = suggestions[category]

    if "unclassified" in suggestions:
        ordered_suggestions["unclassified"] = suggestions["unclassified"]

    return ordered_suggestions
