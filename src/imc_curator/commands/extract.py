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
from imc_curator.commands_code.discovery.extract.raw_imc_parser import (
    extract_raw_imc,
)


def extract(
    name: str = Argument(
        ...,
        help="Name of the cohort project to extract metadata from.",
    ),
) -> None:
    """
    Extract raw IMC images and panel metadata, plus marker and clinical tables.
    """
    config = load_config()
    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    if not project_dir.is_dir():
        raise ValueError(f"Project directory does not exist: {project_dir}")

    curation_manifests_dir = get_manifests_dir(
        project_dir=project_dir,
        config=config,
    )

    examine_dir = curation_manifests_dir / "examine"
    extract_dir = curation_manifests_dir / "extract"

    raw_imc_report = extract_raw_imc(
        project_dir=project_dir,
        form_path=examine_dir / "mcd_channel_form.toml",
        output_dir=extract_dir / "raw_imc",
    )

    marker_report = extract_marker_tables(
        project_dir=project_dir,
        forms_dir=examine_dir / "markers",
        output_dir=extract_dir / "markers",
    )

    clinical_form_path = examine_dir / "clinical" / "clinical_form.toml"

    if clinical_form_path.exists():
        clinical_report = extract_clinical_tables(
            project_dir=project_dir,
            forms_dir=examine_dir / "clinical",
            output_dir=extract_dir / "clinical",
        )
    else:
        clinical_report = (
            "Clinical extraction skipped: no clinical form found."
        )

    print(raw_imc_report)
    print(marker_report)
    print(clinical_report)