"""Command-line interface for Task Tracker CLI.

Parses argv (positional arguments only), loads the store, dispatches to the
pure functions in ``task_cli.tasks``, saves the store for mutating commands,
formats output, and maps errors to exit codes.

This is the ONLY module that prints. See design.md §4.3 and Blueprint §1.4, §4.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from task_cli import store, tasks
from task_cli.errors import InvalidId, TaskError

STORE_FILENAME = "tasks.json"

USAGE = """\
usage: task-cli <command> [args...]

commands:
  add <description>
  update <id> <description>
  delete <id>
  mark-in-progress <id>
  mark-done <id>
  list [todo|in-progress|done]"""

_ID_PATTERN = re.compile(r"-?[0-9]+")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class UsageError(Exception):
    """Raised for malformed invocations (unknown command, wrong arg count, flags).

    Kept separate from ``TaskError`` so the CLI can append the usage text.
    Blueprint: X-01, D-13.
    """


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that raises instead of printing and calling sys.exit(2).

    Combined with ``add_help=False`` this guarantees no ``-h``/``--help`` flag
    exists and every syntax error exits with code 1 (C-04, D-12).
    """

    def error(self, message: str) -> NoReturn:  # noqa: D102 - overrides argparse
        raise UsageError(message)


def _build_parser() -> _Parser:
    """Build the positional-only parser matching Blueprint §4."""
    parser = _Parser(prog="task-cli", add_help=False, usage=USAGE)
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("add", add_help=False)
    p.add_argument("description")

    p = sub.add_parser("update", add_help=False)
    p.add_argument("id")
    p.add_argument("description")

    for name in ("delete", "mark-in-progress", "mark-done"):
        p = sub.add_parser(name, add_help=False)
        p.add_argument("id")

    p = sub.add_parser("list", add_help=False)
    p.add_argument("status", nargs="?", default=None)

    return parser


def _parse_id(raw: str) -> int:
    """Convert a raw ID argument to ``int``.

    Only an optional ``-`` followed by ASCII digits is accepted (no spaces,
    ``+``, underscores, or decimals). Positivity is enforced by ``tasks``.

    Raises:
        InvalidId: if ``raw`` is not an integer literal.

    Blueprint: D-15, X-06.
    """
    if not _ID_PATTERN.fullmatch(raw):
        raise InvalidId(f"Invalid task ID: {raw!r} (must be a positive integer)")
    return int(raw)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_task(task: dict) -> str:
    """Render one task as a D-10 block."""
    return (
        f"[{task['id']}] {task['description']}\n"
        f"Status:  {task['status']}\n"
        f"Created: {task['createdAt']}\n"
        f"Updated: {task['updatedAt']}"
    )


def format_task_list(task_list: list[dict]) -> str:
    """Render tasks as D-10 blocks separated by a blank line, or 'No tasks found.'."""
    if not task_list:
        return "No tasks found."
    return "\n\n".join(format_task(t) for t in task_list)


# ---------------------------------------------------------------------------
# Command handlers: (store, args) -> stdout message
# ---------------------------------------------------------------------------


def _cmd_add(data: dict[str, dict], args: argparse.Namespace) -> str:
    task_id = tasks.add_task(data, args.description)
    return f"Task added successfully (ID: {task_id})"


def _cmd_update(data: dict[str, dict], args: argparse.Namespace) -> str:
    task_id = _parse_id(args.id)
    tasks.update_task(data, task_id, args.description)
    return f"Task {task_id} updated successfully."


def _cmd_delete(data: dict[str, dict], args: argparse.Namespace) -> str:
    task_id = _parse_id(args.id)
    tasks.delete_task(data, task_id)
    return f"Task {task_id} deleted successfully."


def _cmd_mark_in_progress(data: dict[str, dict], args: argparse.Namespace) -> str:
    task_id = _parse_id(args.id)
    tasks.set_status(data, task_id, tasks.STATUS_IN_PROGRESS)
    return f"Task {task_id} marked as in-progress."


def _cmd_mark_done(data: dict[str, dict], args: argparse.Namespace) -> str:
    task_id = _parse_id(args.id)
    tasks.set_status(data, task_id, tasks.STATUS_DONE)
    return f"Task {task_id} marked as done."


def _cmd_list(data: dict[str, dict], args: argparse.Namespace) -> str:
    return format_task_list(tasks.list_tasks(data, args.status))


Handler = Callable[[dict[str, dict], argparse.Namespace], str]

HANDLERS: dict[str, Handler] = {
    "add": _cmd_add,
    "update": _cmd_update,
    "delete": _cmd_delete,
    "mark-in-progress": _cmd_mark_in_progress,
    "mark-done": _cmd_mark_done,
    "list": _cmd_list,
}

MUTATING_COMMANDS: frozenset[str] = frozenset(HANDLERS) - {"list"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _store_path() -> Path:
    """Return ``tasks.json`` in the process CWD at invocation time (D-2)."""
    return Path.cwd() / STORE_FILENAME


def main(argv: list[str]) -> int:
    """Run one CLI invocation and return the process exit code.

    Flow: parse argv -> load store -> dispatch to ``tasks`` -> save store
    (mutating commands only) -> print result.

    Returns:
        0 on success (message on stdout); 1 on any usage error or
        ``TaskError`` (message on stderr). Blueprint: I-04, I-05, I-06, D-12.
    """
    try:
        args = _build_parser().parse_args(argv)
    except UsageError as exc:
        print(f"Error: {exc}\n\n{USAGE}", file=sys.stderr)
        return 1

    try:
        path = _store_path()
        data = store.load_store(path)
        message = HANDLERS[args.command](data, args)
        if args.command in MUTATING_COMMANDS:
            store.save_store(path, data)
    except TaskError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(message)
    return 0
