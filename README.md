# IMC Curator

A Python package for turning raw Imaging Mass Cytometry (IMC) datasets into
standardized, analysis-ready projects.

`imc-curator` covers the full curation workflow: importing a dataset,
inspecting it, generating review forms, extracting selected images and
tables, curating marker/clinical mappings, and finalizing shared global
reference files.

## Installation

From PyPI (once published):

```bash
pip install imc-curator
```

From a source checkout:

```bash
git clone <repository-url>
cd IMC_toolbox_MSc
pip install .
```

For development, install in editable mode:

```bash
pip install -e ".[dev]"
```

Check the installation:

```bash
imc-curator --version
imc-curator --help
```

Python 3.11 or newer is required.

## Configuration

`imc-curator` reads three TOML files:

- `imc_curator_config.toml` — workspace, project, and curated-database paths
- `imc_curator_search_config.toml` — file discovery and classification rules
- `imc_curator_ome_parser_config.toml` — channel-name parsing rules

Configuration is resolved in this order:

1. `IMC_CURATOR_CONFIG_DIR` environment variable.
2. The repository `configs/` directory (source/editable installs).
3. Portable defaults shipped inside the package.

The installed defaults use a self-contained workspace: running
`imc-curator` creates `./projects` and `./curated_database` in the current
directory. Relative paths are resolved against `workspace_dir` in the main
config (default `.`).

Individual paths can be redirected without editing the config:

```bash
export IMC_CURATOR_WORKSPACE=/data/imc
export IMC_CURATOR_PROJECTS_DIR=/data/imc/projects
export IMC_CURATOR_CURATED_DATABASE_DIR=/data/imc/curated_database
```

Existing workspaces that still use `global_files/`, the
`global_files_dir` config key, or `IMC_CURATOR_GLOBAL_FILES_DIR` keep
working through deprecated aliases. New configurations should use the
`curated_database` names.

If you rename an existing folder, update stored `global_path` values in
`global_register_of_images.csv` and `global_image_clinical.csv` from
`.../global_files/...` to `.../curated_database/...`.

## Workflow

```bash
imc-curator init --source <url-or-path> --name <project>
imc-curator inspect <project>
imc-curator populate <project>
imc-curator examine <project>
imc-curator extract <project>
imc-curator curate <project>
imc-curator finalize <project>
imc-curator preprocess
```

After at least one project has been finalized, model-specific configuration
can be generated:

```bash
imc-curator adapt immuvis
imc-curator generate \
    --cohort my_cohort \
    --feature Indication \
    --value CRC \
    --output experiment.csv
```

### Preprocessing the curated image database

Preprocessing is configured once for the whole curated image database:

```text
<curated_database>/preprocessing.toml
```

The first `preprocess` run creates this file with ImmuVis defaults. The
global `[preprocessing]` and `[denoising]` settings apply to every panel.
Optional `[datasets.<panel>]` tables override individual fields for one
panel while inheriting everything else.

```toml
[preprocessing]
method = "arcsinh"          # arcsinh | log1p | none
arcsinh_scale = 5.0

[denoising]
method = "butterworth"      # butterworth | median | gaussian | none
butterworth_cutoff = 0.2
butterworth_high_pass = false

[output]
directory = "preprocessed"
register_file = "global_register_of_preprocessed_images.csv"
compression = "zlib"        # zlib | lzw | deflate | none
```

Run it with:

```bash
imc-curator preprocess
imc-curator preprocess --dataset panelA --dataset panelB
imc-curator preprocess --force
imc-curator preprocess --config path/to/preprocessing.toml
```

The command writes float32 `CYX` TIFFs to
`<curated_database>/preprocessed/`, plus
`global_register_of_preprocessed_images.csv` with source paths, panel
names, preprocessing signatures, and per-image status. A
`preprocess_report.toml` records the configuration and run counts.
Existing outputs are skipped unless `--force` is passed.

ImmuVis applies its own preprocessing by default. If you train on these
preprocessed images, set `preprocessing_func: null` and
`denoising_func: null` in the training config to avoid applying the
pipeline twice.

### ImmuVis preprocessing and clip limits

`imc-curator adapt immuvis` reads the same `preprocessing.toml` (or uses
ImmuVis defaults if it does not exist), applies that pipeline to the
curated images referenced by `global_register_of_images.csv`, and
estimates clip limits:

```text
arcsinh(x / 5) -> Butterworth low-pass filter (cutoff 0.2)
```

It then estimates each panel's clip limit as the 99th percentile of the
preprocessed pixels and writes those values into `clip_limits` in
`all_panels_config.yaml`. To keep adaptation fast, at most 8 images per
panel and 50,000 pixels per image are sampled, with a 2,000,000-pixel
cap per panel. Panels with no curated images fall back to 5.0.

The reusable preprocessing and statistics functions live in
`imc_curator.services.processing`. `marker_stats` is still emitted as a
configured filename; per-marker z-score statistics are not computed yet.

To remove a project and its data folder:

```bash
imc-curator delete-dataset <project>
```

Run `imc-curator <command> --help` for command-specific options.

## Development and tests

```bash
pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -v
```

The test suite uses small fixtures for MCD, both OME-TIFF layouts, and
CSV/XLSX marker and clinical tables.

## License

License to be chosen by the author before publishing to PyPI.
