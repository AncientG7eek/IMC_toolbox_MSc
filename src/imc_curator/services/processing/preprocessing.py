"""Image preprocessing matching the ImmuVis transform pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.filters import butterworth, gaussian, median


@dataclass(frozen=True)
class PreprocessingConfig:
    """Configuration for the ImmuVis-style preprocessing chain.

    The defaults match ImmuVis: ``arcsinh(x / 5)`` followed by a
    Butterworth low-pass filter with a cutoff frequency ratio of 0.2.
    """

    preprocessing: str = "arcsinh"
    arcsinh_scale: float = 5.0
    denoising: str = "butterworth"
    butterworth_cutoff: float = 0.2
    butterworth_high_pass: bool = False
    median_kernel_size: int = 3
    gaussian_sigma: float = 1.0


def as_channel_first(image: np.ndarray) -> np.ndarray:
    """Return a float32 ``CYX`` array, treating 2-D input as one channel."""
    array = np.asarray(image)

    if array.ndim == 2:
        array = array[None, :, :]

    if array.ndim != 3:
        raise ValueError(
            "Expected a 2-D or 3-D image array, "
            f"got shape {array.shape}."
        )

    return array.astype(np.float32, copy=False)


def _preprocess_channels(
    array: np.ndarray,
    method: str,
    config: PreprocessingConfig,
) -> np.ndarray:
    if method == "arcsinh":
        return np.arcsinh(array / config.arcsinh_scale)

    if method == "log1p":
        return np.log1p(array)

    if method in {"", "none"}:
        return array

    raise ValueError(
        f"Unsupported preprocessing method {method!r}. "
        "Choose 'arcsinh', 'log1p', or 'none'."
    )


def _denoise_channels(
    array: np.ndarray,
    method: str,
    config: PreprocessingConfig,
) -> np.ndarray:
    if method == "butterworth":
        return np.stack(
            [
                butterworth(
                    channel,
                    cutoff_frequency_ratio=config.butterworth_cutoff,
                    high_pass=config.butterworth_high_pass,
                )
                for channel in array
            ]
        )

    if method == "median":
        footprint = np.ones(
            (config.median_kernel_size, config.median_kernel_size),
            dtype=bool,
        )
        return np.stack(
            [median(channel, footprint=footprint) for channel in array]
        )

    if method == "gaussian":
        return np.stack(
            [
                gaussian(
                    channel,
                    sigma=config.gaussian_sigma,
                    preserve_range=True,
                )
                for channel in array
            ]
        )

    if method in {"", "none"}:
        return array

    raise ValueError(
        f"Unsupported denoising method {method!r}. "
        "Choose 'butterworth', 'median', 'gaussian', or 'none'."
    )


def apply_preprocessing(
    image: np.ndarray,
    config: PreprocessingConfig | None = None,
) -> np.ndarray:
    """Apply preprocessing and denoising to a 2-D or ``CYX`` image."""
    config = config or PreprocessingConfig()
    array = as_channel_first(image)

    preprocessing = str(config.preprocessing or "none").strip().casefold()
    denoising = str(config.denoising or "none").strip().casefold()

    array = _preprocess_channels(array, preprocessing, config)
    array = _denoise_channels(array, denoising, config)

    return np.asarray(array, dtype=np.float32)
