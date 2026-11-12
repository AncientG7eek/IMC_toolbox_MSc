
from pathlib import Path
import typer

from imc_curator.commands_code.discovery.examine.ome_parser import (
    examine_ome_metadata,
)
from imc_curator.commands_code.discovery.examine.csv_parser import (
    examine_marker_and_clinical_tables,
)
from imc_curator.commands_code.discovery.examine.mcd_parser import (
    examine_mcd_files
)
from imc_curator.config import (
    get_projects_dir,
    get_manifests_dir,
    get_category_config,
    get_logs_dir,
    load_config,
)
from imc_curator.completion import complete_datasets
from imc_curator.progress_bar import ProgressManager


def examine(
    name: str = typer.Argument(
        ..., 
        help="Name of the project to examine",
        autocompletion=complete_datasets,
    ),
) -> None:

    config = load_config()
    project_dir = get_projects_dir() / name
    logs_dir = get_logs_dir(project_dir=project_dir, config=config)

    if not project_dir.is_dir():
        raise typer.BadParameter(
            f"Project directory does not exist: {project_dir}"
        )

    manifests_dir = get_manifests_dir(
        project_dir=project_dir,
        config=config,
    )
    output_dir = manifests_dir / "examine"

    # 1. Examine OME-TIFF metadata if TIFF images exist.
    images_config = get_category_config("images")
    images_dir = project_dir / images_config["destination"]

    if images_dir.is_dir():
        tiff_files = [
            path
            for path in images_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in images_config["extensions"]
        ]
    else:
        tiff_files = []

    with ProgressManager() as progress:

        if tiff_files:
            ome_report = examine_ome_metadata(
                input_dir=images_dir,
                output_dir=output_dir,
                logs_dir=logs_dir,
                project_dir=project_dir,
                markers_output_dir=output_dir / "markers",
                progress=progress,
            )
            typer.echo(ome_report)
        else:
            print(
                "OME-TIFF examination skipped: "
                f"no TIFF images found in {images_dir}"
            )

        # 2. Examine populated MCD files, if the parser is available.
        mcd_report = examine_mcd_files(
            project_dir=project_dir,
            output_dir=output_dir,
            markers_output_dir=output_dir / "markers",
            logs_dir=logs_dir,
            progress=progress,
        )
        typer.echo(mcd_report)

        # 3. Examine marker and clinical tables.
        with progress.stage("Examining marker and clinical tables"):
            csv_report = examine_marker_and_clinical_tables(
                project_dir,
                output_dir=output_dir,
            )
        typer.echo(csv_report)
