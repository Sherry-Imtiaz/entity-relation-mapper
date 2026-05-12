from __future__ import annotations

import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PYTHON_FILES = [
    "app.py",
    "config.py",
    "models.py",
    "state_manager.py",
    "importers.py",
    "validation.py",
    "inference.py",
    "exports.py",
    "visualisation.py",
    "ui_shared.py",
    "ui_contexts.py",
    "ui_tables.py",
    "ui_relationships.py",
    "ui_inference.py",
    "ui_erd.py",
    "ui_export.py",
]

errors = []

for filename in PYTHON_FILES:
    path = ROOT / filename
    if not path.exists():
        errors.append(f"Missing file: {filename}")
        continue

    try:
        py_compile.compile(str(path), doraise=True)
        print(f"OK: {filename}")
    except Exception as exc:
        errors.append(f"{filename}: {exc}")

if errors:
    print("\nCompile check failed:")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print("\nCompile check passed.")
