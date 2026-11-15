"""Concatenate CSV/XLSX tables into a single CSV file.

Usage:
    python table_concatenator.py OUTPUT.csv INPUT [INPUT ...]

Wildcards such as ``*.csv`` are supported.
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import pandas as pd


def _expand_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()

    for pattern in patterns:
        if any(character in pattern for character in "*?["):
            matches = sorted(glob.glob(pattern, recursive=True))
        else:
            matches = [pattern]

        for match in matches:
            path = Path(match)
            if path.is_file() and path.resolve() not in seen:
                paths.append(path)
                seen.add(path.resolve())

    return paths


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, engine="openpyxl")
    raise ValueError(f"Unsupported file type: {path.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Concatenate CSV/XLSX tables into one CSV."
    )
    parser.add_argument("output", help="Output CSV path.")
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input CSV/XLSX paths or wildcard patterns.",
    )
    args = parser.parse_args()

    paths = _expand_paths(args.inputs)
    if not paths:
        print("No input files matched.")
        return 1

    frames: list[pd.DataFrame] = []
    columns: list[str] | None = None

    for path in paths:
        try:
            table = _read_table(path)
        except Exception:
            if path.suffix.lower() == ".xlsx":
                print(f"Unsuccessful xlsx to csv transfer: {path}")
            else:
                print(f"Could not read table: {path}")
            continue

        if columns is None:
            columns = list(table.columns)
            frames.append(table)
            continue

        if list(table.columns) != columns:
            print(f"Skipping table with different columns: {path}")
            continue

        frames.append(table)

    if not frames:
        print("No usable tables were read.")
        return 1

    combined = pd.concat(frames, ignore_index=True)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)

    print(f"Wrote {len(combined)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
