"""Storage layer for Task Tracker CLI.

Handles atomic file persistence, missing file auto-creation, corruption checks,
and I/O error handling. Completely decoupled from domain logic and CLI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from task_cli.errors import CorruptStore, StoreWriteError

JSON_INDENT = 2


def load_store(path: Path | str) -> dict[str, dict]:
    """Return the parsed store. Create with {} if missing.

    Raise CorruptStore if the file exists but is not a JSON object.
    Never modifies an existing file when raising CorruptStore.
    """
    target_path = Path(path)
    if not target_path.exists():
        save_store(target_path, {})
        return {}

    if not target_path.is_file():
        raise CorruptStore(f"Corrupt store at '{target_path}': path is not a file")

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CorruptStore(f"Corrupt store at '{target_path}': invalid JSON") from exc

    if not isinstance(data, dict):
        raise CorruptStore(
            f"Corrupt store at '{target_path}': root must be a JSON object, got {type(data).__name__}"
        )

    return data


def save_store(path: Path | str, store: dict[str, dict]) -> None:
    """Atomically write store to path (tmp + os.replace).

    Write formatted JSON to temporary file path.with_name(path.name + ".tmp").
    Atomically swap using os.replace.
    Wrap file I/O errors in StoreWriteError.
    """
    target_path = Path(path)
    tmp_path = target_path.with_name(target_path.name + ".tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=JSON_INDENT)
            f.write("\n")
        os.replace(tmp_path, target_path)
    except OSError as exc:
        if tmp_path.exists():
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise StoreWriteError(f"Failed to write store to '{target_path}': {exc}") from exc
