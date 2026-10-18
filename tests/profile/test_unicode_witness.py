"""Unicode version witness from independent interpreters (finding #15).

The sealed expectations in ``contracts/unicode-case/15.0.0/vectors.json`` must
equal the output of the independent oracle
(``tests/oracle/unicode_case_oracle.py``, ``str.upper``/``str.lower`` only, no
``bpmn_io`` import) run under a Unicode 15.0.0 interpreter, and the 16.0.0
interpreter must visibly diverge on the version witness. Each case skips only
when its interpreter is unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
ORACLE = ROOT / "tests" / "oracle" / "unicode_case_oracle.py"
SEALED = ROOT / "contracts" / "unicode-case" / "15.0.0" / "vectors.json"


class _NoInterpreterError(Exception):
    """The requested interpreter is not installed and cannot be fetched."""


def _run_oracle(python_version: str) -> dict[str, object]:
    """Run the independent oracle under one interpreter (skip when missing)."""
    uv = shutil.which("uv")
    if uv is None:
        raise _NoInterpreterError
    proc = subprocess.run(  # noqa: S603 - fixed argv ([uv, run, ...]), no shell.
        [uv, "run", "--no-project", "--python", python_version, "python", str(ORACLE)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=ROOT,
        check=False,
    )
    if proc.returncode != 0:
        raise _NoInterpreterError
    try:
        document = json.loads(proc.stdout)
    except ValueError as exc:
        raise _NoInterpreterError from exc
    if not isinstance(document, dict):
        raise _NoInterpreterError
    return document


def _sealed_vectors() -> list[object]:
    document = json.loads(SEALED.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    assert document["unicodeVersion"] == "15.0.0"
    vectors = document["vectors"]
    assert isinstance(vectors, list)
    return vectors


def test_vectors_sealed_from_unicode_15_oracle() -> None:
    """The 15.0.0 interpreter oracle reproduces the sealed vectors exactly."""
    try:
        document = _run_oracle("3.12")
    except _NoInterpreterError:
        pytest.skip("needs a Unicode 15.0.0 interpreter (uv python 3.12)")
    assert document["unicodeVersion"] == "15.0.0"
    assert document["vectors"] == _sealed_vectors()
    assert len(document["vectors"]) >= 10  # type: ignore[arg-type]


def test_unicode_16_diverges_on_the_version_witness() -> None:
    """The 16.0.0 interpreter maps the ram's horn witness differently."""
    try:
        document = _run_oracle("3.14")
    except _NoInterpreterError:
        pytest.skip("needs a Unicode 16.0.0 interpreter (uv python 3.14)")
    assert document["unicodeVersion"] == "16.0.0"
    vectors = document["vectors"]
    assert isinstance(vectors, list)
    by_input = {v["input"]: v for v in vectors if isinstance(v, dict)}
    witness = by_input.get("\u0264")
    assert isinstance(witness, dict)
    assert witness["upper"] == "\ua7cb"
    assert witness["lower"] == "\u0264"


def test_implementation_holds_the_15_pin_against_16() -> None:
    """The runtime keeps 15.0.0 behavior where the platform moved on."""
    from bpmn_io.profile import apply_case

    assert apply_case("\u0264", "upper") == "\u0264"
    assert apply_case("\u0264", "lower") == "\u0264"
