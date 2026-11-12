
from contextlib import contextmanager
from collections.abc import Generator, Iterable, Iterator
from typing import Callable, TypeVar

from rich.progress import (
    Progress,
    BarColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
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
        self.stage_progress.console.print()
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
        item_description: Callable[[T], str] | None = None,
        max_item_description_length: int = 80,
    ) -> Iterator[T]:
        """Iterate items with a temporary progress task.

        Removing the task when done avoids repeated rendering of completed
        bars when multiple tracked stages run in one command.
        """
        self.track_progress.console.print()
        task_id = self.track_progress.add_task(
            description,
            total=total,
        )

        try:
            for item in iterable:
                if item_description is not None:
                    current_item = item_description(item)

                    if len(current_item) > max_item_description_length:
                        current_item = (
                            current_item[: max_item_description_length - 1]
                            + "..."
                        )

                    self.track_progress.update(
                        task_id,
                        description=f"{description}: {current_item}",
                    )

                yield item
                self.track_progress.advance(task_id)
        finally:
            self.track_progress.remove_task(task_id)
