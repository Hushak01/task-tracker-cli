"""End-to-end integration tests for the Task Tracker CLI (Component 4).

Every test runs ``python -m task_cli`` in a real subprocess with its CWD set
to a pytest ``tmp_path``, so the real ``tasks.json`` is never touched.

Covers Blueprint §4 (command contracts) and §5 (X-01 … X-11).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STORE_NAME = "tasks.json"
ISO_SECONDS = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
OLD_TS = "2020-01-01T00:00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``python -m task_cli <args>`` in ``cwd`` and capture text output."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "task_cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def read_store(cwd: Path) -> dict[str, Any]:
    """Parse ``tasks.json`` in ``cwd``."""
    return json.loads((cwd / STORE_NAME).read_text(encoding="utf-8"))


def write_store(cwd: Path, data: Any) -> None:
    """Seed ``tasks.json`` in ``cwd`` with ``data``."""
    (cwd / STORE_NAME).write_text(json.dumps(data), encoding="utf-8")


def seed_task(task_id: int, description: str = "seeded", status: str = "todo") -> dict:
    """Build a task record with old, fixed timestamps."""
    return {
        "id": task_id,
        "description": description,
        "status": status,
        "createdAt": OLD_TS,
        "updatedAt": OLD_TS,
    }


def assert_ok(result: subprocess.CompletedProcess[str], stdout: str | None = None) -> None:
    """Exit 0, empty stderr, and (optionally) exact stdout."""
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    if stdout is not None:
        assert result.stdout == stdout


def assert_error(result: subprocess.CompletedProcess[str], *fragments: str) -> None:
    """Exit 1, empty stdout, clean stderr containing every fragment (X-11, X-12)."""
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("Error: ")
    assert "Traceback" not in result.stderr
    for fragment in fragments:
        assert fragment in result.stderr, result.stderr


def assert_usage_error(result: subprocess.CompletedProcess[str], *fragments: str) -> None:
    """Usage errors additionally print the usage text (X-01, D-13)."""
    assert_error(result, "usage: task-cli", *fragments)


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    """Isolated working directory per test."""
    return tmp_path


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


def test_full_lifecycle(cwd: Path) -> None:
    """add → list → update → list filtered → mark-in-progress → mark-done → delete."""
    assert_ok(run_cli(cwd, "add", "Buy groceries"), "Task added successfully (ID: 1)\n")
    assert_ok(run_cli(cwd, "add", "Write report"), "Task added successfully (ID: 2)\n")

    listed = run_cli(cwd, "list")
    assert_ok(listed)
    assert "[1] Buy groceries\n" in listed.stdout
    assert "[2] Write report\n" in listed.stdout

    assert_ok(
        run_cli(cwd, "update", "1", "Buy groceries and cook dinner"),
        "Task 1 updated successfully.\n",
    )
    todo = run_cli(cwd, "list", "todo")
    assert_ok(todo)
    assert "[1] Buy groceries and cook dinner\n" in todo.stdout
    assert "[2] Write report\n" in todo.stdout

    assert_ok(run_cli(cwd, "mark-in-progress", "1"), "Task 1 marked as in-progress.\n")
    in_progress = run_cli(cwd, "list", "in-progress")
    assert_ok(in_progress)
    assert in_progress.stdout.startswith("[1] Buy groceries and cook dinner\nStatus:  in-progress\n")
    assert "[2]" not in in_progress.stdout

    assert_ok(run_cli(cwd, "mark-done", "1"), "Task 1 marked as done.\n")
    done = run_cli(cwd, "list", "done")
    assert_ok(done)
    assert done.stdout.startswith("[1] Buy groceries and cook dinner\nStatus:  done\n")
    assert_ok(run_cli(cwd, "list", "in-progress"), "No tasks found.\n")

    assert_ok(run_cli(cwd, "delete", "1"), "Task 1 deleted successfully.\n")
    remaining = run_cli(cwd, "list")
    assert_ok(remaining)
    assert "[1]" not in remaining.stdout
    assert "[2] Write report\n" in remaining.stdout
    assert set(read_store(cwd)) == {"2"}


# ---------------------------------------------------------------------------
# Output format (D-10, D-11)
# ---------------------------------------------------------------------------


def test_list_block_format_exact(cwd: Path) -> None:
    write_store(cwd, {"1": seed_task(1, "Buy groceries")})
    assert_ok(
        run_cli(cwd, "list"),
        "[1] Buy groceries\n"
        "Status:  todo\n"
        f"Created: {OLD_TS}\n"
        f"Updated: {OLD_TS}\n",
    )


def test_list_blocks_separated_by_blank_line_and_sorted(cwd: Path) -> None:
    write_store(cwd, {"10": seed_task(10, "ten"), "2": seed_task(2, "two")})
    out = run_cli(cwd, "list")
    assert_ok(out)
    blocks = out.stdout.rstrip("\n").split("\n\n")
    assert [b.splitlines()[0] for b in blocks] == ["[2] two", "[10] ten"]


def test_list_empty_prints_no_tasks_found(cwd: Path) -> None:
    assert_ok(run_cli(cwd, "list"), "No tasks found.\n")


@pytest.mark.parametrize("status", ["todo", "in-progress", "done"])
def test_list_filter_with_no_matches(cwd: Path, status: str) -> None:
    other = "done" if status != "done" else "todo"
    write_store(cwd, {"1": seed_task(1, status=other)})
    assert_ok(run_cli(cwd, "list", status), "No tasks found.\n")


def test_add_timestamps_iso_seconds(cwd: Path) -> None:
    run_cli(cwd, "add", "x")
    task = read_store(cwd)["1"]
    assert re.fullmatch(ISO_SECONDS, task["createdAt"])
    assert task["createdAt"] == task["updatedAt"]


# ---------------------------------------------------------------------------
# Persistence across invocations
# ---------------------------------------------------------------------------


def test_list_auto_creates_empty_store(cwd: Path) -> None:
    """X-02 / D-02 / D-6: first invocation creates tasks.json containing {}."""
    assert not (cwd / STORE_NAME).exists()
    run_cli(cwd, "list")
    assert read_store(cwd) == {}


def test_add_persists_full_record(cwd: Path) -> None:
    run_cli(cwd, "add", "  Buy groceries  ")
    data = read_store(cwd)
    assert list(data) == ["1"]
    task = data["1"]
    assert task["id"] == 1
    assert task["description"] == "Buy groceries"  # D-14: stripped
    assert task["status"] == "todo"
    assert set(task) == {"id", "description", "status", "createdAt", "updatedAt"}


def test_store_is_indented_json(cwd: Path) -> None:
    run_cli(cwd, "add", "x")
    assert (cwd / STORE_NAME).read_text(encoding="utf-8").startswith('{\n  "1": {')


def test_state_survives_separate_processes(cwd: Path) -> None:
    run_cli(cwd, "add", "first")
    run_cli(cwd, "add", "second")
    run_cli(cwd, "mark-done", "1")
    data = read_store(cwd)
    assert data["1"]["status"] == "done"
    assert data["2"]["status"] == "todo"
    done = run_cli(cwd, "list", "done")
    assert "[1] first\n" in done.stdout


def test_id_uses_max_plus_one_after_delete(cwd: Path) -> None:
    """D-7: deleting a lower ID does not cause reuse while a higher ID exists."""
    for d in ("a", "b", "c"):
        run_cli(cwd, "add", d)
    run_cli(cwd, "delete", "2")
    assert_ok(run_cli(cwd, "add", "d"), "Task added successfully (ID: 4)\n")
    assert set(read_store(cwd)) == {"1", "3", "4"}


def test_works_with_preexisting_store(cwd: Path) -> None:
    write_store(cwd, {"7": seed_task(7, "legacy")})
    assert_ok(run_cli(cwd, "add", "new"), "Task added successfully (ID: 8)\n")
    assert read_store(cwd)["7"] == seed_task(7, "legacy")


def test_update_refreshes_updated_at_keeps_created_at(cwd: Path) -> None:
    """D-05 / D-06 / X-10."""
    write_store(cwd, {"1": seed_task(1)})
    run_cli(cwd, "update", "1", "changed")
    task = read_store(cwd)["1"]
    assert task["description"] == "changed"
    assert task["createdAt"] == OLD_TS
    assert task["updatedAt"] != OLD_TS
    assert re.fullmatch(ISO_SECONDS, task["updatedAt"])


@pytest.mark.parametrize(
    ("command", "status"), [("mark-in-progress", "in-progress"), ("mark-done", "done")]
)
def test_mark_refreshes_updated_at_keeps_created_at(cwd: Path, command: str, status: str) -> None:
    write_store(cwd, {"1": seed_task(1, "keep me")})
    run_cli(cwd, command, "1")
    task = read_store(cwd)["1"]
    assert task["status"] == status
    assert task["description"] == "keep me"
    assert task["createdAt"] == OLD_TS
    assert task["updatedAt"] != OLD_TS


def test_list_does_not_modify_store(cwd: Path) -> None:
    write_store(cwd, {"1": seed_task(1)})
    before = (cwd / STORE_NAME).read_bytes()
    run_cli(cwd, "list")
    run_cli(cwd, "list", "todo")
    assert (cwd / STORE_NAME).read_bytes() == before


def test_no_tmp_file_left_behind(cwd: Path) -> None:
    run_cli(cwd, "add", "x")
    assert not (cwd / (STORE_NAME + ".tmp")).exists()


def test_unicode_description_roundtrip(cwd: Path) -> None:
    assert_ok(run_cli(cwd, "add", "Café ☕ naïve"))
    assert read_store(cwd)["1"]["description"] == "Café ☕ naïve"
    assert "[1] Café ☕ naïve\n" in run_cli(cwd, "list").stdout


def test_multiword_description_starting_with_dash(cwd: Path) -> None:
    assert_ok(run_cli(cwd, "add", "-5 apples"), "Task added successfully (ID: 1)\n")
    assert read_store(cwd)["1"]["description"] == "-5 apples"


def test_double_dash_allows_dash_prefixed_description(cwd: Path) -> None:
    assert_ok(run_cli(cwd, "add", "--", "-foo"), "Task added successfully (ID: 1)\n")
    assert read_store(cwd)["1"]["description"] == "-foo"


# ---------------------------------------------------------------------------
# Usage errors: unknown command, missing / extra args, flags (X-01, C-04, D-13)
# ---------------------------------------------------------------------------


def test_no_arguments(cwd: Path) -> None:
    assert_usage_error(run_cli(cwd))


def test_unknown_command(cwd: Path) -> None:
    assert_usage_error(run_cli(cwd, "bogus"), "bogus")


@pytest.mark.parametrize("flag", ["-h", "--help", "--version", "-v"])
def test_flags_rejected(cwd: Path, flag: str) -> None:
    assert_usage_error(run_cli(cwd, flag))


@pytest.mark.parametrize(
    "args",
    [
        ("add",),
        ("update",),
        ("update", "1"),
        ("delete",),
        ("mark-in-progress",),
        ("mark-done",),
    ],
)
def test_missing_arguments(cwd: Path, args: tuple[str, ...]) -> None:
    assert_usage_error(run_cli(cwd, *args), "required")


@pytest.mark.parametrize(
    "args",
    [
        ("add", "a", "b"),
        ("update", "1", "a", "b"),
        ("delete", "1", "2"),
        ("mark-in-progress", "1", "2"),
        ("mark-done", "1", "2"),
        ("list", "todo", "done"),
    ],
)
def test_extra_arguments(cwd: Path, args: tuple[str, ...]) -> None:
    assert_usage_error(run_cli(cwd, *args), "unrecognized arguments")


@pytest.mark.parametrize(
    "args", [("add", "--force", "x"), ("delete", "--all"), ("list", "--status", "todo")]
)
def test_subcommand_flags_rejected(cwd: Path, args: tuple[str, ...]) -> None:
    assert_usage_error(run_cli(cwd, *args))


def test_command_names_are_case_sensitive(cwd: Path) -> None:
    assert_usage_error(run_cli(cwd, "ADD", "x"))


def test_usage_error_does_not_create_store(cwd: Path) -> None:
    run_cli(cwd, "bogus")
    run_cli(cwd, "add")
    assert not (cwd / STORE_NAME).exists()


# ---------------------------------------------------------------------------
# ID errors (X-06, X-07, D-15)
# ---------------------------------------------------------------------------

ID_COMMANDS: list[tuple[str, ...]] = [
    ("update", "{id}", "new text"),
    ("delete", "{id}"),
    ("mark-in-progress", "{id}"),
    ("mark-done", "{id}"),
]


def _with_id(template: tuple[str, ...], task_id: str) -> list[str]:
    return [part.replace("{id}", task_id) for part in template]


@pytest.mark.parametrize("template", ID_COMMANDS, ids=lambda t: t[0])
@pytest.mark.parametrize("bad_id", ["abc", "1.5", "1e3", "+1", " 1", "1_0", "", "one"])
def test_non_integer_id(cwd: Path, template: tuple[str, ...], bad_id: str) -> None:
    write_store(cwd, {"1": seed_task(1)})
    before = (cwd / STORE_NAME).read_bytes()
    assert_error(run_cli(cwd, *_with_id(template, bad_id)), "Invalid task ID")
    assert (cwd / STORE_NAME).read_bytes() == before


@pytest.mark.parametrize("template", ID_COMMANDS, ids=lambda t: t[0])
@pytest.mark.parametrize("bad_id", ["0", "-1", "-42"])
def test_non_positive_id(cwd: Path, template: tuple[str, ...], bad_id: str) -> None:
    write_store(cwd, {"1": seed_task(1)})
    before = (cwd / STORE_NAME).read_bytes()
    assert_error(run_cli(cwd, *_with_id(template, bad_id)), "Invalid task ID")
    assert (cwd / STORE_NAME).read_bytes() == before


@pytest.mark.parametrize("template", ID_COMMANDS, ids=lambda t: t[0])
def test_non_existent_id(cwd: Path, template: tuple[str, ...]) -> None:
    write_store(cwd, {"1": seed_task(1)})
    before = (cwd / STORE_NAME).read_bytes()
    assert_error(run_cli(cwd, *_with_id(template, "99")), "Task 99 not found")
    assert (cwd / STORE_NAME).read_bytes() == before


@pytest.mark.parametrize("template", ID_COMMANDS, ids=lambda t: t[0])
def test_non_existent_id_on_empty_store(cwd: Path, template: tuple[str, ...]) -> None:
    assert_error(run_cli(cwd, *_with_id(template, "1")), "not found")


def test_delete_twice(cwd: Path) -> None:
    run_cli(cwd, "add", "x")
    assert_ok(run_cli(cwd, "delete", "1"))
    assert_error(run_cli(cwd, "delete", "1"), "Task 1 not found")


# ---------------------------------------------------------------------------
# Description and status errors (X-08, X-09)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("desc", ["", "   ", "\t \n"])
def test_add_empty_description(cwd: Path, desc: str) -> None:
    assert_error(run_cli(cwd, "add", desc), "description")
    assert read_store(cwd) == {}


@pytest.mark.parametrize("desc", ["", "   "])
def test_update_empty_description(cwd: Path, desc: str) -> None:
    write_store(cwd, {"1": seed_task(1)})
    before = (cwd / STORE_NAME).read_bytes()
    assert_error(run_cli(cwd, "update", "1", desc), "description")
    assert (cwd / STORE_NAME).read_bytes() == before


@pytest.mark.parametrize("status", ["bogus", "TODO", "not-done", "in_progress", ""])
def test_list_invalid_status(cwd: Path, status: str) -> None:
    assert_error(run_cli(cwd, "list", status), "Invalid status")


# ---------------------------------------------------------------------------
# Corrupt store (D-04, D-09, X-04)
# ---------------------------------------------------------------------------

CORRUPT_CONTENTS = [
    "not json",
    "{",
    "",
    "[]",
    '[{"id": 1}]',
    "42",
    '"string"',
    "null",
]

ALL_COMMANDS: list[tuple[str, ...]] = [
    ("list",),
    ("list", "todo"),
    ("add", "x"),
    ("update", "1", "x"),
    ("delete", "1"),
    ("mark-in-progress", "1"),
    ("mark-done", "1"),
]


@pytest.mark.parametrize("content", CORRUPT_CONTENTS)
@pytest.mark.parametrize("args", ALL_COMMANDS, ids=lambda a: "-".join(a))
def test_corrupt_store_rejected_and_preserved(
    cwd: Path, content: str, args: tuple[str, ...]
) -> None:
    store_file = cwd / STORE_NAME
    store_file.write_bytes(content.encode("utf-8"))
    assert_error(run_cli(cwd, *args), "Corrupt store")
    assert store_file.read_bytes() == content.encode("utf-8")
    assert not (cwd / (STORE_NAME + ".tmp")).exists()


def test_store_path_is_directory(cwd: Path) -> None:
    (cwd / STORE_NAME).mkdir()
    assert_error(run_cli(cwd, "list"), "Corrupt store")
    assert (cwd / STORE_NAME).is_dir()


def test_invalid_utf8_store(cwd: Path) -> None:
    store_file = cwd / STORE_NAME
    store_file.write_bytes(b"\xff\xfe\x00garbage")
    assert_error(run_cli(cwd, "list"), "Corrupt store")
    assert store_file.read_bytes() == b"\xff\xfe\x00garbage"


# ---------------------------------------------------------------------------
# Write failure (X-05)
# ---------------------------------------------------------------------------


def test_write_failure_leaves_store_untouched(cwd: Path) -> None:
    """A blocked temp path makes save_store fail; tasks.json must be unchanged."""
    write_store(cwd, {"1": seed_task(1)})
    before = (cwd / STORE_NAME).read_bytes()
    (cwd / (STORE_NAME + ".tmp")).mkdir()  # open(tmp, "w") will fail
    assert_error(run_cli(cwd, "add", "x"), "Failed to write store")
    assert (cwd / STORE_NAME).read_bytes() == before


# ---------------------------------------------------------------------------
# In-process: main() return codes (fast sanity, same contract)
# ---------------------------------------------------------------------------


def test_main_returns_exit_codes_in_process(
    cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sys.path.insert(0, str(REPO_ROOT))
    from task_cli.cli import main

    monkeypatch.chdir(cwd)
    assert main(["add", "x"]) == 0
    assert capsys.readouterr().out == "Task added successfully (ID: 1)\n"
    assert main(["delete", "9"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Task 9 not found" in captured.err
    assert main([]) == 1
