# Curation workflow

## Overview

IMC Curator separates dataset discovery from dataset curation.

The workflow consists of five stages:

1. Initialize
2. Inspect
3. Review
4. Validate
5. Curate

## 1. Initialize

`init` creates a project and downloads the raw dataset.

    imc-curator init \
        --url <URL> \
        --name <NAME>

No assumptions about the contents of the dataset are made at this stage.

## 2. Inspect

`inspect` examines the downloaded dataset.

    imc-curator inspect IMMUcan

The inspection process identifies candidate:

- image files
- marker metadata
- clinical data
- sample metadata

The result is written to `manifest.toml`.

## 3. Review

Automatic discovery is intentionally treated as a suggestion.

The user must review the generated manifest.

This is important because file names and directory structures vary
between IMC datasets.

## 4. Validate

The manifest is checked against the actual files.

    imc-curator validate IMMUcan

Validation should fail if required inputs are missing or malformed.

## 5. Curate

Once validation succeeds:

    imc-curator curate IMMUcan

The dataset-specific curation pipeline is executed.