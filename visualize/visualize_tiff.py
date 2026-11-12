
from pathlib import Path
import argparse

import numpy as np
import tifffile
import matplotlib.pyplot as plt
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = SCRIPT_DIR / "images"


def normalize_channel(image, lower=1, upper=99.8):
    """Scale channel intensities to 8-bit using percentile clipping."""
    image = image.astype(np.float32)

    low, high = np.percentile(image, [lower, upper])

    if high <= low:
        return np.zeros(image.shape, dtype=np.uint8)

    image = np.clip(image, low, high)
    image = (image - low) / (high - low)

    return (image * 255).astype(np.uint8)


def load_multichannel_tiff(tiff_path, z_index=0):
    """Load a TIFF and return its channels in CYX order."""
    with tifffile.TiffFile(tiff_path) as tif:
        series = tif.series[0]
        image = series.asarray()
        axes = series.axes

    print(f"Original shape: {image.shape}")
    print(f"TIFF axes: {axes}")

    # Remove singleton dimensions, updating the axes accordingly.
    for axis_index in reversed(range(image.ndim)):
        if image.shape[axis_index] == 1:
            image = np.squeeze(image, axis=axis_index)
            axes = axes[:axis_index] + axes[axis_index + 1:]

    # Select one Z plane if the TIFF contains multiple planes.
    if "Z" in axes:
        z_axis = axes.index("Z")

        if not 0 <= z_index < image.shape[z_axis]:
            raise ValueError(
                f"z_index must be between 0 and {image.shape[z_axis] - 1}"
            )

        image = np.take(image, z_index, axis=z_axis)
        axes = axes.replace("Z", "")

    # This script expects channel, Y and X dimensions.
    if not all(axis in axes for axis in ("C", "Y", "X")):
        raise ValueError(
            f"Could not identify channel/Y/X axes. "
            f"Found axes: {axes}, shape: {image.shape}"
        )

    # Rearrange dimensions to channels x height x width.
    image = np.transpose(
        image,
        [axes.index("C"), axes.index("Y"), axes.index("X")]
    )

    print(f"Processed shape (C, Y, X): {image.shape}")

    return image


def save_channels(image, output_dir):
    """Save every channel as a separate grayscale PNG."""
    output_dir.mkdir(parents=True, exist_ok=True)

    channel_images = []

    for channel_index, channel in enumerate(image):
        normalized = normalize_channel(channel)

        output_path = output_dir / f"channel_{channel_index:03d}.png"
        Image.fromarray(normalized).save(output_path)

        channel_images.append(normalized)

        print(f"Saved: {output_path}")

    return channel_images


def create_contact_sheet(channel_images, output_dir):
    """Create a grid displaying all channels."""
    n_channels = len(channel_images)

    columns = min(4, n_channels)
    rows = int(np.ceil(n_channels / columns))

    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=(4 * columns, 4 * rows),
        squeeze=False
    )

    for index, ax in enumerate(axes.flat):
        if index < n_channels:
            ax.imshow(channel_images[index], cmap="gray")
            ax.set_title(f"Channel {index}")
        ax.axis("off")

    fig.tight_layout()

    output_path = output_dir / "contact_sheet.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved contact sheet: {output_path}")


def create_rgb_composite(channel_images, rgb_channels, output_dir):
    """Create an RGB composite using three selected channels."""
    if len(rgb_channels) != 3:
        raise ValueError("Provide exactly three channel indices.")

    for index in rgb_channels:
        if index < 0 or index >= len(channel_images):
            raise ValueError(f"Channel index {index} does not exist.")

    rgb = np.stack(
        [channel_images[index] for index in rgb_channels],
        axis=-1
    )

    output_path = output_dir / "rgb_composite.png"
    Image.fromarray(rgb).save(output_path)

    print(f"Saved RGB composite: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Visualize a multichannel IMC TIFF."
    )

    parser.add_argument(
        "tiff",
        type=Path,
        help="Path to the multichannel TIFF file"
    )

    parser.add_argument(
        "--z-index",
        type=int,
        default=0,
        help="Z plane to visualize if the TIFF contains multiple planes"
    )
    parser.add_argument(
        "--rgb",
        nargs=3,
        type=int,
        metavar=("RED", "GREEN", "BLUE"),
        help="Three channel indices for an RGB composite"
    )

    args = parser.parse_args()

    tiff_path = Path(args.tiff)
    output_dir = OUTPUT_ROOT / tiff_path.stem

    if not tiff_path.is_file():
        raise FileNotFoundError(tiff_path)

    image = load_multichannel_tiff(tiff_path, args.z_index)

    channel_images = save_channels(image, output_dir)

    create_contact_sheet(channel_images, output_dir)

    if args.rgb:
        create_rgb_composite(
            channel_images,
            args.rgb,
            output_dir
        )

    print("\nVisualization complete.")


if __name__ == "__main__":
    main()
