
from pathlib import Path

from readimc import MCDFile


def inspect_mcd(mcd_path: Path) -> list[dict]:
    """Inspect MCD metadata and verify acquisition image data are readable."""

    acquisitions = []

    with MCDFile(mcd_path) as mcd:
        for slide in mcd.slides:
            # Record whether a slide image is available.
            try:
                slide_image = mcd.read_slide(slide)
                slide_image_available = slide_image is not None
                slide_image_shape = (
                    list(slide_image.shape)
                    if slide_image is not None
                    else None
                )
            except Exception as exc:
                slide_image_available = False
                slide_image_shape = None
                slide_image_error = str(exc)
            else:
                slide_image_error = None

            for panorama in slide.panoramas:
                try:
                    panorama_image = mcd.read_panorama(panorama)
                    panorama_available = panorama_image is not None
                    panorama_shape = (
                        list(panorama_image.shape)
                        if panorama_image is not None
                        else None
                    )
                    panorama_error = None
                except Exception as exc:
                    panorama_available = False
                    panorama_shape = None
                    panorama_error = str(exc)

                # Panoramas are reported separately from acquisitions.
                acquisitions.append({
                    "mcd_path": str(mcd_path),
                    "record_type": "panorama",
                    "slide_id": slide.id,
                    "slide_description": slide.description or "",
                    "panorama_id": panorama.id,
                    "panorama_description": panorama.description or "",
                    "image_available": panorama_available,
                    "image_shape": panorama_shape,
                    "image_error": panorama_error,
                })

            for acquisition in slide.acquisitions:
                try:
                    image = mcd.read_acquisition(acquisition)
                    image_available = image is not None and image.size > 0
                    image_shape = list(image.shape) if image_available else None
                    image_error = None
                except Exception as exc:
                    image_available = False
                    image_shape = None
                    image_error = str(exc)

                acquisitions.append({
                    "mcd_path": str(mcd_path),
                    "record_type": "acquisition",
                    "slide_id": slide.id,
                    "slide_description": slide.description or "",
                    "slide_image_available": slide_image_available,
                    "slide_image_shape": slide_image_shape,
                    "slide_image_error": slide_image_error,
                    "acquisition_id": acquisition.id,
                    "acquisition_name": acquisition.description or "",
                    "width_px": acquisition.width_px,
                    "height_px": acquisition.height_px,
                    "channel_names": list(acquisition.channel_names),
                    "channel_labels": list(acquisition.channel_labels),
                    "image_available": image_available,
                    "image_shape": image_shape,
                    "image_error": image_error,
                })

    return acquisitions
