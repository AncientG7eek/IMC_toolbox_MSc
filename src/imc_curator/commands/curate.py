from pathlib import Path
import typer

from imc_curator.config import get_projects_dir
from imc_curator.commands_code.curation.standardize import (
    load_marker_mapping,
    load_clinical_mapping,
)
from imc_curator.commands_code.curation.input_loader import (
    load_extracted_markers,
    load_extracted_clinical,
)
from imc_curator.commands_code.curation.manifest_writer import (
    write_curation_manifests,
)


def curate(
    name: str = typer.Argument(
        ...,
        help="Name of the cohort project to curate.",
    ),
) -> None:
    """Suggest mappings and generate editable curation manifests."""

    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    markers = load_marker_mapping()
    clinical = load_clinical_mapping()

    marker_input = load_extracted_markers(
        project_name=name,
        marker_mapping=markers,
    )

    clinical_path = (
        project_dir
        / "curation_manifests"
        / "extract"
        / "clinical"
        / "clinical_form_clinical_image_clinical_matches.csv"
    )

    clinical_input = load_extracted_clinical(
        clinical_path,
        clinical_mapping=clinical,
    )

    manifest_paths = write_curation_manifests(
        project_dir=project_dir,
        marker_input=marker_input,
        clinical_input=clinical_input,
    )

    typer.echo("Curation review manifests created:")
    for category, path in manifest_paths.items():
        typer.echo(f"  {category}: {path}")