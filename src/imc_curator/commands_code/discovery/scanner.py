from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile
import logging

from imc_curator.commands_code.discovery.classifier import classify_file
from imc_curator.config import load_search_config
from imc_curator.logging_utils import get_action_logger


def scan_directory(source_dir: Path) -> list[dict]:
    """Return all files in the source dataset."""

    source_dir = source_dir.resolve()
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
            discovered.append(
                {
                    "path": relative_path,
                    "classification_path": path,
                    "source_type": "filesystem",
                    "archive_path": None,
                    "member_path": None,
                    "size_bytes": path.stat().st_size,
                }
                
            )

    return discovered


def scan_zip(
        archive_path: Path,
        archive_relative_path: str,
) -> list[dict]:
    """List files in a ZIP archive without extracting them."""
    discovered = []

    try:
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue

                member_path = PurePosixPath(member.filename)

                discovered.append(
                    {
                        "path": f"{archive_relative_path}::{member.filename}",
                        "classification_path": member_path,
                        "source_type": "archive_member",
                        "archive_path": archive_relative_path,
                        "member_path": member.filename,
                        "size_bytes": member.file_size,
                    }
                )
    except (BadZipFile, OSError) as exc:
        logging.getLogger(__name__).warning(
            "Could not inspect ZIP archive %s: %s",
            archive_path,
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
        action="file_classification"
    )

    files = scan_directory(source_dir)
    suggestions: dict[str, list[dict]] = {}

    for file in files:

        classification_result = classify_file(
            file["classification_path"], 
            config=config, 
            logger=logger
        )

        category = classification_result.category

        suggestion = {
            "path": file["path"],
            "source_type": file["source_type"],
            "archive_path": file["archive_path"],
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

    return suggestions