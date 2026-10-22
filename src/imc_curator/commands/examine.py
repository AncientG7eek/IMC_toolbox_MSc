
from pathlib import Path

import typer

from imc_curator.commands_code.discovery.examine.ome_parser import (
    examine_ome_metadata,
)
from imc_curator.commands_code.discovery.examine.csv_parser import (
    examine_marker_and_clinical_tables,
)
from imc_curator.config import (
    get_projects_dir,
    get_manifests_dir,
    get_logs_dir,
    load_config,
)


def examine(
    name: str = typer.Argument(..., help="Name of the project to examine"),
) -> None:
    config = load_config()
    project_dir = get_projects_dir() / name

    if not project_dir.is_dir():
        raise typer.BadParameter(
            f"Project directory does not exist: {project_dir}"
        )

    images_dir = project_dir / "data" / "processed" / "images"
    logs_dir = get_logs_dir(project_dir=project_dir, config=config)
    manifests_dir = get_manifests_dir(
        project_dir=project_dir,
        config=config,
    )

    # 1. Examine OME-TIFF metadata if TIFF images exist.
    tiff_files = []
    if images_dir.is_dir():
        tiff_files = [
            path
            for path in images_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".tif", ".tiff"}
        ]

    if tiff_files:
        ome_report = examine_ome_metadata(
            input_dir=images_dir,
            output_dir=manifests_dir,
            logs_dir=logs_dir,
            rules_path=Path("configs/imc_curator_ome_parser_config.toml"),
        )
        print(ome_report)
    else:
        print(
            "OME-TIFF examination skipped: "
            f"no TIFF images found in {images_dir}"
        )

    # 2. Examine marker and clinical tables.
    csv_report = examine_marker_and_clinical_tables(project_dir)
    print(csv_report)

    # 3. Examine populated MCD files, if the parser is available.
    try:
        from imc_curator.commands_code.discovery.examine.mcd_parser import (
            examine_mcd_files,
        )
    except ImportError:
        print("MCD examination skipped: MCD parser is not available.")
    else:
        mcd_report = examine_mcd_files(
            project_dir=project_dir,
            output_dir=manifests_dir,
        )
        print(mcd_report)
