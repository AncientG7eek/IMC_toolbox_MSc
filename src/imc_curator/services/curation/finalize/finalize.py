import shutil
import typer

from imc_curator.config import (
    get_curated_file_path,
    get_curated_subdir,
    get_projects_dir,
    get_raw_source_dir,
    load_config,
)
from imc_curator.services.curation.finalize.clinical_globals import (
    add_paths_to_image_clinical,
    update_global_clinical_values,
    update_global_image_clinical,
)
from imc_curator.services.curation.finalize.common import (
    CLINICAL_MANIFEST_SUFFIX,
    MARKER_MANIFEST_SUFFIX,
    check_approval,
    discover_manifests,
    read_csv,
)
from imc_curator.services.curation.finalize.image_registry import (
    update_global_image_register,
)
from imc_curator.services.curation.finalize.image_split import (
    update_global_image_split,
)
from imc_curator.services.curation.finalize.mapping import (
    _validate_final_mappings,
)
from imc_curator.services.curation.finalize.marker_globals import (
    update_global_marker_channels,
    update_global_marker_names,
)


def finalizer(
    name: str = typer.Argument(
        ...,
        help="Name of the cohort project to finalize.",
    ),
) -> None:
    """Validate all curation manifests and update the curated database."""
    config = load_config()
    project_dir = get_projects_dir() / name
    curate_dir = project_dir / "curation_manifests" / "curate"

    if not project_dir.is_dir():
        raise FileNotFoundError(
            f"Project directory not found: {project_dir}"
        )

    marker_manifests_dir = curate_dir / "markers"
    clinical_manifests_dir = curate_dir / "clinical"
    marker_manifests = discover_manifests(
        marker_manifests_dir,
        MARKER_MANIFEST_SUFFIX,
    )
    clinical_manifests = discover_manifests(
        clinical_manifests_dir,
        CLINICAL_MANIFEST_SUFFIX,
    )

    if not marker_manifests:
        raise FileNotFoundError(
            f"No marker review manifests found under {curate_dir}"
        )

    marker_sources = [
        (path, read_csv(path)[1])
        for path in marker_manifests
    ]
    clinical_sources = [
        (path, read_csv(path)[1])
        for path in clinical_manifests
    ]

    problems = check_approval(marker_manifests + clinical_manifests)
    proceed = False

    if problems:
        typer.echo("These manifests still contain unapproved rows:")
        for problem in problems:
            typer.echo(f"- {problem}")
        answer = typer.prompt(
            'To continue with suggestions without approval, type "proceed"',
            default="",
            show_default=False,
        )
        if answer.strip().lower() != "proceed":
            typer.echo("Finalization cancelled.")
            raise typer.Exit(code=1)
        proceed = True

    _validate_final_mappings(marker_sources, clinical_sources, proceed)

    marker_names_path = get_curated_file_path(
        config,
        "global_marker_names_file",
    )
    marker_channels_path = get_curated_file_path(
        config,
        "global_marker_channels_file",
    )
    clinical_values_path = get_curated_file_path(
        config,
        "global_clinical_values_file",
    )
    image_clinical_path = get_curated_file_path(
        config,
        "global_image_clinical_file",
    )
    image_register_path = get_curated_file_path(
        config,
        "global_image_register_file",
    )
    all_images_dir = get_curated_subdir(
        config,
        "global_images_subdir",
    )
    curated_split_dir = get_curated_subdir(
        config,
        "global_split_subdir",
    )
    relative_images_dir = config["curation"]["relative_images_dir"]

    selected_images_dir = (
        project_dir
        / config["project_file_system"]["selected_images_dir"]
    )
    panel_map_path = (
        project_dir
        / "curation_manifests"
        / "extract"
        / "image_panel_map.csv"
    )

    clinical_match_files = sorted(
        (
            project_dir
            / "metadata"
            / "clinical"
            / "selected"
        ).glob("*_image_clinical_matches.csv")
    )
    extracted_marker_files = sorted(
        (
            project_dir
            / "metadata"
            / "markers"
            / "selected"
        ).glob("*.csv")
    )

    all_marker_rows = [
        row
        for _, rows in marker_sources
        for row in rows
    ]
    all_clinical_rows = [
        row
        for _, rows in clinical_sources
        for row in rows
    ]

    update_global_marker_names(marker_names_path, all_marker_rows)
    update_global_clinical_values(
        clinical_values_path,
        all_clinical_rows,
        cohort=name,
        proceed=proceed,
    )
    update_global_image_clinical(
        image_clinical_path,
        clinical_match_files,
        clinical_sources,
        project_name=name,
        relative_images_dir=relative_images_dir,
        proceed=proceed,
    )
    update_global_image_register(
        image_register_path,
        all_images_dir,
        project_dir,
        selected_images_dir,
        panel_map_path,
        image_clinical_path,
        project_name=name,
        relative_images_dir=relative_images_dir,
    )
    add_paths_to_image_clinical(
        image_clinical_path,
        image_register_path,
    )
    update_global_image_split(
        curated_split_dir,
        all_images_dir,
        image_register_path,
    )
    update_global_marker_channels(
        marker_channels_path,
        marker_names_path,
        extracted_marker_files,
        marker_sources,
    )

    answer = typer.prompt(
        "The final image files are under data/raw/selected. Files in "
        "data/raw/source and data/raw/unpacked are redundant at this "
        "point. Do you want to delete them? YES/no",
        default="no",
        show_default=False,
    )
    if answer.strip().lower() in {"yes", "y"}:
        unpacked_dir = (
            project_dir
            / config["project_file_system"]["unpacked_images_dir"]
        )
        source_dir = get_raw_source_dir(
            project_dir=project_dir,
            config=config,
        )
        for directory in (source_dir, unpacked_dir):
            if directory.is_dir():
                shutil.rmtree(directory)
                typer.echo(f"Deleted {directory}")

    typer.echo(f"Finalization completed for project: {name}")
    typer.echo(f"Marker manifests processed: {len(marker_manifests)}")
    typer.echo(f"Clinical manifests processed: {len(clinical_manifests)}")
    typer.echo(
        f"Marker tables processed: {len(extracted_marker_files)}"
    )
