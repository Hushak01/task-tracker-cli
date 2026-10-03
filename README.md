# Task Tracker CLI

A stdlib-only Python CLI for tracking tasks, persisted in `tasks.json`
in the current working directory.

## Requirements
- Python 3.10+

## Usage

```
python -m task_cli add "Buy groceries"
python -m task_cli update 1 "Buy milk"
python -m task_cli delete 1
python -m task_cli mark-in-progress 1
python -m task_cli mark-done 1
python -m task_cli list
python -m task_cli list todo
python -m task_cli list in-progress
python -m task_cli list done
```


## Development

- Python version requirement: Python >=3.10
- Create and activate virtual environment:
  - Windows (PowerShell):
    ```powershell
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```
  - POSIX (bash):
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
- Editable install:
  ```bash
  pip install -e ".[dev]"
  ```
- Running tests:
  ```bash
  pytest -v
  pytest tests/test_store.py -v
  ```
- Running the CLI:
  ```bash
  python -m task_cli add "Buy groceries"
  task-cli add "Buy groceries"
  ```
- Specifications: See `Blueprint__Task_Tracker_CLI.md` and `design.md`.
- Implementation Plan: See `task_tracker_implementation_plan.md`.
