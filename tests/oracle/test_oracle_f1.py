"""Live differential tests against the pinned Node reference (oracle marker)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from bpmn_io.codec import hydrate, parse_xml, project, serialize_xml

ORACLE = Path(__file__).resolve().parent / "f1_references.mjs"
VECTORS = (
    Path(__file__).resolve().parent.parent.parent / "contracts" / "f1-extensions" / "1" / "vectors"
)
MIWG = Path(__file__).resolve().parent.parent.parent / "contracts" / "f1-extensions" / "1" / "miwg"

pytestmark = pytest.mark.oracle


def _node_available() -> bool:
    return (
        shutil.which("node") is not None
        and (ORACLE.parent / "node_modules").is_dir()
        and ORACLE.is_file()
    )


def _node_executable() -> str:
    """Full path to node, asserting the oracle prerequisite (mirrors _bridge)."""
    exe = shutil.which("node")
    assert exe is not None, "oracle needs node on PATH"
    return exe


def _call(payload: dict) -> dict:
    data = json.dumps(payload)
    proc = subprocess.run(  # noqa: S603 — fixed argv ([node, runner, JSON]), no shell.
        [_node_executable(), str(ORACLE), data],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=ORACLE.parent,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


def _xml_vector_ids() -> list[str]:
    return sorted(p.name.removesuffix(".input.xml") for p in VECTORS.glob("*.input.xml"))


@pytest.mark.parametrize("vector_id", _xml_vector_ids())
def test_oracle_wire_parity(vector_id: str) -> None:
    """Node wire output equals the Python projection for every XML vector."""
    if not _node_available():
        pytest.skip("oracle needs node and `npm ci` in tests/oracle")
    xml = (VECTORS / f"{vector_id}.input.xml").read_text(encoding="utf-8")
    env = _call({"op": "wire", "xml": xml})
    assert env["ok"], (vector_id, env)
    parsed = parse_xml(xml)
    if not parsed.ok:
        # Boundary refusal: no Python tree exists; refusal is pinned in test_f1_vectors.
        return
    assert project(parsed.value).value == env["result"]["root"], vector_id


@pytest.mark.parametrize("vector_id", _xml_vector_ids())
def test_oracle_f7_parity(vector_id: str) -> None:
    """Node writer bytes equal Python F7 bytes wherever both encode."""
    if not _node_available():
        pytest.skip("oracle needs node and `npm ci` in tests/oracle")
    if vector_id == "entity-upper-01":
        pytest.skip("sealed literal-port divergence (strict xfail in test_f1_vectors)")
    xml = (VECTORS / f"{vector_id}.input.xml").read_text(encoding="utf-8")
    env = _call({"op": "serialize", "xml": xml, "format": False, "preamble": True})
    parsed = parse_xml(xml)
    if not parsed.ok:
        # Boundary refusal: the literal Node reference has no adapter to compare.
        return
    serialized = serialize_xml(parsed.value)
    if not env["ok"]:
        assert not serialized.ok, vector_id
        return
    if not serialized.ok:
        return
    assert serialized.value == env["result"]["xml"], vector_id


def test_oracle_prefix_generation_parity() -> None:
    """Generated prefixes match byte-for-byte on a hydratable generic tree."""
    if not _node_available():
        pytest.skip("oracle needs node and `npm ci` in tests/oracle")
    data = json.loads((VECTORS / "prefix-gen-01.input.json").read_text(encoding="utf-8"))
    env = _call({"op": "genericSerialize", "root": data, "format": False, "preamble": True})
    assert env["ok"], env
    hydrated = hydrate(data)
    assert hydrated.ok
    serialized = serialize_xml(hydrated.value)
    assert serialized.ok
    assert serialized.value == env["result"]["xml"]


@pytest.mark.parametrize("name", ["B.1.0", "C.4.0", "C.5.0"])
def test_oracle_miwg_wire_parity(name: str) -> None:
    """MIWG projections match the Node reference on every original."""
    if not _node_available():
        pytest.skip("oracle needs node and `npm ci` in tests/oracle")
    raw = (MIWG / f"{name}.bpmn").read_bytes()
    text = raw.decode("latin1") if name == "B.1.0" else raw.decode("utf-8")
    env = _call({"op": "wire", "xml": text})
    assert env["ok"], (name, env)
    parsed = parse_xml(raw)
    assert parsed.ok, (name, parsed.diagnostics)
    assert project(parsed.value).value == env["result"]["root"], name
