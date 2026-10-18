"""Independent Unicode case oracle for the pinned 15.0.0 vectors (test-only).

Derives expected ``upper``/``lower`` results with the running interpreter's
own ``str.upper``/``str.lower`` (CPython implements the full default case
mappings, locale-independent, including the untagged Final_Sigma rule) and
stamps ``unicodedata.unidata_version``. It never imports ``bpmn_io`` or the
generated tables: run it under ``uv run --no-project --python 3.12`` (UCD
15.0.0) to seal ``contracts/unicode-case/15.0.0/vectors.json`` and under
``--python 3.14`` (UCD 16.0.0) for the version witness. stdlib only.
"""

from __future__ import annotations

import json
import sys
import unicodedata

#: Fixed vector inputs, mirroring the contract's coverage: sharp s, dotted I,
#: final/non-final/lone sigma, the 16.0.0 witness, ASCII, ligature, final form.
ORACLE_INPUTS: tuple[str, ...] = (
    "\u00df",
    "\u0130",
    "\u039f\u03a3",
    "\u039f\u03a3\u0391",
    "\u03a3",
    "\u0264",
    "Task",
    "SS",
    "\ufb06",
    "\u03c2",
)


def derive(inputs: tuple[str, ...] = ORACLE_INPUTS) -> dict[str, object]:
    """Derive vectors for ``inputs`` with this interpreter's case mapping."""
    vectors = [{"input": text, "upper": text.upper(), "lower": text.lower()} for text in inputs]
    return {"unicodeVersion": unicodedata.unidata_version, "vectors": vectors}


def main() -> int:
    """Print the derived vectors as compact JSON."""
    sys.stdout.write(json.dumps(derive(), ensure_ascii=False, sort_keys=True))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
