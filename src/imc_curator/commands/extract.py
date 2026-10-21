from typer import Argument

from imc_curator.config import (
    get_projects_dir,
    get_manifests_dir,
    load_config,
)
from imc_curator.commands_code.discovery.extract.marker_parser import (
    extract_marker_tables,
)
from imc_curator.commands_code.discovery.extract.clinical_parser import (
    extract_clinical_tables,
)


def extract(
    name: str = Argument(
        ...,
        help="Name of the cohort project to extract metadata from.",
    ),
) -> None:
    """
    Parse marker panels and clinical tables using the completed
    curation forms and save the extracted metadata.
    """
    config = load_config()
    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    curation_manifests_dir = get_manifests_dir(
        project_dir=project_dir,
        config=config,
    )

    extract_dir = curation_manifests_dir / "extract"

    marker_report = extract_marker_tables(
        project_dir=project_dir,
        forms_dir=curation_manifests_dir / "examine" / "markers",
        output_dir=extract_dir / "markers",
    )

    clinical_report = extract_clinical_tables(
        project_dir=project_dir,
        forms_dir=curation_manifests_dir / "examine" / "clinical",
        output_dir=extract_dir / "clinical",
    )

    print(marker_report)
    print(clinical_report)