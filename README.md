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



## Spec

See `Blueprint__Task_Tracker_CLI.md` and `design.md`.
