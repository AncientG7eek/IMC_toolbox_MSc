
import logging
from pathlib import Path
from imc_curator.config import load_config, get_logs_dir

CONFIG = load_config()

def get_action_logger(
    project_dir: Path,
    action: str,
    *,
    level: int = logging.DEBUG,
) -> logging.Logger:
    """Create a logger that writes to this project's action log."""

    logs_subdir = get_logs_dir(project_dir=project_dir, config=CONFIG)
    log_dir = project_dir / logs_subdir
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
