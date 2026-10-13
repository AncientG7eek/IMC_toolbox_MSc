
import logging
from pathlib import Path


def get_action_logger(
    project_dir: Path,
    action: str,
    *,
    level: int = logging.DEBUG,
) -> logging.Logger:
    """Create a logger that writes to this project's action log."""

    log_dir = project_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"imc_curator.{action}")
    logger.setLevel(level)
    logger.propagate = False

    # Avoid adding duplicate handlers if this logger is reused.
    log_path = (log_dir / f"{action}.log").resolve()

    for handler in logger.handlers[:]:
        if (
            isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename).resolve() == log_path
        ):
            return logger

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
    )
    logger.addHandler(handler)

    return logger
