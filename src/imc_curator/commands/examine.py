from pathlib import Path
import typer

from imc_curator.commands_code.discovery.ome_parser import examine_ome_metadata
from imc_curator.config import get_projects_dir, get_manifests_dir, load_config


def examine(
    name: str = typer.Argument(
        ...,
        help="Name of the cohort project file of which to examine.",
    ),
) -> None:
    """
    Examines the files which were find in the raw repository 
    and approved by the user for the population of a standardised repository
    """
    config = load_config()
    projects_dir = get_projects_dir()
    project_dir = projects_dir / name
    images_dir = project_dir / "data" / "processed" / "images"
    curation_manifests_dir = get_manifests_dir(project_dir=project_dir, config=config)

    reports = examine_ome_metadata(
        input_dir=images_dir,
        output_dir=curation_manifests_dir,
        rules_path=Path("configs/imc_curator_ome_parser_config.toml")
    )

    print(f"Channel report: {reports['channels_csv']}")
    print(f"Scan report: {reports['scan_csv']}")