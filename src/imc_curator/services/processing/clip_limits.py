"""Compute dataset-level ImmuVis clip limits from curated images."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import warnings

import numpy as np
import tifffile

from imc_curator.services.processing.image_registry import (
    build_dataset_image_map,
)
from imc_curator.services.processing.preprocessing import (
    PreprocessingConfig,
    apply_preprocessing,
)


@dataclass(frozen=True)
class ClipLimitConfig:
    """Configuration for clip-limit estimation.

    The ImmuVis reference pipeline uses a per-dataset 99th percentile
    after arcsinh and Butterworth preprocessing, then clips and scales
    each image by that value.
    """

    percentile: float = 99.0
    max_images_per_dataset: int = 8
    max_pixels_per_image: int = 50_000
    max_total_pixels: int = 2_000_000
    decimals: int = 3
    fallback: float = 5.0
    seed: int = 0
    preprocessing: PreprocessingConfig = field(
        default_factory=PreprocessingConfig
    )


def _evenly_spaced(paths: list[Path], limit: int) -> list[Path]:
    if limit <= 0:
        return []

    if len(paths) <= limit:
        return paths

    indices = np.linspace(0, len(paths) - 1, limit, dtype=int)
    return [paths[int(index)] for index in indices]


def _sample_preprocessed_pixels(
    paths: list[Path],
    config: ClipLimitConfig,
) -> np.ndarray:
    rng = np.random.default_rng(config.seed)
    samples: list[np.ndarray] = []
    remaining = config.max_total_pixels

    for path in _evenly_spaced(paths, config.max_images_per_dataset):
        if remaining <= 0:
            break

        try:
            image = tifffile.imread(path)
        except Exception as exc:
            warnings.warn(
                f"Could not read {path} for clip-limit estimation: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            continue

        processed = apply_preprocessing(image, config.preprocessing)
        values = processed.reshape(-1)
        values = values[np.isfinite(values)]

        if values.size == 0:
            continue

        if values.size > config.max_pixels_per_image:
            indices = rng.integers(
                0,
                values.size,
                size=config.max_pixels_per_image,
            )
            values = values[indices]

        if values.size > remaining:
            indices = rng.integers(0, values.size, size=remaining)
            values = values[indices]

        samples.append(np.asarray(values, dtype=np.float32))
        remaining -= values.size

    if not samples:
        return np.empty(0, dtype=np.float32)

    return np.concatenate(samples)


def compute_clip_limit(
    paths: list[Path],
    config: ClipLimitConfig | None = None,
) -> float:
    """Compute one clip limit for a dataset/panel."""
    config = config or ClipLimitConfig()
    values = _sample_preprocessed_pixels(paths, config)

    if values.size == 0:
        return float(config.fallback)

    values = np.clip(values, 0, None)

    if not np.isfinite(values).any():
        return float(config.fallback)

    limit = float(np.percentile(values, config.percentile))

    if not np.isfinite(limit) or limit <= 0:
        return float(config.fallback)

    return round(limit, config.decimals)


def compute_clip_limits(
    dataset_images: dict[str, list[Path]],
    config: ClipLimitConfig | None = None,
    preprocessing_by_dataset: (
        dict[str, PreprocessingConfig] | None
    ) = None,
) -> dict[str, float]:
    """Compute one clip limit per dataset/panel."""
    config = config or ClipLimitConfig()
    preprocessing_by_dataset = preprocessing_by_dataset or {}
    preprocessing_by_casefold = {
        dataset.casefold(): preprocessing
        for dataset, preprocessing in preprocessing_by_dataset.items()
    }

    limits: dict[str, float] = {}

    for dataset, paths in dataset_images.items():
        dataset_config = config
        preprocessing = preprocessing_by_casefold.get(
            dataset.casefold()
        )

        if preprocessing is not None:
            dataset_config = replace(
                config,
                preprocessing=preprocessing,
            )

        limits[dataset] = compute_clip_limit(paths, dataset_config)

    return limits
