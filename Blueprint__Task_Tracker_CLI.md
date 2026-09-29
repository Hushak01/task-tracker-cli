# Blueprint: Task Tracker CLI


## 0. Purpose & Scope

This document is the **single source of truth** for the Task Tracker CLI. It supersedes `requirements-extracting.txt` and `system-behavior.txt`. Any disagreement between this document and the original spec (`Task-tracker.md`) is a **documented decision** and is marked as such.

Where the original spec is silent, this document makes a decision and records the rationale.

---

## 1. Requirements Classification

### 1.1 Functional Requirements

Written in testable "SHALL" form.

| ID | Requirement |
|----|-------------|
| F-01 | The system SHALL add a new task with a user-supplied description. |
| F-02 | The system SHALL update the description of an existing task identified by ID. |
| F-03 | The system SHALL delete an existing task identified by ID. |
| F-04 | The system SHALL change the status of an existing task to `in-progress`. |
| F-05 | The system SHALL change the status of an existing task to `done`. |
| F-06 | The system SHALL list all tasks when no filter is provided. |
| F-07 | The system SHALL list tasks filtered by exactly one status: `todo`, `in-progress`, or `done`. |
| F-08 | The system SHALL list all tasks that are "not done" (status ∈ {`todo`, `in-progress`}). See ⚙️ Decision D-1. |

> ⚙️ **Decision D-1 — "Not done" listing**
>
> The spec's prose mentions "list all tasks that are not done," but the examples only show `list todo` and `list in-progress`.
> **Decision:** "Not done" is satisfied by the union of `list todo` and `list in-progress`. No separate `list not-done` command is added.
> **Rationale:** The examples define the actual CLI surface. Adding a command not in the examples would exceed the spec.

### 1.2 Constraints

| ID | Constraint | Source |
|----|------------|--------|
| C-01 | Implementation language: Python (chosen). | ⚙️ Decision |
| C-02 | No external libraries or frameworks. Standard library only. | Spec |
| C-03 | File system access via the language's native module (`os`, `pathlib`, `json`). | Spec |
| C-04 | User input accepted **exclusively** via positional command-line arguments. No flags, no prompts, no config files. | Spec |
| C-05 | All errors and edge cases handled gracefully. | Spec |
| C-06 | The JSON file lives in the current working directory (where the CLI is invoked). | Spec |
| C-07 | The JSON file is created automatically if missing. | Spec |

> ⚙️ **Decision D-2 — Meaning of "current directory"**
>
> The JSON file is created in the **process's current working directory** at invocation time (i.e., `os.getcwd()`), not next to the script.
> **Rationale:** Matches Unix CLI conventions; lets users run the tool in different project folders.
> **Rejected alternative:** Next to the script file — surprises users who `cd` elsewhere.

> ⚙️ **Decision D-3 — Standard library usage**
>
> `argparse`, `json`, `os`, `sys`, `pathlib`, and `datetime` are permitted. They ship with Python, so C-02 is satisfied.
> **Rationale:** C-02 forbids *external* libraries, not the standard library.

### 1.3 Data Requirements

| ID | Requirement |
|----|-------------|
| D-01 | The system SHALL persist state in a JSON file named `tasks.json` in the current working directory. |
| D-02 | The system SHALL auto-create `tasks.json` with an empty object `{}` if it does not exist. |
| D-03 | Each task SHALL have the fields: `id`, `description`, `status`, `createdAt`, `updatedAt`. |
| D-04 | The system SHALL NOT overwrite or reset `tasks.json` if it is unparseable. |
| D-05 | `createdAt` SHALL be set once at creation and never modified. |
| D-06 | `updatedAt` SHALL be refreshed on every modification (description or status). |

> ⚙️ **Decision D-4 — File name**
>
> `tasks.json` (explicit, so scripts and tests can rely on it).
> **Rejected alternative:** `data.json`, `.tasks.json` — less self-documenting.

> ⚙️ **Decision D-5 — JSON root shape**
>
> `tasks.json` is a JSON **object keyed by string ID**: `{"1": {...}, "2": {...}}`.
> **Rationale:** O(1) lookup by ID, natural uniqueness of IDs.
> **Rejected alternative:** Array of task objects — requires linear scans and manual uniqueness checks.
> **Consequence:** JSON keys are strings; the code must cast to `int` when comparing with user-supplied IDs.

> ⚙️ **Decision D-6 — Empty store shape**
>
> A newly created `tasks.json` contains exactly `{}` (empty JSON object), not `[]`.

> ⚙️ **Decision D-7 — ID strategy**
>
> Auto-incrementing integer: `max(existing ids, default=0) + 1`.
> **Rationale:** Simple, deterministic, no counter to persist separately.
> **Consequence:** Deleted IDs are never reused within a session where a higher ID exists.
> **Rejected alternative:** UUIDs — overkill for a local CLI, harder for humans to type.

> ⚙️ **Decision D-8 — Timestamp format**
>
> ISO 8601, generated via `datetime.now().isoformat(timespec="seconds")` (no timezone suffix).
> **Rationale:** Human-readable, sortable, matches the spec's "e.g., ISO 8601."
> **Rejected alternative:** Unix epoch integers — less readable in the JSON file.

> ⚙️ **Decision D-9 — Corrupt file handling**
>
> If `tasks.json` exists but cannot be parsed as JSON, the process SHALL print an error to stderr and exit with code 1. The file SHALL NOT be modified.
> **Rationale:** Never destroy user data. (Matches D-04.)

### 1.4 Interface Requirements

| ID | Requirement |
|----|-------------|
| I-01 | The system is invoked as `task-cli <command> [args...]`. |
| I-02 | Commands use kebab-case: `add`, `update`, `delete`, `mark-in-progress`, `mark-done`, `list`. |
| I-03 | All user inputs are positional arguments. |
| I-04 | Successful operations print a confirmation to stdout. |
| I-05 | Errors print to stderr and exit with code 1. |
| I-06 | Success exits with code 0. |

> ⚙️ **Decision D-10 — Output format for `list`**
>
> One task per block:
>
> ```
> [1] Buy groceries
> Status:  todo
> Created: 2026-09-28T10:00:00
> Updated: 2026-09-28T10:00:00
> ```
>
> If no tasks match, print `No tasks found.` to stdout and exit 0.
> **Rationale:** Human-readable for a personal CLI.
> **Rejected alternative:** Raw JSON dump — machine-friendly but hostile to humans.

> ⚙️ Decision D-11 — Confirmation message formats
>
> · add → Task added successfully (ID: {id}) (matches spec's example verbatim)
> · update → Task {id} updated successfully.
> · delete → Task {id} deleted successfully.
> · mark-in-progress → Task {id} marked as in-progress.
> · mark-done → Task {id} marked as done.
>   Rationale: Spec only fixes the add message; the rest are consistent in tone.

> ⚙️ Decision D-12 — Exit codes
>
> 0 on success, 1 on any error (unknown command, missing args, ID not found, invalid status, corrupt file, write failure).
> Rationale: Conventional, scriptable.
> Rejected alternative: Different codes per error class — premature for this scope.

> ⚙️ Decision D-13 — Unknown / missing command
>
> Print usage line to stderr, exit 1.

---

## 2. Domain Model

**Entity:** Task

| Field | Type | Allowed Values | Invariants |
|-------|------|----------------|------------|
| id | integer | Positive integer (≥ 1) | Unique across store; never 0 or negative; never null. |
| description | string | Non-empty, not solely whitespace | Trimmed of leading/trailing whitespace before storage. |
| status | string | enum `todo`, `in-progress`, `done` | Defaults to todo on creation. |
| createdAt | string (ISO 8601) | — | Set once at creation; immutable. |
| updatedAt | string (ISO 8601) | — | Refreshed whenever description or status changes. |

> ⚙️ Decision D-14 — Description trimming
>
> Descriptions are .strip()-ed before validation and storage.
> Rationale: Prevents "  " from passing validation and prevents inconsistent stored values.
> Consequence: add "  hi  " stores "hi".

> ⚙️ Decision D-15 — ID positivity
>
> IDs must be positive integers everywhere (this resolves the drift between the two prior files, which inconsistently said "integer" vs. "positive integer"). Applied uniformly to update, delete, mark-in-progress, mark-done.

---

## 3. Persistence Design

### 3.1 File Layout

· Path: ./tasks.json (relative to CWD at invocation)
· Encoding: UTF-8
· Root: JSON object { "<id>": <task>, ... }
· Empty state: {}

### 3.2 Read Behavior

1. If file does not exist → create with {} and continue.
2. If file exists but is not valid JSON → print error to stderr, exit 1. Do not modify.
3. If file exists and is valid JSON but is not an object → same as (2).

### 3.3 Write Behavior

· Write full JSON object back on every mutation.
· Use atomic-ish write: write to a temp file, then os.replace — see ⚙️ Decision D-16.
· If write fails (permissions, disk) → print error to stderr, exit 1.

> ⚙️ Decision D-16 — Atomic write
>
> Write to tasks.json.tmp, then os.replace(tmp, tasks.json).
> Rationale: Prevents corrupting tasks.json if the process dies mid-write.
> Rejected alternative: Direct overwrite — simpler, but a crash can leave a truncated file.

---

## 4. Command Contract

Each command lists: Args, Preconditions, Behavior, Success output, Failure cases, Exit code.

### 4.1 add <description>

· Args: exactly one positional string.
· Preconditions: description present; after .strip(), non-empty.
· Behavior: load store → compute id = max(ids, default=0) + 1 → build task (status="todo", both timestamps = now) → insert → save.
· Success: Task added successfully (ID: {id}) → exit 0.
· Failures: missing arg; empty/whitespace description; write permission denied → exit 1.

### 4.2 update <id> <description>

· Args: exactly two positionals; <id> convertible to positive int; description non-empty after strip.
· Preconditions: ID exists in store.
· Behavior: load store → find task → overwrite description → set updatedAt = now → save.
· Success: Task {id} updated successfully. → exit 0.
· Failures: missing args; non-integer ID; non-positive ID; ID not found; empty description; write failure → exit 1.

### 4.3 delete <id>

· Args: exactly one positional; positive int.
· Preconditions: ID exists.
· Behavior: load store → remove key → save.
· Success: Task {id} deleted successfully. → exit 0.
· Failures: missing arg; non-integer/non-positive ID; ID not found; write failure → exit 1.

### 4.4 mark-in-progress <id>

· Args: exactly one positional; positive int.
· Preconditions: ID exists.
· Behavior: load store → set status="in-progress" → set updatedAt = now → save.
· Success: Task {id} marked as in-progress. → exit 0.
· Failures: missing arg; non-integer/non-positive ID; ID not found; write failure → exit 1.

### 4.5 mark-done <id>

Same as 4.4 with status="done" and message Task {id} marked as done.

### 4.6 list [status]

· Args: zero or one positional. If present, must be exactly todo, in-progress, or done.
· Preconditions: store file is either absent or valid JSON object.
· Behavior: load store (auto-create if absent) → select all tasks, or filter by status → print each per D-10.
· Success: printed tasks (or No tasks found.) → exit 0.
· Failures: unknown status filter; corrupt file → exit 1.

---

## 5. Cross-Cutting Behavior

### ID Behavior

X-01 CLI arg validation: unknown command or wrong arg count → stderr + exit 1.
X-02 File auto-creation on first mutation or list (D-02).
X-03 Reading and writing via json, os, pathlib only (C-02, C-03).
X-04 Corrupt file → abort, stderr, exit 1, never overwrite (D-04, D-09).
X-05 Write permission denied → abort, stderr, exit 1, file untouched.
X-06 Non-integer / non-positive ID → abort, stderr, exit 1 (D-15).
X-07 ID not found → abort, stderr, exit 1.
X-08 Invalid status filter → abort, stderr, exit 1.
X-09 Empty/whitespace description → abort, stderr, exit 1 (D-14).
X-10 createdAt immutable; updatedAt refreshed on change (D-08).
X-11 Success → stdout, exit 0. Errors → stderr, exit 1 (D-12).
X-12 No unhandled exceptions reach the user — wrap the top level in a guard.

---

## 6. Ambiguities Resolved (Changelog from Prior Files)

This section exists so the decisions don't get lost.

| # | Ambiguity | Resolution | Where |
|---|-----------|------------|-------|
| 1 | "list not done" not in examples | Treated as union of todo + in-progress | D-1 |
| 2 | "current directory" meaning | CWD at invocation | D-2 |
| 3 | ID "integer" vs. "positive integer" | Positive integer everywhere | D-15 |
| 4 | Root JSON shape (object vs. array) | Object keyed by string ID | D-5 |
| 5 | Empty store shape | {} | D-6 |
| 6 | Timestamp format | ISO 8601, seconds precision, no TZ | D-8 |
| 7 | Output format for list | Human-readable block per task | D-10 |
| 8 | Confirmation messages for non-add commands | Defined explicitly | D-11 |
| 9 | Exit codes | 0 success / 1 error | D-12 |
| 10 | Unknown command behavior | stderr + exit 1 | D-13 |
| 11 | Description whitespace handling | Strip before validate & store | D-14 |
| 12 | Atomic write | tmp + os.replace | D-16 |
| 13 | argparse allowed? | Yes, it's stdlib | D-3 |

---

## 7. Non-Goals / Explicitly Out of Scope

· No due dates, priorities, tags, or projects.
· No undo/redo.
· No multi-user or concurrent-write locking.
· No search by substring.
· No sorting options.
· No machine-readable output mode (JSON) — may be added later as a ⚙️ Decision.


