
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile, is_zipfile
import logging

from imc_curator.commands_code.discovery.classifier import classify_file
from imc_curator.config import load_search_config
from imc_curator.logging_utils import get_action_logger


MAX_NESTED_ZIP_DEPTH = 5


def scan_directory(source_dir: Path) -> list[dict]:
    """Return files from a source directory, including ZIP contents."""

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
                    archive_path=path,
                    archive_relative_path=relative_path,
                )
            )
        else:
            discovered.append({
                "path": relative_path,
                "classification_path": path,
                "source_type": "filesystem",
                "archive_path": None,
                "archive_chain": [],
                "member_path": None,
                "size_bytes": path.stat().st_size,
            })

    return discovered


def scan_zip(
    archive_path: Path,
    archive_relative_path: str,
    archive_chain: list[str] | None = None,
    archive_bytes: bytes | None = None,
) -> list[dict]:
    """Recursively list files in a ZIP and any nested ZIPs."""
    if archive_chain is None:
        archive_chain = []

    logger = logging.getLogger(__name__)

    if len(archive_chain) >= MAX_NESTED_ZIP_DEPTH:
        logger.warning(
            "Maximum nested ZIP depth reached for %s",
            "::".join([archive_relative_path, *archive_chain]),
        )
        return []

    discovered = []
    current_archive = "::".join([archive_relative_path, *archive_chain])

    try:
        archive_context = (
            ZipFile(archive_path)
            if archive_bytes is None
            else ZipFile(BytesIO(archive_bytes))
        )

        with archive_context as archive:
            for member in archive.infolist():
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

                member_suffix = PurePosixPath(member_path).suffix.lower()

                # Recursively inspect valid nested ZIP archives.
                if member_suffix == ".zip":
                    with archive.open(member, "r") as stream:
                        nested_bytes = stream.read()

                    if not is_zipfile(BytesIO(nested_bytes)):
                        logger.warning(
                            "Skipping ZIP-named member that is not a valid ZIP: %s::%s",
                            current_archive,
                            member_path,
                        )
                        continue

                    discovered.extend(
                        scan_zip(
                            archive_path=archive_path,
                            archive_relative_path=archive_relative_path,
                            archive_chain=[*archive_chain, member_path],
                            archive_bytes=nested_bytes,
                        )
                    )
                    continue

                full_path = "::".join([
                    archive_relative_path,
                    *archive_chain,
                    member_path,
                ])

                discovered.append({
                    "path": full_path,
                    "classification_path": PurePosixPath(member_path),
                    "source_type": (
                        "nested_archive_member"
                        if archive_chain
                        else "archive_member"
                    ),
                    "archive_path": archive_relative_path,
                    "archive_chain": list(archive_chain),
                    "member_path": member_path,
                    "size_bytes": member.file_size,
                })

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

    files = scan_directory(source_dir)
    suggestions: dict[str, list[dict]] = {}

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
            "archive_path": file["archive_path"],
            "archive_chain": file["archive_chain"],
            "member_path": file["member_path"],
            "size_bytes": file["size_bytes"],
            "suggested_category": category,
            "score": classification_result.score,
            "evidence": classification_result.evidence,
        }

        suggestions.setdefault(category, []).append(suggestion)

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
