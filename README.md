# IMC_toolbox_MSc
A Computational Toolbox for Large-Scale IMC Data and Feature Analysis + finetuning of the Immuvis model


# IMC Curator

A toolkit for discovering, validating, and curating Imaging Mass Cytometry
(IMC) datasets into a standardized project structure.

## Overview

`imc-curator` helps organize the process of turning a raw IMC dataset into
a structured dataset ready for downstream analysis.

The workflow is:

    Raw dataset
        ↓
    Initialize project
        ↓
    Inspect dataset
        ↓
    Review manifest
        ↓
    Validate inputs
        ↓
    Curate
        ↓
    Standardized dataset

## Installation

Clone the repository:

    git clone <repository-url>
    cd IMC_toolbox_MSc

Create an environment:

    python -m venv .venv
    source .venv/bin/activate

Install the package in editable mode:

    pip install -e .

Check the CLI:

    imc-curator --help

## Configuration

The location of cohort projects is defined in:

    configs/config.toml

For example:

    projects_dir = "cohorts/"

Relative paths are resolved relative to the repository root.

## Basic usage

### 1. Initialize a project

    imc-curator init \
        --url https://example.com/dataset.zip \
        --name IMMUcan

This creates:

    cohorts/
    └── IMMUcan/
        ├── data/
        │   └── raw/
        ├── metadata/
        └── output/

and downloads the dataset archive into `data/raw/`.

### 2. Inspect the dataset

    imc-curator inspect IMMUcan

The inspection step searches the downloaded dataset and suggests:

- image files
- marker metadata
- clinical information
- sample metadata
- unclassified files

It creates:

    cohorts/IMMUcan/manifest.toml

### 3. Review the manifest

Open:

    cohorts/IMMUcan/manifest.toml

and check or modify the suggested paths.

The manifest is the authoritative description of the input data used
for curation.

### 4. Validate

    imc-curator validate IMMUcan

Validation checks that the files specified in the manifest exist and
contain the expected information.

### 5. Curate

    imc-curator curate IMMUcan

This runs the dataset-specific curation pipeline.

## Project structure

A curated project has the following structure:

    cohorts/
    └── IMMUcan/
        ├── data/
        │   ├── raw/
        │   └── processed/
        ├── metadata/
        ├── output/
        └── manifest.toml

## CLI commands

    imc-curator init
    imc-curator inspect
    imc-curator validate
    imc-curator curate

Run:

    imc-curator <command> --help

for command-specific documentation.

## Development

Install the package in editable mode:

    pip install -e .

Run tests:

    pytest

Source code is located in:

    src/imc_curator/

# IMC statistics
tbd

# IMMUVIS model finetuning
tbd

## License

...