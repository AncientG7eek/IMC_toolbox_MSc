"""Adapt global marker files into immuvis model configuration."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from imc_curator.config import (
    PROJECT_ROOT,
    get_global_file_path,
    load_config,
)
from imc_curator.services.adapt.base import ModelConfig


TOKENIZER_PATH = PROJECT_ROOT / "all_markers_tokenizer.yaml"
PANELS_PATH = PROJECT_ROOT / "all_panels_config.yaml"
MARKER_STATS_FILENAME = "marker_ds_stats.csv"


def _write_yaml(path: Path, data: object) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )


def _load_existing_panels() -> dict:
    if not PANELS_PATH.is_file():
        return {}

    try:
        data = yaml.safe_load(PANELS_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}

    return data if isinstance(data, dict) else {}


def adapt_immuvis() -> str:
    """Generate tokenizer and panel configs for immuvis."""
    config = load_config()

    marker_names_path = get_global_file_path(
        config,
        "global_marker_names_file",
    )
    marker_channels_path = get_global_file_path(
        config,
        "global_marker_channels_file",
    )

    marker_names = pd.read_csv(marker_names_path)
    all_markers = sorted(
        marker_names["Marker Name"].dropna().astype(str).unique()
    )
    tokenizer = {
        marker: index
        for index, marker in enumerate(all_markers)
    }
    _write_yaml(TOKENIZER_PATH, tokenizer)

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

    existing = _load_existing_panels()
    paths = existing.get("paths", {"train": "", "test": ""})
    datasets = sorted(markers_by_dataset)
    clip_limits = {
        dataset: ImmuvisConfig().clip_limit(dataset)
        for dataset in datasets
    }

    panels = {
        "paths": paths,
        "datasets": datasets,
        "clip_limits": clip_limits,
        "marker_stats": MARKER_STATS_FILENAME,
        "markers": markers_by_dataset,
    }
    _write_yaml(PANELS_PATH, panels)

    return (
        f"Tokenizer written to {TOKENIZER_PATH}\n"
        f"Panels written to {PANELS_PATH}"
    )


class ImmuvisConfig(ModelConfig):
    model_name = "immuvis"

    def clip_limit(self, dataset: str) -> float:
        """Return the clipping limit for a dataset."""
        return 1.0

    def adapt(self) -> str:
        return adapt_immuvis()
