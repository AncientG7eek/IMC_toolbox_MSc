
from pathlib import Path

from readimc import MCDFile


def inspect_mcd(mcd_path: Path) -> list[dict]:
    """Read acquisition metadata from an MCD file without exporting images."""

    acquisitions = []

    with MCDFile(mcd_path) as mcd:
        for slide in mcd.slides:
            for acquisition in slide.acquisitions:
                acquisitions.append({
                    "mcd_path": str(mcd_path),
                    "slide_id": slide.id,
                    "slide_description": slide.description or "",
                    "acquisition_id": acquisition.id,
                    "acquisition_name": acquisition.description or "",
                    "width_px": acquisition.width_px,
                    "height_px": acquisition.height_px,
                    "channel_names": list(acquisition.channel_names),
                    "channel_labels": list(acquisition.channel_labels),
                })

    return acquisitions
