"""Differential lexical tests against the independent Node reference.

Expectations are produced by ``tests/oracle/profile_references.mjs``
(``lexical`` op, same ``parseStrict`` lineage as DESIGN R3.3 §2.1.1) at test
time; the Python side must agree exactly. Needs node plus ``npm ci`` in
``tests/oracle``; skips otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ORACLE_DIR = Path(__file__).parent
ORACLE_SCRIPT = ORACLE_DIR / "profile_references.mjs"

VECTORS = [
    '\u0085{"x":1e400}',
    '{"x":1e400}',
    '{"x":1e400,"x":0}',
    '{"x":0,"x":1e400}',
    '{"x":1} true',
    '\u00a0{"a":1}',
    '{"a":1}',
    "{}",
    "[]",
    "[1,[2,3]]",
    '{"x":"\\ud800"}',
    '{"x":0,"x":"\\ud800"}',
]


def _node_lexical(node_exe: str, text: str) -> dict[str, object]:
    """Run one oracle ``lexical`` call, returning its JSON verdict."""
    import json

    hexed = text.encode().hex()
    proc = subprocess.run(  # noqa: S603 - fixed argv ([node, script, flags]), no shell.
        [node_exe, str(ORACLE_SCRIPT), "lexical", "--hex", hexed],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=ORACLE_DIR,
        check=False,
    )
    if proc.returncode != 0:
        msg = "oracle lexical call failed"
        raise RuntimeError(msg)
    result = json.loads(proc.stdout)
    if not isinstance(result, dict):
        msg = "oracle lexical call misbehaved"
        raise TypeError(msg)
    return result


@pytest.mark.oracle
def test_lexical_matches_node_reference() -> None:
    """Every vector yields the same status and code on both runtimes."""
    from bpmn_io.profile import check_lexical

    node_exe = shutil.which("node")
    if node_exe is None or not (ORACLE_DIR / "node_modules").is_dir():
        pytest.skip("oracle needs node and `npm ci` in tests/oracle")
    for text in VECTORS:
        wanted = _node_lexical(node_exe, text)
        result = check_lexical(text.encode())
        if result.status == "ok":
            assert wanted == {"status": "ok"}, text
        else:
            assert wanted == {"status": "refused", "code": result.code}, text
