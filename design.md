# Design: Task Tracker CLI

**Status:** Locked (v1)
**Depends on:** `Blueprint__Task_Tracker_CLI.md`
**Last updated:** 2026-09-29

## 1. Goals of This Document

Explain *how* the blueprint will be realized: module structure, contracts between layers, error strategy, entry point, and test strategy. Not the algorithm — that lives in code.

## 2. High-Level Architecture

Three layers, one direction of dependency:

```
     ┌─────────────────────┐
     │        cli          │  parses argv, prints, maps errors → exit codes
     └──────────┬──────────┘
                │ calls pure functions
     ┌──────────▼──────────┐
     │       tasks         │  business logic: validate, mutate, filter
     └──────────┬──────────┘
                │ takes/returns plain dict
     ┌──────────▼──────────┐
     │       store         │  load/save tasks.json (atomic)
     └─────────────────────┘
```

**Rule:** dependencies point downward only. `tasks` never imports `cli`. `store` never imports `tasks`.

## 3. Module Layout

```
task_cli/
  __init__.py
  __main__.py     # entry point for `python -m task_cli`
  cli.py          # argv parsing, dispatch, output, exit codes
  tasks.py        # pure business logic
  store.py        # file I/O, atomic write
  errors.py       # custom exception types
tests/
  test_tasks.py
  test_store.py
  test_cli.py     # integration tests via subprocess
```

## 4. Layer Contracts

### 4.1 `store.py`

```python
def load_store(path: Path) -> dict[str, dict]:
    """Return the parsed store. Create with {} if missing.
    Raise CorruptStore if the file exists but is not a JSON object."""

def save_store(path: Path, store: dict[str, dict]) -> None:
    """Atomically write store to path (tmp + os.replace).
    Raise StoreWriteError on permission/IO failure."""
```

**Invariants:**
- `load_store` never modifies an existing but corrupt file.
- `save_store` never leaves a partially-written `tasks.json`.
- `path` is passed in by the caller (never read from `os.getcwd()` inside).

### 4.2 `tasks.py`

```python
def add_task(store: dict, description: str) -> int: ...
def update_task(store: dict, task_id: int, description: str) -> None: ...
def delete_task(store: dict, task_id: int) -> None: ...
def set_status(store: dict, task_id: int, status: str) -> None: ...
def list_tasks(store: dict, status: str | None = None) -> list[dict]: ...
```

**Contract rules:**
- These functions **mutate the passed dict in place** and return nothing.
- `add_task` is the exception: it returns the newly generated `id`.
- They **do not** print. They **do not** read/write files.
- They **raise** from the closed set in `errors.py` on invalid input.

### 4.3 `cli.py`

```python
def main(argv: list[str]) -> int:
    """Parse argv, load store, dispatch to tasks, save store,
    print result, return exit code. This is the ONLY place that
    prints and the ONLY place that catches exceptions."""
```

**Responsibilities:**
- Build an `argparse` parser matching §4 of the blueprint.
- Load store once via `store.load_store(path)`.
- Dispatch by command name via a **dict of handlers** (see §4.5).
- Call the corresponding `tasks.*` function.
- Save store (only for mutating commands).
- Print success or error message.
- Return `0` or `1`.

### 4.4 `errors.py`

```python
class TaskError(Exception): ...
class TaskNotFound(TaskError): ...
class InvalidId(TaskError): ...
class InvalidDescription(TaskError): ...
class InvalidStatus(TaskError): ...
class CorruptStore(TaskError): ...
class StoreWriteError(TaskError): ...
```

**Rule:** every user-facing error path in the blueprint maps to exactly one of these.



## 5. Error Flow

```
tasks.*  raises TaskError subclass
             │
             ▼
cli.main  catches TaskError
             │
             ├─ print message to stderr
             └─ return 1
```

Unexpected exceptions (bugs) are **not caught** until tests are green. Only once the full test suite passes do we add a top-level `except Exception` guard that converts any residual crash into exit 1 + stderr message.

## 6. Entry Point

`task_cli/__main__.py`:

```python
from task_cli.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

User runs: `python -m task_cli add "Buy groceries"`.

## 7. Test Strategy

| Layer | Test style | Touches disk? | Touches subprocess? |
|-------|-----------|---------------|---------------------|
| `tasks` | unit | No | No |
| `store` | unit + `tmp_path` | Yes | No |
| `cli` | integration | Yes | Yes |

**Framework:** `pytest`, using `tmp_path` for filesystem isolation and `subprocess` (or `capsys`) for integration tests.
