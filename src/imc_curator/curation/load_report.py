from pathlib import Path
import tomllib


def load_manifest(project_dir: Path) -> dict:
    """Load a project's manifest.toml."""

    manifest_path = project_dir / "manifest.toml"

    if not manifest_path.exists():
        raise RuntimeError(
            f"Manifest not found: {manifest_path}"
        )

    with manifest_path.open("rb") as f:
        return tomllib.load(f)