"""Unit tests for the storage layer (task_cli.store).

Verifies atomic file persistence, missing file auto-creation, corruption checks,
and I/O error handling per Component 1 specifications and Blueprint requirements.
"""

from __future__ import annotations

import builtins
import json
import os
from pathlib import Path
import sys
from typing import Any

# Ensure workspace root is in sys.path when running pytest directly without python -m
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from task_cli.errors import CorruptStore, StoreWriteError
from task_cli.store import JSON_INDENT, load_store, save_store


def test_json_indent_constant() -> None:
    """Verify JSON_INDENT constant is defined and equals 2."""
    assert JSON_INDENT == 2


def test_load_store_missing_file_auto_creation(tmp_path: Path) -> None:
    """Missing store file is automatically created with an empty object {}.

    Blueprint: D-02, C-07.
    """
    store_file = tmp_path / "tasks.json"
    assert not store_file.exists()

    result = load_store(store_file)

    assert result == {}
    assert store_file.exists()
    assert store_file.is_file()
    assert json.loads(store_file.read_text(encoding="utf-8")) == {}


def test_load_store_successful_load_of_valid_json_object(tmp_path: Path) -> None:
    """Valid JSON object is loaded and returned as a dictionary."""
    store_file = tmp_path / "tasks.json"
    initial_data = {
        "1": {
            "id": 1,
            "description": "Buy groceries",
            "status": "todo",
            "createdAt": "2026-10-01T10:00:00",
            "updatedAt": "2026-10-01T10:00:00",
        },
        "2": {
            "id": 2,
            "description": "Cook dinner",
            "status": "in-progress",
            "createdAt": "2026-10-01T11:00:00",
            "updatedAt": "2026-10-01T11:30:00",
        },
    }
    store_file.write_text(json.dumps(initial_data, indent=JSON_INDENT), encoding="utf-8")

    result = load_store(store_file)

    assert result == initial_data


def test_load_store_corrupt_store_raised_on_non_json_without_altering_file(tmp_path: Path) -> None:
    """CorruptStore is raised on non-JSON content without altering the file.

    Blueprint: D-04, D-09, X-04.
    """
    store_file = tmp_path / "tasks.json"
    invalid_content = "NOT_VALID_JSON: {{{]]]'"
    store_file.write_text(invalid_content, encoding="utf-8")

    with pytest.raises(CorruptStore):
        load_store(store_file)

    assert store_file.read_text(encoding="utf-8") == invalid_content


def test_load_store_corrupt_store_raised_on_non_utf8_without_altering_file(tmp_path: Path) -> None:
    """CorruptStore is raised on invalid UTF-8 bytes without altering the file."""
    store_file = tmp_path / "tasks.json"
    invalid_bytes = b"\xff\xfe\x80\x00corrupt"
    store_file.write_bytes(invalid_bytes)

    with pytest.raises(CorruptStore):
        load_store(store_file)

    assert store_file.read_bytes() == invalid_bytes


def test_load_store_corrupt_store_raised_on_empty_file(tmp_path: Path) -> None:
    """CorruptStore is raised if file exists but is 0 bytes."""
    store_file = tmp_path / "tasks.json"
    store_file.write_text("", encoding="utf-8")

    with pytest.raises(CorruptStore):
        load_store(store_file)

    assert store_file.read_text(encoding="utf-8") == ""


@pytest.mark.parametrize(
    "array_json",
    [
        "[]",
        '[{"id": 1, "description": "test"}]',
        "[1, 2, 3]",
    ],
)
def test_load_store_corrupt_store_raised_on_json_array(tmp_path: Path, array_json: str) -> None:
    """CorruptStore is raised when root JSON structure is an array rather than an object.

    Blueprint: D-05, D-06, X-04.
    """
    store_file = tmp_path / "tasks.json"
    store_file.write_text(array_json, encoding="utf-8")

    with pytest.raises(CorruptStore):
        load_store(store_file)

    assert store_file.read_text(encoding="utf-8") == array_json


@pytest.mark.parametrize(
    "scalar_json",
    [
        "123",
        '"hello world"',
        "true",
        "false",
        "null",
        "45.67",
    ],
)
def test_load_store_corrupt_store_raised_on_scalar_root(tmp_path: Path, scalar_json: str) -> None:
    """CorruptStore is raised when root JSON structure is a scalar rather than an object."""
    store_file = tmp_path / "tasks.json"
    store_file.write_text(scalar_json, encoding="utf-8")

    with pytest.raises(CorruptStore):
        load_store(store_file)

    assert store_file.read_text(encoding="utf-8") == scalar_json


def test_load_store_corrupt_store_raised_on_directory(tmp_path: Path) -> None:
    """CorruptStore is raised if path exists but is a directory."""
    store_dir = tmp_path / "tasks.json"
    store_dir.mkdir()

    with pytest.raises(CorruptStore):
        load_store(store_dir)


def test_save_store_atomic_write_verification(tmp_path: Path) -> None:
    """Atomic write creates the file, formats with JSON_INDENT, and leaves no tmp file.

    Blueprint: D-16, §3.3.
    """
    store_file = tmp_path / "tasks.json"
    tmp_file = store_file.with_name(store_file.name + ".tmp")
    data: dict[str, Any] = {
        "1": {
            "id": 1,
            "description": "Write unit tests",
            "status": "todo",
        }
    }

    save_store(store_file, data)

    assert store_file.exists()
    assert not tmp_file.exists()

    content = store_file.read_text(encoding="utf-8")
    assert json.loads(content) == data
    # Verify 2-space indentation
    assert '  "1": {' in content
    assert '    "id": 1' in content


def test_save_store_overwrites_existing_file_atomically(tmp_path: Path) -> None:
    """Successive save_store calls atomically replace file content."""
    store_file = tmp_path / "tasks.json"
    tmp_file = store_file.with_name(store_file.name + ".tmp")

    first_data: dict[str, Any] = {"1": {"id": 1, "description": "First"}}
    second_data: dict[str, Any] = {"1": {"id": 1, "description": "Updated"}, "2": {"id": 2, "description": "Second"}}

    save_store(store_file, first_data)
    assert load_store(store_file) == first_data

    save_store(store_file, second_data)
    assert load_store(store_file) == second_data
    assert not tmp_file.exists()


def test_save_store_failure_preserves_original_file_and_cleans_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When os.replace fails during save_store, original file is preserved and tmp file is cleaned up."""
    store_file = tmp_path / "tasks.json"
    tmp_file = store_file.with_name(store_file.name + ".tmp")

    original_data: dict[str, Any] = {"1": {"id": 1, "description": "Original"}}
    save_store(store_file, original_data)
    original_content = store_file.read_text(encoding="utf-8")

    def failing_replace(src: Any, dst: Any) -> None:
        raise OSError("Simulated atomic swap failure")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(StoreWriteError, match="Simulated atomic swap failure"):
        save_store(store_file, {"2": {"id": 2, "description": "New"}})

    # Original file is untouched
    assert store_file.read_text(encoding="utf-8") == original_content
    # Temporary file is cleaned up
    assert not tmp_file.exists()


def test_save_store_raises_store_write_error_on_permission_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """StoreWriteError is raised when writing the temporary file fails (e.g. PermissionError).

    Blueprint: X-05.
    """
    store_file = tmp_path / "tasks.json"
    tmp_file = store_file.with_name(store_file.name + ".tmp")
    real_open = builtins.open

    def failing_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if str(file) == str(tmp_file) and "w" in mode:
            raise PermissionError("Permission denied")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", failing_open)

    with pytest.raises(StoreWriteError, match="Permission denied"):
        save_store(store_file, {"1": {"id": 1}})

    assert not tmp_file.exists()


def test_save_store_raises_store_write_error_on_invalid_directory(tmp_path: Path) -> None:
    """StoreWriteError is raised when the destination directory does not exist."""
    invalid_path = tmp_path / "non_existent_subdir" / "tasks.json"

    with pytest.raises(StoreWriteError):
        save_store(invalid_path, {})


def test_load_store_raises_store_write_error_if_auto_creation_fails(tmp_path: Path) -> None:
    """load_store raises StoreWriteError if auto-creating the missing store fails."""
    invalid_path = tmp_path / "non_existent_subdir" / "tasks.json"

    with pytest.raises(StoreWriteError):
        load_store(invalid_path)


def test_string_path_support(tmp_path: Path) -> None:
    """load_store and save_store accept string paths as well as Path objects."""
    store_file_str = str(tmp_path / "tasks.json")

    # Auto-create via string path
    data = load_store(store_file_str)
    assert data == {}

    # Save via string path
    save_store(store_file_str, {"1": {"id": 1, "description": "String path test"}})
    loaded = load_store(store_file_str)
    assert loaded["1"]["description"] == "String path test"
