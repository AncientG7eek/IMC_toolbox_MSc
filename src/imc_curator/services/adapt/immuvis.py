"""Adapt curated-database marker files into immuvis model configuration."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
import yaml

from imc_curator.config import (
    get_curated_file_path,
    get_workspace_dir,
    load_config,
)
from imc_curator.services.adapt.base import ModelConfig
from imc_curator.services.processing.clip_limits import (
    ClipLimitConfig,
    build_dataset_image_map,
    compute_clip_limits,
)
from imc_curator.services.processing.preprocess import (
    PreprocessConfig,
    load_preprocess_config,
    preprocess_config_path,
    preprocess_signature,
)
from imc_curator.services.processing.preprocessing import (
    PreprocessingConfig,
)


TOKENIZER_FILENAME = "all_markers_tokenizer.yaml"
PANELS_FILENAME = "all_panels_config.yaml"
MARKER_STATS_FILENAME = "marker_ds_stats.csv"

CLIP_LIMIT_CONFIG = ClipLimitConfig(
    percentile=99.0,
    max_images_per_dataset=8,
    max_pixels_per_image=50_000,
    max_total_pixels=2_000_000,
    decimals=3,
    fallback=5.0,
    preprocessing=PreprocessingConfig(
        preprocessing="arcsinh",
        arcsinh_scale=5.0,
        denoising="butterworth",
        butterworth_cutoff=0.2,
        butterworth_high_pass=False,
    ),
)


def _write_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )


def _output_path(config: dict, key: str, default: str) -> Path:
    """Resolve a configured output filename against the workspace."""
    value = str(config.get("curation", {}).get(key, default))
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = get_workspace_dir(config) / path
    return path


def _load_existing_panels(path: Path) -> dict:
    if not path.is_file():
        return {}

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}

    return data if isinstance(data, dict) else {}


def adapt_immuvis() -> str:
    """Generate tokenizer and panel configs for immuvis."""
    config = load_config()
    tokenizer_path = _output_path(
        config,
        "tokenizer_output_file",
        TOKENIZER_FILENAME,
    )
    panels_path = _output_path(
        config,
        "panels_output_file",
        PANELS_FILENAME,
    )
    marker_stats_filename = str(
        config.get("curation", {}).get(
            "marker_stats_file",
            MARKER_STATS_FILENAME,
        )
    )

    marker_names_path = get_curated_file_path(
        config,
        "global_marker_names_file",
    )
    marker_channels_path = get_curated_file_path(
        config,
        "global_marker_channels_file",
    )

    if (
        not marker_names_path.is_file()
        or not marker_channels_path.is_file()
    ):
        raise typer.BadParameter(
            "Curated-database marker files are missing. Run "
            "`imc-curator finalize <project>` for at least one project "
            "before generating model configuration."
        )

    marker_names = pd.read_csv(marker_names_path)
    all_markers = sorted(
        marker_names["Marker Name"].dropna().astype(str).unique()
    )
    tokenizer = {
        marker: index
        for index, marker in enumerate(all_markers)
    }
    _write_yaml(tokenizer_path, tokenizer)

    channels = pd.read_csv(marker_channels_path)
    dataset_columns = [
        column
        for column in channels.columns
        if column != "Marker Name"
    ]

    markers_by_dataset = {}
    for dataset in dataset_columns:
        entries = []
        for _, row in channels.iterrows():
            marker = str(row.get("Marker Name", "")).strip()
            channel_value = row.get(dataset)
            if not marker or pd.isna(channel_value):
                continue
            channel_text = str(channel_value).strip()
            if not channel_text:
                continue
            entries.append((float(channel_text), marker))

        entries.sort(key=lambda item: item[0])
        markers_by_dataset[dataset] = [
            marker for _, marker in entries
        ]

    existing = _load_existing_panels(panels_path)
    paths = existing.get("paths", {"train": "", "test": ""})
    datasets = sorted(markers_by_dataset)

    resolved_preprocess_path = preprocess_config_path(config)
    if resolved_preprocess_path.is_file():
        preprocess_config = load_preprocess_config(
            resolved_preprocess_path
        )
        preprocessing_note = None
    else:
        preprocess_config = PreprocessConfig()
        preprocessing_note = (
            "No preprocessing config found at "
            f"{resolved_preprocess_path}; using ImmuVis defaults."
        )

    dataset_images, image_diagnostics = build_dataset_image_map(
        config,
        datasets,
    )
    computed_limits = compute_clip_limits(
        dataset_images,
        CLIP_LIMIT_CONFIG,
        preprocessing_by_dataset={
            dataset: preprocess_config.for_dataset(dataset)
            for dataset in datasets
        },
    )
    immuvis_config = ImmuvisConfig(clip_limits=computed_limits)
    clip_limits = {
        dataset: immuvis_config.clip_limit(dataset)
        for dataset in datasets
    }

    panels = {
        "paths": paths,
        "datasets": datasets,
        "clip_limits": clip_limits,
        "marker_stats": marker_stats_filename,
        "markers": markers_by_dataset,
    }
    _write_yaml(panels_path, panels)

    report_lines = [
        f"Tokenizer written to {tokenizer_path}",
        f"Panels written to {panels_path}",
        "Preprocessing:",
        f"  global: {preprocess_signature(preprocess_config)}",
    ]

    for dataset in sorted(preprocess_config.dataset_overrides):
        report_lines.append(
            f"  {dataset}: {preprocess_signature(preprocess_config, dataset)}",
        )

    report_lines.append("Clip limits:")

    for dataset in datasets:
        image_count = len(dataset_images.get(dataset, []))
        if image_count:
            report_lines.append(
                f"  {dataset}: {clip_limits[dataset]} "
                f"({image_count} image(s))"
            )
        else:
            report_lines.append(
                f"  {dataset}: {clip_limits[dataset]} "
                "(fallback; no curated images found)"
            )

    register_note = image_diagnostics.get("register")
    if register_note:
        report_lines.append(f"  Note: {register_note}")

    if preprocessing_note:
        report_lines.append(f"  Note: {preprocessing_note}")

    for dataset, message in image_diagnostics.items():
        if dataset == "register":
            continue
        report_lines.append(f"  Note for {dataset}: {message}")

    return "\n".join(report_lines)


class ImmuvisConfig(ModelConfig):
    model_name = "immuvis"

    def __init__(
        self,
        clip_limits: dict[str, float] | None = None,
    ) -> None:
        self._clip_limits = dict(clip_limits or {})

    def clip_limit(self, dataset: str) -> float:
        """Return the computed clipping limit for a dataset."""
        return float(
            self._clip_limits.get(
                dataset,
                CLIP_LIMIT_CONFIG.fallback,
            )
        )

    def adapt(self) -> str:
        return adapt_immuvis()
