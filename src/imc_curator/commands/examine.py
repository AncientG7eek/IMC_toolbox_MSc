from pathlib import Path
import typer

from imc_curator.commands_code.discovery.examine.ome_parser import examine_ome_metadata
from imc_curator.commands_code.discovery.examine.csv_parser import examine_marker_and_clinical_tables
from imc_curator.config import get_projects_dir, get_manifests_dir, load_config, get_logs_dir


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
    logs_dir = get_logs_dir(project_dir=project_dir, config=config)
    curation_manifests_dir = get_manifests_dir(project_dir=project_dir, config=config)

    ome_report = examine_ome_metadata(
        input_dir=images_dir,
        output_dir=curation_manifests_dir,
        logs_dir=logs_dir,
        rules_path=Path("configs/imc_curator_ome_parser_config.toml")
    )

    csv_report = examine_marker_and_clinical_tables(project_dir)

    print(ome_report)
    print(csv_report)