"""Domain business logic for Task Tracker CLI.

Pure in-memory operations on the store (``dict[str, dict]`` keyed by string ID).
This module never touches the filesystem, never prints, and never parses argv.
All invalid input is reported by raising exceptions from ``task_cli.errors``.

See design.md §4.2 and Blueprint §2, §4, §5.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from task_cli.errors import (
    InvalidDescription,
    InvalidId,
    InvalidStatus,
    TaskNotFound,
)

STATUS_TODO = "todo"
STATUS_IN_PROGRESS = "in-progress"
STATUS_DONE = "done"

VALID_STATUSES: frozenset[str] = frozenset({STATUS_TODO, STATUS_IN_PROGRESS, STATUS_DONE})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    """Return the current local time as an ISO 8601 string (seconds, no TZ).

    Blueprint: D-8.
    """
    return datetime.now().isoformat(timespec="seconds")


def _validate_id(task_id: Any) -> int:
    """Ensure ``task_id`` is a positive integer and return it.

    Booleans are rejected even though ``bool`` subclasses ``int``.

    Raises:
        InvalidId: if ``task_id`` is not an ``int`` (or is a ``bool``) or is <= 0.

    Blueprint: D-15, X-06.
    """
    if isinstance(task_id, bool) or not isinstance(task_id, int):
        raise InvalidId(f"Invalid task ID: {task_id!r} (must be a positive integer)")
    if task_id <= 0:
        raise InvalidId(f"Invalid task ID: {task_id} (must be a positive integer)")
    return task_id


def _validate_description(description: Any) -> str:
    """Strip ``description`` and ensure it is non-empty; return the stripped value.

    Raises:
        InvalidDescription: if ``description`` is not a ``str`` or is empty /
            whitespace-only after ``.strip()``.

    Blueprint: D-14, X-09.
    """
    if not isinstance(description, str):
        raise InvalidDescription("Task description must be a string")
    stripped = description.strip()
    if not stripped:
        raise InvalidDescription("Task description cannot be empty")
    return stripped


def _validate_status(status: Any) -> str:
    """Ensure ``status`` is one of ``todo``, ``in-progress``, ``done``; return it.

    Raises:
        InvalidStatus: if ``status`` is not one of the allowed values.

    Blueprint: X-08.
    """
    if not isinstance(status, str) or status not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        raise InvalidStatus(f"Invalid status: {status!r} (must be one of: {allowed})")
    return status


def _get_task(store: dict[str, dict], task_id: int) -> dict:
    """Return the task with ``task_id`` from ``store``.

    Assumes ``task_id`` has already been validated.

    Raises:
        TaskNotFound: if no task with that ID exists.

    Blueprint: X-07.
    """
    task = store.get(str(task_id))
    if task is None:
        raise TaskNotFound(f"Task {task_id} not found")
    return task


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------


def add_task(store: dict[str, dict], description: str) -> int:
    """Create a new ``todo`` task in ``store`` and return its ID.

    ID = ``max(existing int IDs, default=0) + 1``. ``createdAt`` and
    ``updatedAt`` are both set to the same current timestamp. The description
    is stored stripped.

    Raises:
        InvalidDescription: if the description is empty or whitespace-only.

    Blueprint: F-01, D-03, D-7, D-8, D-14, §4.1.
    """
    clean_description = _validate_description(description)
    task_id = max([int(k) for k in store.keys()], default=0) + 1
    timestamp = _now()
    store[str(task_id)] = {
        "id": task_id,
        "description": clean_description,
        "status": STATUS_TODO,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    return task_id


def update_task(store: dict[str, dict], task_id: int, description: str) -> None:
    """Replace the description of an existing task and refresh ``updatedAt``.

    ``createdAt`` is never modified. All inputs are validated before the
    store is touched, so the store is unchanged if any exception is raised.

    Raises:
        InvalidId: if ``task_id`` is not a positive integer.
        InvalidDescription: if the description is empty or whitespace-only.
        TaskNotFound: if no task with ``task_id`` exists.

    Blueprint: F-02, D-05, D-06, §4.2.
    """
    valid_id = _validate_id(task_id)
    clean_description = _validate_description(description)
    task = _get_task(store, valid_id)
    task["description"] = clean_description
    task["updatedAt"] = _now()


def delete_task(store: dict[str, dict], task_id: int) -> None:
    """Remove an existing task from ``store``.

    Raises:
        InvalidId: if ``task_id`` is not a positive integer.
        TaskNotFound: if no task with ``task_id`` exists.

    Blueprint: F-03, §4.3.
    """
    valid_id = _validate_id(task_id)
    _get_task(store, valid_id)
    del store[str(valid_id)]


def set_status(store: dict[str, dict], task_id: int, status: str) -> None:
    """Set the status of an existing task and refresh ``updatedAt``.

    ``updatedAt`` is refreshed on every successful call (D-06), even when the
    new status equals the current one. ``createdAt`` is never modified.

    Raises:
        InvalidId: if ``task_id`` is not a positive integer.
        InvalidStatus: if ``status`` is not ``todo``, ``in-progress`` or ``done``.
        TaskNotFound: if no task with ``task_id`` exists.

    Blueprint: F-04, F-05, D-05, D-06, §4.4, §4.5.
    """
    valid_id = _validate_id(task_id)
    valid_status = _validate_status(status)
    task = _get_task(store, valid_id)
    task["status"] = valid_status
    task["updatedAt"] = _now()


def list_tasks(store: dict[str, dict], status: str | None = None) -> list[dict]:
    """Return tasks from ``store``, optionally filtered by ``status``.

    Results are ordered by ascending numeric ID and are shallow copies, so
    callers cannot accidentally mutate the store through them. The store
    itself is never modified.

    Raises:
        InvalidStatus: if ``status`` is given and is not a valid status.

    Blueprint: F-06, F-07, §4.6.
    """
    if status is not None:
        _validate_status(status)
    ordered = sorted(store.items(), key=lambda item: int(item[0]))
    return [
        dict(task)
        for _, task in ordered
        if status is None or task.get("status") == status
    ]
