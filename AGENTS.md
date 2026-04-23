# AGENTS.md — Guidance for coding agents

This repo is a **Dataiku DSS plugin** skeleton:
- Descriptor: `plugin.json`
- Reusable Python code: `python-lib/`
- Plugin components (runnables): `python-runnables/`

There is currently **no standard Python packaging/test toolchain** checked in (no `pyproject.toml`, `pytest.ini`, `Makefile`, etc.).

## Environment (Dataiku)
- Preferred interpreter: `/opt/dataiku/pyenv/bin/python` (Python 3.9)
- `import dataiku` works in this env.
- `/opt/dataiku/python-code-envs` is not present in this container.

## Cursor / Copilot rules
- No Cursor rules found (`.cursorrules` or `.cursor/rules/`).
- No Copilot instructions found (`.github/copilot-instructions.md`).

---

## Build / Lint / Test

### Syntax sanity
Fast compile of all plugin Python:

```bash
/opt/dataiku/pyenv/bin/python -m compileall -q python-lib python-runnables
```

### Unit tests (unittest)
There are currently **no tests**, but `unittest` is available.

Recommended layout if you add tests:
- `python-lib/tests/test_*.py` (make `python-lib/tests/__init__.py` if needed)

Run all tests:

```bash
/opt/dataiku/pyenv/bin/python -m unittest discover -s python-lib -p 'test_*.py'
```

Run a single test module (preferred for “single test file”):

```bash
/opt/dataiku/pyenv/bin/python -m unittest fiservgoverncicd.tests.test_example
```

Run a single test case / method:

```bash
/opt/dataiku/pyenv/bin/python -m unittest fiservgoverncicd.tests.test_example.TestSomething
/opt/dataiku/pyenv/bin/python -m unittest fiservgoverncicd.tests.test_example.TestSomething.test_happy_path
```

Notes:
- `unittest` takes **module paths** (dots), not file paths.
- Prefer mocking Dataiku APIs; avoid requiring a live DSS.

### Lint / format (optional)
No formatter/linter is installed by default here.

If `ruff` is available in your code env:

```bash
ruff check python-lib python-runnables
ruff format python-lib python-runnables
```

If `black` is used instead:

```bash
black python-lib python-runnables
```

### Package plugin (zip)

```bash
zip -r fiserv-govern-cicd.zip plugin.json python-lib python-runnables \
  -x '*.pyc' -x '__pycache__/*' -x '.git/*'
```

---

## Code style guidelines

### Python compatibility
- Target **Python 3.9**.
- Avoid 3.10+ only syntax (e.g. `match`, `|` unions).

### Imports
Ordering:
1) stdlib 2) third-party 3) Dataiku 4) local (`fiservgoverncicd`)

Avoid `import *`. Prefer explicit symbols.

Example:
```python
import json
import logging
from typing import Optional

import dataiku
from dataiku.runnables import Runnable

from fiservgoverncicd.github import GithubClient
```

### Formatting
- 4 spaces, no tabs.
- Prefer 88–100 char lines.
- Use f-strings.
- Keep functions small; extract helpers instead of deep nesting.
- Add docstrings to public modules/classes/functions.

### Naming
- Packages/modules/functions/vars: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Prefer clear names over abbreviations.

### Types
- Add type hints for public APIs and non-trivial helpers.
- Use `Optional[T]` when `None` is valid.
- Prefer structured returns (dict/dataclass) over “mystery tuples”.
- Use `TypedDict` for structured config dictionaries when helpful.

### Logging
- Use `logging.getLogger(__name__)`.
- Log actionable context (project key, ids) but **never secrets** (tokens, passwords).
- In runnables, log progress steps so DSS users can debug from run logs.

### Error handling
- Raise specific exceptions (`ValueError`, `RuntimeError`) instead of bare `Exception`.
- Validate `config`/`plugin_config` early; fail fast with clear messages.
- When wrapping, preserve context:

```python
try:
    ...
except SomeError as err:
    raise RuntimeError("Failed to <action>") from err
```

- Avoid bare `except:`.
- For network calls: set timeouts and handle transient failures.

### Dataiku plugin patterns
- Keep component entrypoints (runnables/recipes) thin.
- Put reusable logic in `python-lib/fiservgoverncicd/`.
- Treat `config` and `plugin_config` as untrusted input.
- Implement `get_progress_target()` / `progress_callback()` only if you can report meaningful progress.

### JSON descriptors
- `plugin.json` / `python-runnables/*/runnable.json` may contain comments (Dataiku-style).
- Keep keys stable and human-readable; avoid large rewrites of generated scaffolding.

---

## Repository layout
- Add reusable modules under `python-lib/fiservgoverncicd/`.
- Add new runnables under `python-runnables/<runnable-id>/`.
