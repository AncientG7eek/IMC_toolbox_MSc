import typer

from imc_curator.commands_code.adapt.base import ModelConfig
from imc_curator.commands_code.adapt.immuvis import ImmuvisConfig
from imc_curator.completion import complete_models


MODEL_CONFIGS: dict[str, ModelConfig] = {
    ImmuvisConfig.model_name: ImmuvisConfig(),
}


def adapt(
    model: str = typer.Argument(
        ...,
        help="Name of the ML model to adapt the global files for.",
        autocompletion=complete_models,
    ),
) -> None:
    """Generate model-specific config files from global marker tables."""
    model_key = model.strip().casefold()
    config_instance = MODEL_CONFIGS.get(model_key)

    if config_instance is None:
        raise typer.BadParameter(
            f"No adapt module available for model: {model}"
        )

    typer.echo(config_instance.adapt())
