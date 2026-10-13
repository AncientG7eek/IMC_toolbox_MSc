from pathlib import Path
from shutil import copytree
from urllib.parse import urlparse
from urllib.request import urlretrieve
from zipfile import ZipFile

from imc_curator.config import get_archive_extensions


archive_extensions = get_archive_extensions()


def is_url(source: str) -> bool:
    """Return True if source is an HTTP or HTTPS URL."""

    parsed = urlparse(source)

    return parsed.scheme in {"http", "https"}


def download(
    url: str,
    destination: Path,
) -> Path:
    """
    Download a dataset archive to a temporary location.

    Parameters
    ----------
    url:
        HTTP or HTTPS URL of the dataset archive.

    destination:
        Directory in which to save the downloaded archive.

    Returns
    -------
    Path
        Path to the downloaded archive.
    """

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = Path(
        urlparse(url).path
    ).name

    if not filename:
        raise ValueError(
            f"Could not determine filename from URL: {url}"
        )

    archive_path = destination / filename

    print(f"Downloading {url}")
    print(f"Saving to {archive_path}")

    urlretrieve(
        url,
        archive_path,
    )

    return archive_path


def extract_zip(
    archive_path: Path,
    destination: Path,
) -> Path:
    """
    Extract a ZIP archive into destination.
    """

    if not archive_path.exists():
        raise FileNotFoundError(
            f"Archive does not exist: {archive_path}"
        )

    if archive_path.suffix.lower() not in archive_extensions:
        raise ValueError(
            f"Unsupported archive format: {archive_path.suffix}"
        )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    with ZipFile(archive_path) as archive:
        archive.extractall(destination)

    return destination


def import_local_directory(
    source: Path,
    destination: Path,
) -> Path:
    """
    Copy a local dataset directory into destination.
    """

    if not source.exists():
        raise FileNotFoundError(
            f"Source directory does not exist: {source}"
        )

    if not source.is_dir():
        raise ValueError(
            f"Source is not a directory: {source}"
        )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    copytree(
        source,
        destination,
        dirs_exist_ok=True,
    )

    return destination


def import_local_archive(
    source: Path,
    destination: Path,
) -> Path:
    """
    Extract a local archive into destination.
    """

    if not source.exists():
        raise FileNotFoundError(
            f"Archive does not exist: {source}"
        )

    if not source.is_file():
        raise ValueError(
            f"Archive path is not a file: {source}"
        )

    if source.suffix.lower() not in archive_extensions:
        raise ValueError(
            f"Unsupported archive format: {source.suffix}"
        )

    return extract_zip(
        archive_path=source,
        destination=destination,
    )


def import_local(
    source: Path,
    destination: Path,
) -> Path:
    """
    Import a local dataset.

    The source may be either a directory or a supported archive.
    """

    source = source.expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(
            f"Local source does not exist: {source}"
        )

    if source.is_dir():
        return import_local_directory(
            source=source,
            destination=destination,
        )

    if source.is_file():
        return import_local_archive(
            source=source,
            destination=destination,
        )

    raise ValueError(
        f"Unsupported local source: {source}"
    )


def import_from_url(
    url: str,
    destination: Path,
) -> Path:
    """
    Download an archive and extract it into destination.

    The downloaded archive is removed after successful extraction.
    """

    if not is_url(url):
        raise ValueError(
            f"Source is not an HTTP/HTTPS URL: {url}"
        )

    # Temporary directory for the downloaded archive
    temporary_dir = destination.parent / ".download"

    archive_path = download(
        url=url,
        destination=temporary_dir,
    )

    try:
        return extract_zip(
            archive_path=archive_path,
            destination=destination,
        )
    finally:
        if archive_path.exists():
            archive_path.unlink()

        if temporary_dir.exists():
            try:
                temporary_dir.rmdir()
            except OSError:
                pass


def import_source(
    source: str,
    destination: Path,
) -> Path:
    """
    Import a dataset from a URL or local path.

    The resulting dataset is always placed in destination.
    """

    if is_url(source):
        return import_from_url(
            url=source,
            destination=destination,
        )

    return import_local(
        source=Path(source),
        destination=destination,
    )