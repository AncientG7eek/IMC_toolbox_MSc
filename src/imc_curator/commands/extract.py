from typer import Argument

from imc_curator.config import (
    get_projects_dir,
    get_manifests_dir,
    get_unpacked_images_dir,
    get_selected_images_dir,
    get_panels_dir,
    load_config,
)
from imc_curator.commands_code.discovery.extract.marker_parser import (
    extract_marker_tables,
)
from imc_curator.commands_code.discovery.extract.clinical_parser import (
    extract_clinical_tables,
)
from imc_curator.commands_code.discovery.extract.raw_tiff_extractor import (
    extract_raw_tiffs,
)
from imc_curator.commands_code.discovery.extract.subset_tiffs import (
    subset_images,
)
from imc_curator.commands_code.discovery.extract.panel_map import (
    init_panel_map,
    remap_tiff_files,
)
from imc_curator.completion import complete_datasets
from imc_curator.progress_bar import ProgressManager


def extract(
    name: str = Argument(
        ...,
        help="Name of the cohort project to extract metadata from.",
        autocompletion=complete_datasets,
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

    images_output_dir = get_unpacked_images_dir(
        project_dir=project_dir,
        config=config,
    )
    selected_images_dir = get_selected_images_dir(
        project_dir=project_dir,
        config=config,
    )

    panels_dir = get_panels_dir(
        project_dir=project_dir,
        config=config,
    )
    selected_panels_dir = panels_dir / "selected"

    examine_dir = curation_manifests_dir / "examine"
    extract_dir = curation_manifests_dir / "extract"
    panel_map_path = init_panel_map(extract_dir / "image_panel_map.csv")

    with ProgressManager() as progress:
        with progress.stage("Extracting raw IMC TIFFs"):
            raw_imc_report = extract_raw_tiffs(
                project_dir=project_dir,
                markers_dir=examine_dir / "markers",
                selected_images_dir=selected_images_dir,
                progress=progress,
            )

        with progress.stage("Extracting marker tables"):
            marker_report = extract_marker_tables(
                project_dir=project_dir,
                forms_dir=examine_dir / "markers",
                selected_panels_dir=selected_panels_dir,
                panel_map_path=panel_map_path,
                progress=progress,
            )

        with progress.stage("Subsetting image channels"):
            subset_report = subset_images(
                project_dir=project_dir,
                images_output_dir=images_output_dir,
                selected_images_dir=selected_images_dir,
                panel_map_path=panel_map_path,
                selected_panels_dir=selected_panels_dir,
                progress=progress,
            )

        remap_tiff_files(
            panel_map_path,
            images_output_dir,
            selected_images_dir,
            project_dir,
        )

        clinical_form_path = examine_dir / "clinical"

        if clinical_form_path.exists():
            with progress.stage("Extracting clinical tables"):
                clinical_report = extract_clinical_tables(
                    project_dir=project_dir,
                    forms_dir=clinical_form_path,
                    output_dir=extract_dir / "clinical",
                )
        else:
            clinical_report = (
                "Clinical extraction skipped: no clinical form found."
            )

    print(raw_imc_report)
    print(marker_report)
    print(subset_report)
    print(clinical_report)
    print(f"IMAGE PANEL MAP\n{panel_map_path.resolve()}")
