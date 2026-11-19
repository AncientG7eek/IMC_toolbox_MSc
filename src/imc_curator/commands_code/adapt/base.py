"""Base interface for model-specific adaptation."""

from __future__ import annotations


class ModelConfig:
    """A model adapter contract.

    Subclasses implement ``adapt`` and may expose model-specific options.
    """

    model_name: str = ""

    def adapt(self) -> str:
        raise NotImplementedError
