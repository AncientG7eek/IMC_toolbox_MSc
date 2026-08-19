from pathlib import Path


def create_project(
    name: str,
    path: Path | str = ".",
) -> Path:

    path = Path(path)
    project_dir = path / name

    project_dir.mkdir(parents=True, exist_ok=False)

    for directory in [
        "data/raw",
        "data/processed",
        "metadata",
        "output",
    ]:
        (project_dir / directory).mkdir(parents=True)

    config = project_dir / "imc-curator.yaml"
    config.write_text(
        f"name: {name}\n"
    )

    return project_dir