
import typer

from imc_curator.config import get_projects_dir
from imc_curator.commands_code.curation.curate.standardize import (
    load_marker_mapping,
    load_clinical_mapping,
)
from imc_curator.commands_code.curation.curate.input_loader import (
    load_extracted_markers,
    load_extracted_clinical,
)
from imc_curator.commands_code.curation.curate.manifest_writer import (
    write_curation_manifests,
)
from imc_curator.completion import complete_datasets


def curate(
    name: str = typer.Argument(
        ...,
        help="Name of the cohort project to curate.",
        autocompletion=complete_datasets,
    ),
) -> None:
    """Suggest mappings and generate editable curation manifests."""
    project_dir = get_projects_dir() / name

    if not project_dir.is_dir():
        raise typer.BadParameter(
            f"Project directory does not exist: {project_dir}"
        )

    extract_dir = project_dir / "curation_manifests" / "extract"
    marker_dir = extract_dir / "markers"
    clinical_dir = extract_dir / "clinical"

    if not marker_dir.is_dir():
        raise typer.BadParameter(
            f"Marker extraction directory does not exist: {marker_dir}. "
            "Run extraction first."
        )

    marker_files = sorted(marker_dir.glob("*_parsed.csv"))
    if not marker_files:
        raise typer.BadParameter(
            f"No parsed marker tables found in {marker_dir}. "
            "Run extraction first."
        )

    clinical_files = (
        sorted(clinical_dir.glob("*_image_clinical_matches.csv"))
        if clinical_dir.is_dir()
        else []
    )

    marker_mapping = load_marker_mapping()
    clinical_mapping = load_clinical_mapping()

    marker_inputs = load_extracted_markers(
        project_name=name,
        marker_mapping=marker_mapping,
    )

    clinical_inputs = [
        load_extracted_clinical(
            path=path,
            clinical_mapping=clinical_mapping,
        )
        for path in clinical_files
    ]

    manifest_paths = write_curation_manifests(
        project_dir=project_dir,
        marker_input=marker_inputs,
        clinical_input=clinical_inputs,
    )

    typer.echo("Curation review manifests created:")

    for category, paths in manifest_paths.items():
        if not paths:
            typer.echo(f"  {category}: none")
            continue

        for path in paths:
            typer.echo(f"  {category}: {path}")

    typer.echo(
        f"Loaded {len(marker_inputs)} marker table(s) and "
        f"{len(clinical_inputs)} clinical table(s)."
    )
