
"""Extract raw OME channel metadata from TIFF files.

This module does not parse marker/isotope naming conventions.
It extracts the raw metadata for later review and regex-based parsing.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


import tifffile


TIFF_EXTENSIONS = {".tif", ".tiff"}

CHANNEL_COLUMNS = [
    "tiff_path",
    "image_name",
    "image_id",
    "channel_number",
    "channel_id",
    "raw_name",
    "raw_fluor",
    "excitation_wavelength",
    "emission_wavelength",
    "color",
    "samples_per_pixel",
]

SCAN_COLUMNS = [
    "tiff_path",
    "status",
    "image_count",
    "channel_count",
    "error",
]


def local_name(tag: str) -> str:
    """Return an XML tag name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def child_elements(
    element: ET.Element,
    name: str,
) -> list[ET.Element]:
    """Return direct children matching an XML local name."""
    return [
        child
        for child in element
        if local_name(child.tag) == name
    ]


def attribute(element: ET.Element, name: str) -> str:
    """Return an XML attribute, or an empty string if missing."""
    return element.attrib.get(name, "")


def discover_tiffs(root_dir: Path) -> list[Path]:
    """Find TIFF files recursively in a directory."""
    return sorted(
        (
            path
            for path in root_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in TIFF_EXTENSIONS
        ),
        key=lambda path: str(path).lower(),
    )


def extract_tiff_metadata(
    tiff_path: Path,
    root_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract raw channel metadata from one TIFF.

    Returns:
        A tuple containing:
        - One dictionary per channel.
        - One scan-status dictionary for the TIFF.
    """
    relative_path = str(tiff_path.relative_to(root_dir))

    scan_record: dict[str, Any] = {
        "tiff_path": relative_path,
        "status": "",
        "image_count": 0,
        "channel_count": 0,
        "error": "",
    }

    try:
        # Read embedded OME-XML without loading pixel arrays.
        with tifffile.TiffFile(tiff_path) as tif:
            ome_xml = tif.ome_metadata

        if not ome_xml:
            scan_record["status"] = "no_ome_metadata"
            return [], scan_record

        root = ET.fromstring(ome_xml)

        if local_name(root.tag) != "OME":
            scan_record["status"] = "unexpected_xml_root"
            return [], scan_record

        channel_records: list[dict[str, Any]] = []
        image_count = 0

        for image in root.iter():
            if local_name(image.tag) != "Image":
                continue

            pixels_elements = child_elements(image, "Pixels")

            if not pixels_elements:
                continue

            image_count += 1
            image_name = attribute(image, "Name")
            image_id = attribute(image, "ID")

            for pixels in pixels_elements:
                for channel in child_elements(pixels, "Channel"):
                    channel_id = attribute(channel, "ID")

                    # OME IDs often end in a zero-based index, but
                    # numbering here is intentionally human-readable
                    # and 1-based within this TIFF.
                    channel_number = len(channel_records) + 1

                    channel_records.append({
                        "tiff_path": relative_path,
                        "image_name": image_name,
                        "image_id": image_id,
                        "channel_number": channel_number,
                        "channel_id": channel_id,
                        "raw_name": attribute(channel, "Name"),
                        "raw_fluor": attribute(channel, "Fluor"),
                        "excitation_wavelength": attribute(
                            channel,
                            "ExcitationWavelength",
                        ),
                        "emission_wavelength": attribute(
                            channel,
                            "EmissionWavelength",
                        ),
                        "color": attribute(channel, "Color"),
                        "samples_per_pixel": attribute(
                            channel,
                            "SamplesPerPixel",
                        ),
                    })

        scan_record["image_count"] = image_count
        scan_record["channel_count"] = len(channel_records)

        if channel_records:
            scan_record["status"] = "ok"
        else:
            scan_record["status"] = "ome_found_no_channels"

        return channel_records, scan_record

    except ET.ParseError as exc:
        scan_record["status"] = "xml_parse_error"
        scan_record["error"] = str(exc)
        return [], scan_record

    except Exception as exc:
        # Keep scanning if this TIFF is damaged or unreadable.
        scan_record["status"] = "error"
        scan_record["error"] = f"{type(exc).__name__}: {exc}"
        return [], scan_record


def extract_all_tiff_metadata(
    input_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract raw OME channel metadata from every TIFF in a directory.

    TIFFs are scanned recursively.

    Returns:
        channel_records: One dictionary per channel.
        scan_records: One dictionary per TIFF, including its status.
    """
    input_dir = input_dir.expanduser().resolve()

    if not input_dir.is_dir():
        raise NotADirectoryError(
            f"Input directory does not exist: {input_dir}"
        )

    channel_records: list[dict[str, Any]] = []
    scan_records: list[dict[str, Any]] = []

    tiff_paths = discover_tiffs(input_dir)
    total = len(tiff_paths)

    for index, tiff_path in enumerate(tiff_paths, start=1):
        channels, scan_record = extract_tiff_metadata(
            tiff_path=tiff_path,
            root_dir=input_dir,
        )

        channel_records.extend(channels)
        scan_records.append(scan_record)

        print(
            f"[{index}/{total}] "
            f"{scan_record['status']}: "
            f"{scan_record['tiff_path']} "
            f"({scan_record['channel_count']} channels)"
        )

    return channel_records, scan_records


def write_csv(
    output_path: Path,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> Path:
    """Write records to a CSV file and return its path."""
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    return output_path
