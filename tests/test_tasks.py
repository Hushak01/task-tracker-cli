"""Unit tests for the domain logic layer (task_cli.tasks).

Pure in-memory tests: no disk, no subprocess. Timestamps are controlled by
monkeypatching ``task_cli.tasks._now`` so refresh/immutability is deterministic.

Component 2 of task_tracker_implementation_plan.md.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

# Ensure workspace root is in sys.path when running pytest directly without python -m
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from task_cli import tasks
from task_cli.errors import (
    InvalidDescription,
    InvalidId,
    InvalidStatus,
    TaskError,
    TaskNotFound,
)
from task_cli.tasks import (
    _validate_description,
    _validate_id,
    _validate_status,
    add_task,
    delete_task,
    list_tasks,
    set_status,
    update_task,
)

T0 = "2026-09-28T10:00:00"
T1 = "2026-09-28T11:00:00"
T2 = "2026-09-28T12:00:00"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Return a setter that makes ``tasks._now`` yield the given timestamps in order."""

    def _set(*stamps: str) -> None:
        it: Iterator[str] = iter(stamps)
        monkeypatch.setattr(tasks, "_now", lambda: next(it))

    return _set


def _make_store(*statuses: str) -> dict[str, dict]:
    """Build a store with one task per status, IDs 1..n, all at T0."""
    return {
        str(i): {
            "id": i,
            "description": f"task {i}",
            "status": s,
            "createdAt": T0,
            "updatedAt": T0,
        }
        for i, s in enumerate(statuses, start=1)
    }


# ---------------------------------------------------------------------------
# _now
# ---------------------------------------------------------------------------


def test_now_is_iso8601_seconds_without_timezone() -> None:
    """_now uses isoformat(timespec='seconds') with no TZ suffix (D-8)."""
    value = tasks._now()
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is None
    assert parsed.microsecond == 0
    assert value == parsed.isoformat(timespec="seconds")
    assert len(value) == len("YYYY-MM-DDTHH:MM:SS")


# ---------------------------------------------------------------------------
# _validate_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [1, 2, 999_999])
def test_validate_id_accepts_positive_ints(value: int) -> None:
    assert _validate_id(value) == value


@pytest.mark.parametrize("value", [0, -1, -100])
def test_validate_id_rejects_non_positive(value: int) -> None:
    with pytest.raises(InvalidId):
        _validate_id(value)


@pytest.mark.parametrize("value", [True, False])
def test_validate_id_rejects_bools(value: bool) -> None:
    with pytest.raises(InvalidId):
        _validate_id(value)


@pytest.mark.parametrize("value", ["1", 1.0, None, [1]])
def test_validate_id_rejects_non_int_types(value: Any) -> None:
    with pytest.raises(InvalidId):
        _validate_id(value)


# ---------------------------------------------------------------------------
# _validate_description
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("hi", "hi"), ("  hi  ", "hi"), ("\tBuy milk\n", "Buy milk"), ("a  b", "a  b")],
)
def test_validate_description_strips(raw: str, expected: str) -> None:
    assert _validate_description(raw) == expected


@pytest.mark.parametrize("raw", ["", " ", "   ", "\t\n  \r"])
def test_validate_description_rejects_empty_or_whitespace(raw: str) -> None:
    with pytest.raises(InvalidDescription):
        _validate_description(raw)


@pytest.mark.parametrize("raw", [None, 123])
def test_validate_description_rejects_non_str(raw: Any) -> None:
    with pytest.raises(InvalidDescription):
        _validate_description(raw)


# ---------------------------------------------------------------------------
# _validate_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["todo", "in-progress", "done"])
def test_validate_status_accepts_valid(status: str) -> None:
    assert _validate_status(status) == status


@pytest.mark.parametrize(
    "status", ["", "TODO", "Done", "in_progress", "inprogress", "not-done", " todo", None]
)
def test_validate_status_rejects_invalid(status: Any) -> None:
    with pytest.raises(InvalidStatus):
        _validate_status(status)


# ---------------------------------------------------------------------------
# add_task
# ---------------------------------------------------------------------------


def test_add_task_first_id_is_one(clock: Callable[..., None]) -> None:
    clock(T0)
    store: dict[str, dict] = {}
    assert add_task(store, "Buy groceries") == 1
    assert list(store.keys()) == ["1"]


def test_add_task_initializes_all_fields(clock: Callable[..., None]) -> None:
    """New task has id/description/status=todo/createdAt==updatedAt (D-03)."""
    clock(T0)
    store: dict[str, dict] = {}
    add_task(store, "Buy groceries")
    assert store["1"] == {
        "id": 1,
        "description": "Buy groceries",
        "status": "todo",
        "createdAt": T0,
        "updatedAt": T0,
    }


def test_add_task_ids_increment(clock: Callable[..., None]) -> None:
    clock(T0, T0, T0)
    store: dict[str, dict] = {}
    assert [add_task(store, f"t{i}") for i in range(3)] == [1, 2, 3]
    assert set(store.keys()) == {"1", "2", "3"}


def test_add_task_id_is_max_plus_one_with_gaps(clock: Callable[..., None]) -> None:
    """ID = max(existing) + 1, not len+1 and not gap-filling (D-7)."""
    clock(T1)
    store = _make_store("todo", "todo", "todo")
    del store["2"]
    assert add_task(store, "new") == 4


def test_add_task_does_not_reuse_deleted_highest_id_when_higher_exists(
    clock: Callable[..., None],
) -> None:
    clock(T1)
    store = {"5": _make_store("todo")["1"] | {"id": 5}}
    assert add_task(store, "new") == 6


def test_add_task_uses_numeric_not_lexicographic_max(clock: Callable[..., None]) -> None:
    """'10' > '9' numerically even though '9' > '10' as strings."""
    clock(T1)
    store = {str(i): {"id": i} for i in (2, 9, 10)}
    assert add_task(store, "new") == 11


def test_add_task_strips_description(clock: Callable[..., None]) -> None:
    """add '  hi  ' stores 'hi' (D-14)."""
    clock(T0)
    store: dict[str, dict] = {}
    add_task(store, "  hi  ")
    assert store["1"]["description"] == "hi"


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
def test_add_task_rejects_empty_description_without_mutation(raw: str) -> None:
    store = _make_store("todo")
    snapshot = {k: dict(v) for k, v in store.items()}
    with pytest.raises(InvalidDescription):
        add_task(store, raw)
    assert store == snapshot


def test_add_task_uses_real_timestamp_format() -> None:
    """Without monkeypatching, timestamps are ISO 8601 at seconds precision."""
    store: dict[str, dict] = {}
    add_task(store, "x")
    task = store["1"]
    assert task["createdAt"] == task["updatedAt"]
    assert datetime.fromisoformat(task["createdAt"]).microsecond == 0


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------


def test_update_task_changes_description_and_refreshes_updated_at(
    clock: Callable[..., None],
) -> None:
    store = _make_store("todo")
    clock(T1)
    update_task(store, 1, "new text")
    assert store["1"]["description"] == "new text"
    assert store["1"]["updatedAt"] == T1


def test_update_task_created_at_is_immutable(clock: Callable[..., None]) -> None:
    """createdAt never changes on update (D-05)."""
    clock(T0, T1, T2)
    store: dict[str, dict] = {}
    add_task(store, "orig")
    update_task(store, 1, "first edit")
    update_task(store, 1, "second edit")
    assert store["1"]["createdAt"] == T0
    assert store["1"]["updatedAt"] == T2


def test_update_task_strips_description(clock: Callable[..., None]) -> None:
    store = _make_store("todo")
    clock(T1)
    update_task(store, 1, "   padded   ")
    assert store["1"]["description"] == "padded"


def test_update_task_preserves_status_and_id(clock: Callable[..., None]) -> None:
    store = _make_store("in-progress")
    clock(T1)
    update_task(store, 1, "x")
    assert store["1"]["status"] == "in-progress"
    assert store["1"]["id"] == 1


def test_update_task_only_touches_target(clock: Callable[..., None]) -> None:
    store = _make_store("todo", "todo")
    other = dict(store["2"])
    clock(T1)
    update_task(store, 1, "x")
    assert store["2"] == other


def test_update_task_not_found() -> None:
    store = _make_store("todo")
    snapshot = {k: dict(v) for k, v in store.items()}
    with pytest.raises(TaskNotFound):
        update_task(store, 99, "x")
    assert store == snapshot


@pytest.mark.parametrize("bad_id", [0, -1, True, "1", 1.5, None])
def test_update_task_invalid_id(bad_id: Any) -> None:
    store = _make_store("todo")
    with pytest.raises(InvalidId):
        update_task(store, bad_id, "x")


@pytest.mark.parametrize("raw", ["", "   "])
def test_update_task_invalid_description_without_mutation(raw: str) -> None:
    store = _make_store("todo")
    snapshot = {k: dict(v) for k, v in store.items()}
    with pytest.raises(InvalidDescription):
        update_task(store, 1, raw)
    assert store == snapshot


# ---------------------------------------------------------------------------
# delete_task
# ---------------------------------------------------------------------------


def test_delete_task_removes_only_target() -> None:
    store = _make_store("todo", "done", "todo")
    delete_task(store, 2)
    assert set(store.keys()) == {"1", "3"}


def test_delete_task_last_task_leaves_empty_store() -> None:
    store = _make_store("todo")
    delete_task(store, 1)
    assert store == {}


def test_delete_task_not_found() -> None:
    store = _make_store("todo")
    with pytest.raises(TaskNotFound):
        delete_task(store, 2)
    assert set(store.keys()) == {"1"}


def test_delete_task_not_found_on_empty_store() -> None:
    with pytest.raises(TaskNotFound):
        delete_task({}, 1)


def test_delete_task_twice_raises_not_found() -> None:
    store = _make_store("todo")
    delete_task(store, 1)
    with pytest.raises(TaskNotFound):
        delete_task(store, 1)


@pytest.mark.parametrize("bad_id", [0, -5, False, "1"])
def test_delete_task_invalid_id(bad_id: Any) -> None:
    store = _make_store("todo")
    with pytest.raises(InvalidId):
        delete_task(store, bad_id)
    assert set(store.keys()) == {"1"}


# ---------------------------------------------------------------------------
# set_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["in-progress", "done", "todo"])
def test_set_status_transitions(clock: Callable[..., None], status: str) -> None:
    store = _make_store("todo")
    clock(T1)
    set_status(store, 1, status)
    assert store["1"]["status"] == status
    assert store["1"]["updatedAt"] == T1
    assert store["1"]["createdAt"] == T0


def test_set_status_full_lifecycle(clock: Callable[..., None]) -> None:
    """todo -> in-progress -> done, updatedAt refreshed each time, createdAt fixed."""
    clock(T0, T1, T2)
    store: dict[str, dict] = {}
    add_task(store, "x")
    set_status(store, 1, "in-progress")
    assert (store["1"]["status"], store["1"]["updatedAt"]) == ("in-progress", T1)
    set_status(store, 1, "done")
    assert (store["1"]["status"], store["1"]["updatedAt"]) == ("done", T2)
    assert store["1"]["createdAt"] == T0


def test_set_status_preserves_description(clock: Callable[..., None]) -> None:
    store = _make_store("todo")
    clock(T1)
    set_status(store, 1, "done")
    assert store["1"]["description"] == "task 1"


@pytest.mark.parametrize("status", ["", "DONE", "finished", "in_progress", None])
def test_set_status_invalid_status_without_mutation(status: Any) -> None:
    store = _make_store("todo")
    snapshot = {k: dict(v) for k, v in store.items()}
    with pytest.raises(InvalidStatus):
        set_status(store, 1, status)
    assert store == snapshot


def test_set_status_not_found() -> None:
    store = _make_store("todo")
    with pytest.raises(TaskNotFound):
        set_status(store, 42, "done")


@pytest.mark.parametrize("bad_id", [0, -1, True, "1"])
def test_set_status_invalid_id(bad_id: Any) -> None:
    store = _make_store("todo")
    with pytest.raises(InvalidId):
        set_status(store, bad_id, "done")


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------


def test_list_tasks_empty_store() -> None:
    assert list_tasks({}) == []


@pytest.mark.parametrize("status", ["todo", "in-progress", "done"])
def test_list_tasks_empty_store_with_filter(status: str) -> None:
    assert list_tasks({}, status) == []


def test_list_tasks_all() -> None:
    store = _make_store("todo", "in-progress", "done")
    result = list_tasks(store)
    assert [t["id"] for t in result] == [1, 2, 3]
    assert result == [store["1"], store["2"], store["3"]]


def test_list_tasks_sorted_numerically() -> None:
    store = {str(i): {"id": i, "status": "todo"} for i in (10, 2, 1)}
    assert [t["id"] for t in list_tasks(store)] == [1, 2, 10]


@pytest.mark.parametrize(
    ("status", "expected_ids"),
    [("todo", [1, 4]), ("in-progress", [2]), ("done", [3])],
)
def test_list_tasks_filtered(status: str, expected_ids: list[int]) -> None:
    store = _make_store("todo", "in-progress", "done", "todo")
    result = list_tasks(store, status)
    assert [t["id"] for t in result] == expected_ids
    assert all(t["status"] == status for t in result)


def test_list_tasks_filter_with_no_matches() -> None:
    store = _make_store("todo", "todo")
    assert list_tasks(store, "done") == []


@pytest.mark.parametrize("status", ["", "not-done", "TODO", "all"])
def test_list_tasks_invalid_status(status: str) -> None:
    with pytest.raises(InvalidStatus):
        list_tasks(_make_store("todo"), status)


def test_list_tasks_does_not_mutate_store() -> None:
    store = _make_store("todo", "done")
    snapshot = {k: dict(v) for k, v in store.items()}
    result = list_tasks(store)
    result[0]["description"] = "hacked"
    result.clear()
    assert store == snapshot


# ---------------------------------------------------------------------------
# Error hierarchy contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda: add_task({}, ""),
        lambda: update_task({}, 0, "x"),
        lambda: delete_task({}, 1),
        lambda: set_status(_make_store("todo"), 1, "bogus"),
        lambda: list_tasks({}, "bogus"),
    ],
)
def test_all_domain_errors_are_task_errors(call: Callable[[], object]) -> None:
    """cli.main relies on catching TaskError for every user-facing failure."""
    with pytest.raises(TaskError):
        call()
