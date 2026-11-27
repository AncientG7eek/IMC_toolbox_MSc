from __future__ import annotations

from pathlib import Path

from imc_curator.services.curation.finalize.common import read_csv


def split_register_rows(
    rows: list[dict[str, str]],
    train_ratio: float = 0.8,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split register rows into train and test sets."""
    train_count = int(len(rows) * train_ratio)
    return rows[:train_count], rows[train_count:]


def update_global_image_split(
    split_dir: Path,
    all_images_dir: Path,
    register_path: Path,
) -> None:
    """Create train/test symlink folders that mirror all_images ordinals."""
    _, rows = read_csv(register_path)
    train_rows, test_rows = split_register_rows(rows)

    for subset, subset_rows in (
        ("train", train_rows),
        ("test", test_rows),
    ):
        for row in subset_rows:
            panel_name = row.get("panel_name", "").strip() or "unassigned"
            global_name = Path(
                row.get("global_path", "").strip()
            ).name
            if not global_name:
                continue

            source_symlink = all_images_dir / global_name
            if not source_symlink.is_symlink():
                continue

            destination = (
                split_dir / subset / panel_name / global_name
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink() or destination.exists():
                destination.unlink()
            destination.symlink_to(source_symlink.resolve())
