"""Curated-database-level preprocessing configuration and execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
import tomllib

import pandas as pd
import tifffile
import tomli_w

from imc_curator.config import (
    get_curated_database_dir,
    get_curated_file_path,
)
from imc_curator.services.processing.image_registry import (
    load_image_register,
    resolve_registered_image,
    text_value,
)
from imc_curator.services.processing.preprocessing import (
    PreprocessingConfig,
    apply_preprocessing,
)


DEFAULT_PREPROCESSING_CONFIG_FILENAME = "preprocessing.toml"
PREPROCESSED_REGISTER_FILENAME = (
    "global_register_of_preprocessed_images.csv"
)
PREPROCESSED_REGISTER_COLUMNS = [
    "global_path",
    "relative_path",
    "source_global_path",
    "source_relative_path",
    "shape",
    "panel_name",
    "cohort_name",
    "project_name",
    "preprocessing",
    "status",
]

_PREPROCESSING_METHODS = {"arcsinh", "log1p", "none"}
_DENOISING_METHODS = {"butterworth", "median", "gaussian", "none"}
_COMPRESSION_METHODS = {"none", "zlib", "lzw", "deflate"}

DEFAULT_PREPROCESSING_CONFIG_TOML = """# Global preprocessing for the curated image database.
#
# These settings are applied to every panel by default. Add optional
# per-panel overrides under [datasets.<panel_name>] if needed.

[preprocessing]
method = "arcsinh"          # arcsinh | log1p | none
arcsinh_scale = 5.0

[denoising]
method = "butterworth"      # butterworth | median | gaussian | none
butterworth_cutoff = 0.2
butterworth_high_pass = false
median_kernel_size = 3
gaussian_sigma = 1.0

[output]
directory = "preprocessed"
register_file = "global_register_of_preprocessed_images.csv"
compression = "zlib"        # zlib | lzw | deflate | none

# Optional per-panel overrides. Any omitted field inherits the global value.
#
# [datasets.panelA.preprocessing]
# method = "arcsinh"
# arcsinh_scale = 3.0
#
# [datasets.panelA.denoising]
# method = "butterworth"
# butterworth_cutoff = 0.1
"""


@dataclass(frozen=True)
class PreprocessOutputConfig:
    """Where preprocessed images and their register are written."""

    directory: str = "preprocessed"
    register_file: str = PREPROCESSED_REGISTER_FILENAME
    compression: str = "zlib"


@dataclass(frozen=True)
class PreprocessConfig:
    """Global preprocessing settings with optional per-panel overrides."""

    preprocessing: PreprocessingConfig = field(
        default_factory=PreprocessingConfig
    )
    output: PreprocessOutputConfig = field(
        default_factory=PreprocessOutputConfig
    )
    dataset_overrides: dict[str, PreprocessingConfig] = field(
        default_factory=dict
    )

    def for_dataset(
        self,
        dataset: str | None,
    ) -> PreprocessingConfig:
        if not dataset:
            return self.preprocessing

        by_casefold = {
            name.casefold(): config
            for name, config in self.dataset_overrides.items()
        }
        return by_casefold.get(
            dataset.casefold(),
            self.preprocessing,
        )


@dataclass(frozen=True)
class PreprocessResult:
    """Summary of a preprocessing run."""

    processed: int
    skipped: int
    failed: int
    output_dir: Path
    output_register: Path
    report_path: Path
    report: str


def _validate_preprocessing(config: PreprocessingConfig) -> None:
    if config.preprocessing not in _PREPROCESSING_METHODS:
        raise ValueError(
            f"Unsupported preprocessing method {config.preprocessing!r}. "
            f"Choose one of: {', '.join(sorted(_PREPROCESSING_METHODS))}."
        )

    if config.denoising not in _DENOISING_METHODS:
        raise ValueError(
            f"Unsupported denoising method {config.denoising!r}. "
            f"Choose one of: {', '.join(sorted(_DENOISING_METHODS))}."
        )

    if config.arcsinh_scale <= 0:
        raise ValueError("arcsinh_scale must be greater than 0.")

    if not 0 < config.butterworth_cutoff <= 1:
        raise ValueError(
            "butterworth_cutoff must be in the range (0, 1]."
        )

    if config.median_kernel_size < 1:
        raise ValueError("median_kernel_size must be at least 1.")

    if config.gaussian_sigma <= 0:
        raise ValueError("gaussian_sigma must be greater than 0.")


def _build_preprocessing(
    base: PreprocessingConfig,
    preprocessing_section: dict,
    denoising_section: dict,
) -> PreprocessingConfig:
    config = replace(
        base,
        preprocessing=str(
            preprocessing_section.get(
                "method",
                base.preprocessing,
            )
        ).strip().casefold(),
        arcsinh_scale=float(
            preprocessing_section.get(
                "arcsinh_scale",
                base.arcsinh_scale,
            )
        ),
        denoising=str(
            denoising_section.get(
                "method",
                base.denoising,
            )
        ).strip().casefold(),
        butterworth_cutoff=float(
            denoising_section.get(
                "butterworth_cutoff",
                base.butterworth_cutoff,
            )
        ),
        butterworth_high_pass=bool(
            denoising_section.get(
                "butterworth_high_pass",
                base.butterworth_high_pass,
            )
        ),
        median_kernel_size=int(
            denoising_section.get(
                "median_kernel_size",
                base.median_kernel_size,
            )
        ),
        gaussian_sigma=float(
            denoising_section.get(
                "gaussian_sigma",
                base.gaussian_sigma,
            )
        ),
    )
    _validate_preprocessing(config)
    return config


def load_preprocess_config(path: Path) -> PreprocessConfig:
    """Load a curated-database preprocessing TOML."""
    path = Path(path).expanduser()

    with path.open("rb") as file:
        data = tomllib.load(file)

    global_config = _build_preprocessing(
        PreprocessingConfig(),
        data.get("preprocessing", {}),
        data.get("denoising", {}),
    )

    dataset_overrides: dict[str, PreprocessingConfig] = {}
    datasets_section = data.get("datasets", {})

    if not isinstance(datasets_section, dict):
        raise ValueError(
            "The [datasets] section must contain one table per panel."
        )

    for dataset, sections in datasets_section.items():
        if not isinstance(sections, dict):
            raise ValueError(
                f"[datasets.{dataset}] must be a table."
            )
        dataset_overrides[dataset] = _build_preprocessing(
            global_config,
            sections.get("preprocessing", {}),
            sections.get("denoising", {}),
        )

    output_section = data.get("output", {})
    compression = str(
        output_section.get("compression", "zlib")
    ).strip().casefold()

    if compression not in _COMPRESSION_METHODS:
        raise ValueError(
            f"Unsupported output compression {compression!r}. "
            f"Choose one of: {', '.join(sorted(_COMPRESSION_METHODS))}."
        )

    return PreprocessConfig(
        preprocessing=global_config,
        output=PreprocessOutputConfig(
            directory=str(
                output_section.get("directory", "preprocessed")
            ),
            register_file=str(
                output_section.get(
                    "register_file",
                    PREPROCESSED_REGISTER_FILENAME,
                )
            ),
            compression=compression,
        ),
        dataset_overrides=dataset_overrides,
    )


def write_default_preprocess_config(path: Path) -> Path:
    """Write the default curated-database preprocessing config."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        DEFAULT_PREPROCESSING_CONFIG_TOML,
        encoding="utf-8",
    )
    return path


def preprocess_config_path(
    config: dict,
    override: Path | None = None,
) -> Path:
    """Resolve the preprocessing config with the documented hierarchy."""
    if override is not None:
        return Path(override).expanduser()

    curation = config.get("curation", {})
    filename = str(
        curation.get(
            "preprocessing_config_file",
            DEFAULT_PREPROCESSING_CONFIG_FILENAME,
        )
    )
    return get_curated_database_dir(config) / filename


def preprocess_signature(
    config: PreprocessConfig,
    dataset: str | None = None,
) -> str:
    """Return a compact human-readable preprocessing description."""
    current = config.for_dataset(dataset)
    parts: list[str] = []

    if current.preprocessing == "arcsinh":
        parts.append(f"arcsinh(scale={current.arcsinh_scale:g})")
    elif current.preprocessing == "log1p":
        parts.append("log1p")

    if current.denoising == "butterworth":
        parts.append(
            "butterworth("
            f"cutoff={current.butterworth_cutoff:g},"
            f"high_pass={str(current.butterworth_high_pass).lower()}"
            ")"
        )
    elif current.denoising == "median":
        parts.append(
            f"median(kernel={current.median_kernel_size})"
        )
    elif current.denoising == "gaussian":
        parts.append(f"gaussian(sigma={current.gaussian_sigma:g})")

    return "+".join(parts) or "none"


def _markers_by_dataset(config: dict) -> dict[str, list[str]]:
    marker_channels_path = get_curated_file_path(
        config,
        "global_marker_channels_file",
    )

    if not marker_channels_path.is_file():
        return {}

    table = pd.read_csv(marker_channels_path)

    if "Marker Name" not in table.columns:
        return {}

    markers: dict[str, list[str]] = {}

    for dataset in table.columns:
        if dataset == "Marker Name":
            continue

        entries: list[tuple[float, str]] = []

        for _, row in table.iterrows():
            marker = text_value(row.get("Marker Name"))
            channel_value = row.get(dataset)

            if not marker or pd.isna(channel_value):
                continue

            channel_text = text_value(channel_value)
            if not channel_text:
                continue

            entries.append((float(channel_text), marker))

        entries.sort(key=lambda item: item[0])
        markers[dataset] = [marker for _, marker in entries]

    return markers


def _resolve_output_path(
    curated_dir: Path,
    value: str,
) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = curated_dir / path
    return path


def preprocess_registered_images(
    config: dict,
    preprocess_config: PreprocessConfig | None = None,
    *,
    datasets: list[str] | None = None,
    force: bool = False,
    progress=None,
) -> PreprocessResult:
    """Apply the curated preprocessing config to registered images."""
    preprocess_config = preprocess_config or PreprocessConfig()
    curated_dir = get_curated_database_dir(config)
    source_register = get_curated_file_path(
        config,
        "global_image_register_file",
    )
    output_dir = _resolve_output_path(
        curated_dir,
        preprocess_config.output.directory,
    )
    output_register = _resolve_output_path(
        curated_dir,
        preprocess_config.output.register_file,
    )
    report_path = output_dir / "preprocess_report.toml"

    table = load_image_register(config)
    markers_by_casefold = {
        dataset.casefold(): markers
        for dataset, markers in _markers_by_dataset(config).items()
    }

    requested = None
    if datasets:
        requested = {dataset.casefold() for dataset in datasets}
        table = table[
            table["panel_name"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.casefold()
            .isin(requested)
        ]

    rows = table.to_dict(orient="records")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_register.parent.mkdir(parents=True, exist_ok=True)

    processed_count = 0
    skipped_count = 0
    failed_count = 0
    diagnostics: list[str] = []
    output_rows: list[dict] = []

    iterable = (
        progress.track(
            rows,
            description="Preprocessing images",
            total=len(rows),
            item_description=lambda row: text_value(
                row.get("relative_path")
            ),
        )
        if progress
        else rows
    )

    for index, row in enumerate(iterable):
        panel_name = text_value(row.get("panel_name"))
        source_path = resolve_registered_image(row, config)

        if source_path is None:
            failed_count += 1
            diagnostics.append(
                "Could not resolve "
                f"{text_value(row.get('relative_path')) or text_value(row.get('global_path'))!r}"
            )
            continue

        source_global_path = text_value(row.get("global_path"))
        source_relative_path = text_value(row.get("relative_path"))
        stem = Path(
            source_global_path or source_relative_path
        ).stem or f"image_{index}"
        output_path = output_dir / f"{stem}.tiff"

        signature = preprocess_signature(
            preprocess_config,
            panel_name,
        )
        markers = markers_by_casefold.get(
            panel_name.casefold(),
            [],
        )

        if output_path.exists() and not force:
            skipped_count += 1
            shape = ""
            try:
                with tifffile.TiffFile(output_path) as tiff:
                    if tiff.series:
                        shape = str(list(tiff.series[0].shape))
            except Exception:
                shape = ""

            output_rows.append(
                {
                    "global_path": str(output_path),
                    "relative_path": source_relative_path,
                    "source_global_path": source_global_path,
                    "source_relative_path": source_relative_path,
                    "shape": shape,
                    "panel_name": panel_name,
                    "cohort_name": text_value(
                        row.get("cohort_name")
                    ),
                    "project_name": text_value(
                        row.get("project_name")
                    ),
                    "preprocessing": signature,
                    "status": "existing",
                }
            )
            continue

        try:
            image = tifffile.imread(source_path)
            processed = apply_preprocessing(
                image,
                preprocess_config.for_dataset(panel_name),
            )
            channel_names = (
                markers
                if markers and len(markers) == processed.shape[0]
                else []
            )
            compression = (
                None
                if preprocess_config.output.compression == "none"
                else preprocess_config.output.compression
            )
            tifffile.imwrite(
                output_path,
                processed,
                metadata={
                    "axes": "CYX",
                    "channel_names": channel_names,
                    "preprocessing": signature,
                    "source_image": str(source_path),
                },
                photometric="minisblack",
                planarconfig="separate",
                compression=compression,
            )
        except Exception as exc:
            failed_count += 1
            diagnostics.append(f"{source_path}: {exc}")
            continue

        processed_count += 1
        output_rows.append(
            {
                "global_path": str(output_path),
                "relative_path": source_relative_path,
                "source_global_path": source_global_path,
                "source_relative_path": source_relative_path,
                "shape": str(list(processed.shape)),
                "panel_name": panel_name,
                "cohort_name": text_value(
                    row.get("cohort_name")
                ),
                "project_name": text_value(
                    row.get("project_name")
                ),
                "preprocessing": signature,
                "status": "processed",
            }
        )

    if requested is not None:
        found = {
            str(value).strip().casefold()
            for value in table["panel_name"].dropna().astype(str)
        }
        missing = sorted(requested - found)
        if missing:
            diagnostics.append(
                "No images found for requested dataset(s): "
                f"{', '.join(missing)}"
            )

    if requested is not None and output_register.is_file():
        try:
            existing_rows = pd.read_csv(output_register)
            existing_rows = existing_rows[
                ~existing_rows["panel_name"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.casefold()
                .isin(requested)
            ].reindex(columns=PREPROCESSED_REGISTER_COLUMNS)
            output_rows = (
                existing_rows.to_dict(orient="records")
                + output_rows
            )
        except Exception:
            pass

    output_rows.sort(
        key=lambda row: (
            str(row.get("panel_name", "")).casefold(),
            str(row.get("global_path", "")).casefold(),
        )
    )
    pd.DataFrame(
        output_rows,
        columns=PREPROCESSED_REGISTER_COLUMNS,
    ).to_csv(output_register, index=False)

    report_data = {
        "run": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_register": str(source_register),
            "output_register": str(output_register),
            "output_dir": str(output_dir),
            "force": force,
        },
        "preprocessing": {
            "global": preprocess_signature(preprocess_config),
            "datasets": {
                dataset: preprocess_signature(
                    preprocess_config,
                    dataset,
                )
                for dataset in sorted(
                    preprocess_config.dataset_overrides
                )
            },
        },
        "counts": {
            "processed": processed_count,
            "skipped": skipped_count,
            "failed": failed_count,
        },
        "diagnostics": diagnostics,
    }
    report_path.write_bytes(
        tomli_w.dumps(report_data).encode("utf-8")
    )

    report_lines = [
        "",
        "IMAGE PREPROCESSING",
        f"Source register: {source_register}",
        f"Output directory: {output_dir}",
        f"Output register: {output_register}",
        f"Processed: {processed_count}",
        f"Skipped (already present): {skipped_count}",
        f"Failed: {failed_count}",
        f"Report: {report_path}",
    ]
    report_lines.extend(f"  - {message}" for message in diagnostics)

    return PreprocessResult(
        processed=processed_count,
        skipped=skipped_count,
        failed=failed_count,
        output_dir=output_dir,
        output_register=output_register,
        report_path=report_path,
        report="\n".join(report_lines),
    )
