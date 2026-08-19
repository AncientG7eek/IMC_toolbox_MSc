from pathlib import Path
from urllib.request import urlopen
import shutil


def download(url: str, destination: Path) -> Path:
    """Download a file from URL to destination."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {url}")

    with urlopen(url) as response:
        with destination.open("wb") as f:
            shutil.copyfileobj(response, f)

    print(f"Downloaded to {destination}")

    return destination