# Implementation Plan: Task Tracker CLI

## Goal Description

The Task Tracker CLI is a zero-dependency, standard-library-only Python command-line utility for tracking tasks, persisted in an atomic JSON document (`tasks.json`) in the current working directory. 

The baseline repository structure and error hierarchy (`task_cli/errors.py`) have already been created and verified. The goal is to implement the remaining layers of the system—persistence (`store.py`), domain business logic (`tasks.py`), CLI parsing/dispatch/output formatting (`cli.py`, `__main__.py`), integration testing (`test_cli.py`), and top-level error hardening (X-12)—in small, decoupled, independently verifiable implementation units adhering strictly to `Blueprint__Task_Tracker_CLI.md` and `design.md`.

---

## User Review Required

> [!IMPORTANT]
> **Argparse vs. Custom Argv Dispatcher:**
> Blueprint requirement C-04 mandates positional arguments exclusively (no flags, no prompts), and D-12 / I-05 require exit code 1 on any error. Python's default `argparse` module generates `-h`/`--help` flags by default and exits with code 2 on syntax errors. We propose configuring `argparse` with `add_help=False` and a custom error handler (or a dedicated positional argv dispatcher) to ensure 100% strict adherence to C-04 and exit code 1.

> [!NOTE]
> **`design.md` §4.5 Reference:**
> In `design.md` §4.3, the text states "Dispatch by command name via a dict of handlers (see §4.5)". However, section 4.5 is absent in `design.md`. The design intent is clear (a dictionary mapping command names to handler callables), and this pattern is adopted directly in IMP-003.

---

## Open Questions

1. **Strict Flag Prohibition:**
   Should invocation with `-h` or `--help` be rejected with exit code 1 like any unrecognized argument (strictly satisfying C-04: "no flags" and D-12: "exit code 1"), or should `--help` be permitted?
   *Recommendation:* In accordance with Blueprint C-04 and D-13, treat unknown flags as invalid positional arguments/commands, printing usage to `stderr` and exiting with code 1.

2. **JSON Formatting in `tasks.json`:**
   Blueprint §3.1 and §3.3 specify UTF-8 JSON object persistence. Should `tasks.json` be indented (e.g. `indent=2`) for human inspection, or compact?
   *Recommendation:* Use `json.dump(..., indent=2)` as it facilitates human readability when inspecting the file directly, while maintaining standard JSON parsing compatibility.

---

## Proposed Changes

```
┌────────────────────────────────────────────────────────┐
│                        cli.py                          │
│   (Parses argv, formats output, maps errors → exit 1)  │
└───────────────────────────┬────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
┌─────────────────────────────┐  ┌─────────────────────────────┐
│          tasks.py           │  │          store.py           │
│  (Pure business logic,      │  │  (Atomic file read/write,   │
│   mutations, validations)   │  │   corruption detection)     │
└──────────────┬──────────────┘  └──────────────┬──────────────┘
               │                                │
               └────────────────┬───────────────┘
                                ▼
                 ┌─────────────────────────────┐
                 │          errors.py          │
                 │   [ALREADY IMPLEMENTED]     │
                 └─────────────────────────────┘
```

### Component 1: Persistence & Storage Layer (`task_cli/store.py`)

Handles atomic file persistence, missing file auto-creation, corruption checks, and I/O error handling. Completely decoupled from domain logic and CLI.

#### [MODIFY] `task_cli/store.py`
- Implement `load_store(path: Path) -> dict[str, dict]`:
  - If `path` does not exist: create file with `{}` and return `{}`.
  - If `path` exists: parse JSON. If parsing fails, or if root is not a `dict`, raise `CorruptStore`. File is never modified.
- Implement `save_store(path: Path, store: dict[str, dict]) -> None`:
  - Write formatted JSON to temporary file `path.with_name(path.name + ".tmp")`.
  - Atomically swap using `os.replace`.
  - Wrap file I/O errors in `StoreWriteError`.

#### [MODIFY] `tests/test_store.py`
- Unit tests using pytest `tmp_path`:
  - Missing file auto-creation.
  - Successful load of valid JSON object.
  - CorruptStore raised on non-JSON content without altering file.
  - CorruptStore raised on JSON array (`[]`) or scalar root.
  - Atomic write verification.
  - StoreWriteError raised on read-only directory or write permission failure.

---

### Component 2: Domain Business Logic (`task_cli/tasks.py`)

Pure in-memory domain operations operating on `dict[str, dict]`. No disk access, no terminal printing.

#### [MODIFY] `task_cli/tasks.py`
- In-memory validation helpers:
  - `_validate_id(task_id: int)`: Positive integer check (rejects bools and values <= 0 with `InvalidId`).
  - `_validate_description(description: str)`: `.strip()` check (rejects empty/whitespace with `InvalidDescription`).
  - `_validate_status(status: str)`: Enforces `status in {"todo", "in-progress", "done"}` (raises `InvalidStatus`).
- Core operations:
  - `add_task(store: dict, description: str) -> int`:
    - Computes `id = max([int(k) for k in store.keys()], default=0) + 1`.
    - Timestamps: `createdAt` and `updatedAt` set to `datetime.now().isoformat(timespec="seconds")`.
    - Inserts `str(id)` into `store` with `status="todo"`. Returns `id`.
  - `update_task(store: dict, task_id: int, description: str) -> None`:
    - Updates description, refreshes `updatedAt`.
  - `delete_task(store: dict, task_id: int) -> None`:
    - Removes task from `store`.
  - `set_status(store: dict, task_id: int, status: str) -> None`:
    - Updates status, refreshes `updatedAt`.
  - `list_tasks(store: dict, status: str | None = None) -> list[dict]`:
    - Returns all tasks or tasks filtered by status.

#### [MODIFY] `tests/test_tasks.py`
- In-memory unit tests:
  - `add_task` ID generation, field initialization, description stripping.
  - Description validation errors (`InvalidDescription`).
  - `update_task` description update, timestamp refresh, immutability of `createdAt`.
  - `delete_task` removal, `TaskNotFound` on missing ID.
  - `set_status` transitions (`in-progress`, `done`), `InvalidStatus` on bad status.
  - `list_tasks` empty store, all tasks, filtered tasks by status.

---

### Component 3: CLI Dispatcher, Formatting & Entry Point (`task_cli/cli.py`, `task_cli/__main__.py`)

Handles argument parsing, command dispatching, stdout/stderr formatting, and exit codes.

#### [MODIFY] `task_cli/cli.py`
- Enforce exact positional argument counts per command (X-01).
- Handlers map to `tasks.*` and `store.*`:
  - `add <description>`
  - `update <id> <description>`
  - `delete <id>`
  - `mark-in-progress <id>`
  - `mark-done <id>`
  - `list [status]`
- Formatting:
  - Confirmation messages per D-11.
  - Task block layout per D-10 with aligned column labels.
  - `No tasks found.` on empty match.
- Exception boundary:
  - Catch `TaskError`: print message to `stderr`, return `1`.
  - Successful execution returns `0`.

#### [MODIFY] `task_cli/__main__.py`
- Standard entry point:
  ```python
  import sys
  from task_cli.cli import main

  if __name__ == "__main__":
      sys.exit(main(sys.argv[1:]))
  ```

---

### Component 4: Integration Test Suite (`tests/test_cli.py`)

Verifies end-to-end command-line executions via subprocess in temporary test environments.

#### [MODIFY] `tests/test_cli.py`
- Test full CLI lifecycle:
  - Add task -> list -> update -> list filtered -> mark-in-progress -> mark-done -> delete.
  - Persistence across invocations in `tasks.json`.
  - Missing argument / unknown command exit codes and stderr messages.
  - Non-integer ID, non-positive ID, non-existent ID error handling.
  - Corrupt store handling (stderr + exit 1 + file preserved).

---

### Component 5: Top-Level Exception Hardening (`task_cli/cli.py`)

Final production hardening to enforce Blueprint §5 X-12.

#### [MODIFY] `task_cli/cli.py`
- Wrap `main()` with top-level `except Exception as exc:` guard to ensure unhandled bugs exit 1 with a clean message on stderr, preventing Python tracebacks from leaking.

#### [MODIFY] `tests/test_cli.py`
- Regression test verifying unexpected internal exceptions produce clean stderr and exit code 1.

---

## Verification Plan

### Automated Tests
1. **Store Layer Unit Tests:**
   ```powershell
   .\.venv\Scripts\pytest tests/test_store.py -v
   ```
2. **Domain Logic Unit Tests:**
   ```powershell
   .\.venv\Scripts\pytest tests/test_tasks.py -v
   ```
3. **End-to-End Integration Tests:**
   ```powershell
   .\.venv\Scripts\pytest tests/test_cli.py -v
   ```
4. **Complete Test Suite:**
   ```powershell
   .\.venv\Scripts\pytest -v
   ```

### Manual Verification
Execute sample workflow matching `README.md`:
```powershell
python -m task_cli add "Buy groceries"
python -m task_cli list
python -m task_cli mark-in-progress 1
python -m task_cli list in-progress
python -m task_cli update 1 "Buy groceries and cook dinner"
python -m task_cli mark-done 1
python -m task_cli list done
python -m task_cli delete 1
python -m task_cli list
```
