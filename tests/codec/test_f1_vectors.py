"""Meta-driven F1 vector tests: sealed expectations rule, never the codec."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bpmn_io.codec import hydrate, parse_xml, project, serialize_xml

VECTORS = (
    Path(__file__).resolve().parent.parent.parent / "contracts" / "f1-extensions" / "1" / "vectors"
)


def _load_meta(vector_id: str) -> dict:
    return json.loads((VECTORS / f"{vector_id}.meta.json").read_text(encoding="utf-8"))


def _vector_ids() -> list[str]:
    return sorted(p.name.removesuffix(".meta.json") for p in VECTORS.glob("*.meta.json"))


def _tuples(diagnostics: object) -> list[tuple]:
    return [(d.code, d.path, d.target) for d in diagnostics]  # type: ignore[union-attr]


def _expected(stage: dict) -> list[tuple]:
    return [
        (entry["code"], entry.get("path"), entry.get("target"))
        for entry in stage.get("diagnostics", [])
    ]


def _input_bytes(meta: dict) -> bytes | str | dict:
    """Discover the vector input by file convention (meta pins stages only)."""
    vector_id = meta["id"]
    xml = VECTORS / f"{vector_id}.input.xml"
    if xml.is_file():
        if meta.get("asBytes"):
            return xml.read_bytes()
        return xml.read_text(encoding="utf-8")
    raw = VECTORS / f"{vector_id}.input.bin"
    if raw.is_file():
        return raw.read_bytes()
    doc = VECTORS / f"{vector_id}.input.json"
    assert doc.is_file(), f"vector {vector_id} has no input file"
    return json.loads(doc.read_text(encoding="utf-8"))


def _has_input(meta: dict, suffix: str) -> bool:
    return (VECTORS / f"{meta['id']}.input.{suffix}").is_file()


def _parse_stage(meta: dict) -> object:
    source = _input_bytes(meta)
    assert not isinstance(source, dict), "XML vector carries JSON input"
    return parse_xml(source)


def _check_parse_stage(meta: dict, vector_id: str) -> object:
    """Run the sealed parse stage; return the native root (or None)."""
    stage = meta.get("parse")
    if stage is None:
        return None
    result = _parse_stage(meta)
    assert result.ok == stage["ok"], (vector_id, result.diagnostics)
    assert _tuples(result.diagnostics) == _expected(stage), vector_id
    return result.value if result.ok else None


def _check_project_stage(meta: dict, vector_id: str, root: object) -> dict | None:
    """Run the sealed project stage; return the wire dict (or None)."""
    stage = meta.get("project")
    wire_path = VECTORS / f"{vector_id}.wire.json"
    if not wire_path.is_file() or root is None:
        return None
    projected = project(root)
    assert projected.ok, (vector_id, projected.diagnostics)
    expected_wire = json.loads(wire_path.read_text(encoding="utf-8"))
    assert projected.value == expected_wire, vector_id
    if stage is not None:
        assert _tuples(projected.diagnostics) == _expected(stage), vector_id
    return expected_wire


def _check_hydrate_stage(meta: dict, vector_id: str, wire: dict | None) -> object:
    """Run the sealed hydrate stage; return the native tree (or None)."""
    stage = meta.get("hydrate")
    if stage is not None and wire is not None:
        return _check_wire_hydrate(stage, vector_id, wire)
    if stage is not None and wire is None and _has_input(meta, "json"):
        return _check_json_hydrate(stage, meta, vector_id)
    return None


def _check_wire_hydrate(stage: dict, vector_id: str, wire: dict) -> object:
    """Hydrate one sealed wire and reproject (round-trip identity)."""
    hydrated = hydrate(wire)
    assert hydrated.ok == stage["ok"], (vector_id, hydrated.diagnostics)
    assert _tuples(hydrated.diagnostics) == _expected(stage), vector_id
    if not hydrated.ok:
        return None
    native = hydrated.value
    again = project(native)
    assert again.ok
    assert again.value == wire, vector_id
    return native


def _check_json_hydrate(stage: dict, meta: dict, vector_id: str) -> object:
    """Hydrate one sealed JSON input and reproject when silent."""
    data = _input_bytes(meta)
    assert isinstance(data, dict), vector_id
    hydrated = hydrate(data)
    assert hydrated.ok == stage["ok"], (vector_id, hydrated.diagnostics)
    assert _tuples(hydrated.diagnostics) == _expected(stage), vector_id
    if not hydrated.ok:
        return None
    native = hydrated.value
    if hydrated.diagnostics == ():
        reprojected = project(native)
        assert reprojected.ok, (vector_id, reprojected.diagnostics)
        assert reprojected.value == data, vector_id
    return native


def _check_serialize_stage(meta: dict, vector_id: str, native: object, root: object) -> None:
    """Run the sealed serialize stage against the frozen F7 bytes."""
    stage = meta.get("serialize")
    if stage is None or (native is None and root is None):
        return
    selected = native if native is not None else root
    serialized = serialize_xml(selected)
    assert serialized.ok == stage["ok"], (vector_id, serialized.diagnostics)
    assert _tuples(serialized.diagnostics) == _expected(stage), vector_id
    f7_path = VECTORS / f"{vector_id}.f7.xml"
    if f7_path.is_file() and serialized.ok and stage.get("f7Expect", "equal") == "equal":
        assert serialized.value == f7_path.read_text(encoding="utf-8"), vector_id


@pytest.mark.parametrize("vector_id", _vector_ids())
def test_vector_stages(vector_id: str) -> None:
    """Every sealed stage behaves as its meta pins (ok + code/path/target)."""
    meta = _load_meta(vector_id)
    if meta.get("kind") == "c14n":
        pytest.skip("canonical-form unit vector (see test_utf16_ordering)")
    root = _check_parse_stage(meta, vector_id)
    wire = _check_project_stage(meta, vector_id, root)
    native = _check_hydrate_stage(meta, vector_id, wire)
    _check_serialize_stage(meta, vector_id, native, root)


def test_vector_wire_files_match_metas() -> None:
    """Every meta with XML input and ok parse/hydrate pins its wire file."""
    for vector_id in _vector_ids():
        meta = _load_meta(vector_id)
        if meta.get("kind") == "c14n":
            continue
        if not _has_input(meta, "xml"):
            continue
        parse = meta.get("parse", {})
        hydrate_stage = meta.get("hydrate", {"ok": True})
        if parse.get("ok") and hydrate_stage.get("ok", True):
            assert (VECTORS / f"{vector_id}.wire.json").is_file(), vector_id


def test_inherit_reference_identity() -> None:
    """Hydrated typed references alias the indexed targets with parents set."""
    wire = json.loads((VECTORS / "inherit-01.wire.json").read_text(encoding="utf-8"))
    hydrated = hydrate(wire)
    assert hydrated.ok, hydrated.diagnostics
    root = hydrated.value
    process = root.get("rootElements")[0]
    task = next(e for e in process.get("flowElements") if e.get("id") == "T1")
    flows = {e.get("id"): e for e in process.get("flowElements") if e.type_.startswith("bpmn:")}
    assert task.get("incoming") == [flows["F1"]]
    assert task.get("outgoing") == [flows["F2"]]
    assert flows["F1"].get("sourceRef") is task
    assert flows["F1"].get("targetRef") is task
    assert task.parent_ is process
    assert flows["F1"].parent_ is process


def test_descriptors_empty_map_accepted() -> None:
    """A valid empty descriptor map parses exactly like the default model."""
    xml = (VECTORS / "decl-01.input.xml").read_text(encoding="utf-8")
    default = parse_xml(xml)
    injected = parse_xml(xml, descriptors={})
    assert default.ok
    assert injected.ok
    assert project(default.value).value == project(injected.value).value


def test_invalid_descriptors_refuse() -> None:
    """Malformed injected descriptors refuse with descriptor-mismatch."""
    xml = (VECTORS / "decl-01.input.xml").read_text(encoding="utf-8")
    result = parse_xml(xml, descriptors={"broken": {"name": "broken"}})  # type: ignore[dict-item]
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["descriptor-mismatch"]
    hydrated = hydrate({"$type": "$any"}, descriptors="nope")  # type: ignore[arg-type]
    assert not hydrated.ok
    assert hydrated.diagnostics[0].code == "descriptor-mismatch"


def test_inputs_immutable() -> None:
    """Hydration never mutates its input (deep-frozen comparison)."""
    import copy

    data = json.loads((VECTORS / "neutral-ext-01.wire.json").read_text(encoding="utf-8"))
    snapshot = copy.deepcopy(data)
    hydrated = hydrate(data)
    assert hydrated.ok, hydrated.diagnostics
    assert data == snapshot


def test_project_does_not_mutate_tree() -> None:
    """Projection reads only: no lazy collections materialize on the tree."""
    from bpmn_io.codec import parse_xml as _parse

    root = _parse((VECTORS / "decl-01.input.xml").read_text(encoding="utf-8")).value
    before = {id(e): dict(vars(e)) for e in _walk(root)}
    projected = project(root)
    assert projected.ok
    after = {id(e): dict(vars(e)) for e in _walk(root)}
    assert before.keys() == after.keys()
    for key, entry in before.items():
        assert set(entry) == set(after[key]), key


def _walk(root: object) -> list:
    seen: list = []
    stack = [root]
    while stack:
        element = stack.pop()
        seen.append(element)
        raw = vars(element)
        children = raw.get("$children")
        if isinstance(children, list):
            stack.extend(children)
        descriptor = getattr(element, "descriptor_", None)
        for prop in getattr(descriptor, "properties", []) or []:
            value = raw.get(prop.name)
            if value is None:
                continue
            if isinstance(value, list):
                stack.extend(v for v in value if hasattr(v, "descriptor_"))
            elif hasattr(value, "descriptor_"):
                stack.append(value)
    return seen


@pytest.mark.xfail(
    strict=True,
    reason=(
        "F1 plan rev d writer rule vs literal-port transcription: upstream escapeAttr "
        "covers lone `'` (tests/upstream/moddle-xml/lib/write.js) while the Python "
        "port merged it into a two-character alternative; the Node oracle stays "
        "authoritative for escaping"
    ),
)
def test_port_apostrophe_escaping_matches_oracle() -> None:
    """Sealed divergence: Python F7 must equal the Node oracle bytes (xfails today)."""
    xml = (VECTORS / "entity-upper-01.input.xml").read_text(encoding="utf-8")
    serialized = serialize_xml(parse_xml(xml).value)
    expected = (VECTORS / "entity-upper-01.f7.xml").read_text(encoding="utf-8")
    assert serialized.ok
    assert serialized.value == expected
