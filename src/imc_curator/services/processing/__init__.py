"""Image preprocessing and dataset-level statistics."""

from imc_curator.services.processing.clip_limits import (
    ClipLimitConfig,
    compute_clip_limit,
    compute_clip_limits,
)
from imc_curator.services.processing.image_registry import (
    build_dataset_image_map,
    load_image_register,
    resolve_registered_image,
)
from imc_curator.services.processing.preprocess import (
    PreprocessConfig,
    PreprocessOutputConfig,
    PreprocessResult,
    load_preprocess_config,
    preprocess_config_path,
    preprocess_registered_images,
    preprocess_signature,
    write_default_preprocess_config,
)
from imc_curator.services.processing.preprocessing import (
    PreprocessingConfig,
    apply_preprocessing,
)


__all__ = [
    "ClipLimitConfig",
    "PreprocessConfig",
    "PreprocessOutputConfig",
    "PreprocessResult",
    "PreprocessingConfig",
    "apply_preprocessing",
    "build_dataset_image_map",
    "compute_clip_limit",
    "compute_clip_limits",
    "load_image_register",
    "load_preprocess_config",
    "preprocess_config_path",
    "preprocess_registered_images",
    "preprocess_signature",
    "resolve_registered_image",
    "write_default_preprocess_config",
]
