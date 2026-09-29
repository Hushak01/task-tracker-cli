"""Custom exception types for Task Tracker CLI.

Every user-facing error path defined in the Blueprint maps to exactly one
exception class here. See design.md §4.4 and Blueprint §5.

Hierarchy
---------
    Exception
     └── TaskError                (base for everything user-facing)
          ├── TaskNotFound        (X-07)
          ├── InvalidId           (D-15, X-06)
          ├── InvalidDescription  (D-14, X-09)
          ├── InvalidStatus       (X-08)
          ├── CorruptStore        (D-04, D-09, X-04)
          └── StoreWriteError     (X-05)
"""

from __future__ import annotations


class TaskError(Exception):
    """Base class for all user-facing Task Tracker errors.

    cli.main catches this class and converts it into:
        - a message on stderr
        - exit code 1

    Any error that should reach the user MUST be a subclass of TaskError.
    Programming errors (bugs) should NOT be wrapped in this hierarchy —
    they are caught by the top-level guard added in Phase 7 (X-12).
    """


class TaskNotFound(TaskError):
    """Raised when a user-supplied task ID is well-formed but not in the store.

    Blueprint: X-07.
    """


class InvalidId(TaskError):
    """Raised when a task ID is not a positive integer.

    The Blueprint (D-15) requires IDs to be positive integers everywhere:
    update, delete, mark-in-progress, mark-done.

    Blueprint: D-15, X-06.
    """


class InvalidDescription(TaskError):
    """Raised when a task description is missing, empty, or only whitespace.

    Blueprint: D-14 (strip before validate/store), X-09.
    """


class InvalidStatus(TaskError):
    """Raised when a status value is not one of todo / in-progress / done.

    Applies both to `mark-*` operations and to the `list <status>` filter.

    Blueprint: X-08.
    """


class CorruptStore(TaskError):
    """Raised when tasks.json exists but is not a JSON object.

    The file MUST NOT be modified when this is raised — user data is never
    destroyed (Blueprint D-04, D-09, X-04).

    Blueprint: D-04, D-09, X-04.
    """


class StoreWriteError(TaskError):
    """Raised when tasks.json cannot be written (permissions, disk full, ...).

    On this error the original file MUST be left untouched. The atomic write
    in store.save_store (D-16) guarantees this.

    Blueprint: X-05.
    """