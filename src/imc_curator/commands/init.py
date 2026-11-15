from pathlib import Path
import typer
from urllib.parse import urlparse


from imc_curator.config import get_projects_dir
from imc_curator.commands_code.discovery.init.download import download, import_local
from imc_curator.commands_code.discovery.init.project import init_project
from imc_curator.progress_bar import ProgressManager


def is_url(value: str) -> bool:
    parsed = urlparse(value)

    return parsed.scheme in {
        "http",
        "https",
    }


def init(
    source: str = typer.Option(
        ...,
        "--source",
        "-s",
        help="Dataset URL, local archive, or local directory.",
    ),
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Name of the dataset project.",
    ),
):
    """Initialize a new IMC dataset project."""

    projects_dir = get_projects_dir()

    project_dir = init_project(
        name=name,
        projects_dir=projects_dir,
    )

    source_dir = (
        project_dir
        / "data"
        / "raw"
        / "source"
    )

    local_source = Path(source).expanduser()

    with ProgressManager() as progress:
        if is_url(source):
            typer.echo(f"Downloading dataset: {source}")
            with progress.stage("Downloading dataset"):
                download(
                    url=source,
                    destination=source_dir,
                )

        elif local_source.exists():
            typer.echo(f"Importing local dataset: {local_source}")
            with progress.stage("Importing local dataset"):
                import_local(
                    source=local_source,
                    destination=source_dir,
                    progress=progress,
                )

        else:
            typer.echo(
                f"{source} is neither an URL nor an existing local path"
                " Please provide either of these.",
                err=True,
            )
            raise typer.Exit(code=1)

    typer.echo(
        f"Project initialized: {project_dir}"
    )
