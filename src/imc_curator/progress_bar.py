
from contextlib import contextmanager
from collections.abc import Generator, Iterable
from typing import TypeVar

from rich.progress import (
    Progress,
    BarColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

T = TypeVar("T")


class ProgressManager:
    """Reusable progress display for IMC Curator commands."""

    def __init__(self) -> None:
        # For operations without a known total.
        self.stage_progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        )

        # For operations with a known number of items.
        self.track_progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )

    def __enter__(self):
        self.stage_progress.start()
        self.track_progress.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.track_progress.stop()
        self.stage_progress.stop()

    @contextmanager
    def stage(self, description: str) -> Generator[None, None, None]:
        """Display an activity using a spinner."""
        task_id = self.stage_progress.add_task(description, total=None)

        try:
            yield
        finally:
            self.stage_progress.remove_task(task_id)

    def track(
        self,
        iterable: Iterable[T],
        description: str,
        total: int | None = None,
    ) -> Iterable[T]:
        """Iterate over items while displaying a progress bar."""
        return self.track_progress.track(
            iterable,
            description=description,
            total=total,
        )
