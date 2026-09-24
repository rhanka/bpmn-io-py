"""Assert a built wheel contains only the runtime surface (cyber-review N6).

Usage: ``python scripts/check_wheel.py dist/*.whl``. Fails (exit 1) on
``*.pyc``/``*.xsd`` entries or ``tests/`` trees; requires ``py.typed`` and the
generated ``types.pyi`` to be present.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path, PurePath

FORBIDDEN_SUFFIXES = (".pyc", ".xsd")


def main(argv: list[str]) -> int:
    """Check every wheel matched by the argv globs."""
    paths = [
        str(match)
        for pattern in argv[1:]
        for match in Path(PurePath(pattern).parent).glob(PurePath(pattern).name)
    ]
    if not paths:
        print("check_wheel: no wheel matched", file=sys.stderr)
        return 1
    ok = True
    for path in paths:
        names = zipfile.ZipFile(path).namelist()
        bad = [
            name
            for name in names
            if name.endswith(FORBIDDEN_SUFFIXES) or "/tests/" in name or name.startswith("tests/")
        ]
        has_typed = any(name.endswith("py.typed") for name in names)
        has_stubs = any(name.endswith("types.pyi") for name in names)
        print(f"check_wheel: {path}: {len(names)} entries")
        if bad or not (has_typed and has_stubs):
            print(f"check_wheel: forbidden or missing entries: {bad}", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
