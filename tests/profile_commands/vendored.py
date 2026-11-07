"""Vendored JS parity runner for lot-5 harness records (binding spec 9.1).

Executes one harness record through the public API: the record profile
compiled with its vendored registry, base, descriptors and asset bag, a
bridge session over the snapshot input with the archived presentation
importedDi, then the command artifact (transaction, sequence, queries,
compile or lot-3 script). Twin comparison resolves ``$unsealed`` members
to the actual, ``$equals`` pointers inside the twin/input documents, and
the l3 relation markers over actual step results.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tests.profile_commands.harness import EXPECTED

if TYPE_CHECKING:
    from bpmn_io.profile import HeadlessBridge

VENDOR = EXPECTED / "vendor" / "js"
ROOT = EXPECTED.parent.parent.parent
SCHEMA_BYTES = (
    ROOT / "contracts" / "profile-mechanism" / "1" / "profile-mechanism-1.schema.json"
).read_bytes()

Json = Any

LOT5_DEFAULTS = {
    "registry": "lot5-ui/expectations/fixtures/ui-neutral-registry.json",
    "base": "lot5-ui/expectations/fixtures/ui-neutral-base.json",
    "descriptors": "lot5-ui/expectations/fixtures/ui-neutral-descriptors.json",
    "assets": {
        "fixtures/ui-neutral-metrics.json": "lot5-ui/expectations/fixtures/ui-neutral-metrics.json"
    },
}


def read_record(stem: str) -> dict[str, Json]:
    """Load one vendored harness record by stem."""
    value = json.loads((EXPECTED / f"{stem}.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def vendored_stems() -> list[str]:
    """Return every vendored harness stem (profile carries a vendored path)."""
    found = []
    for path in sorted(EXPECTED.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            continue
        profile = value.get("profile")
        if isinstance(profile, dict) and "vendored" in profile:
            found.append(path.stem)
    return found


def _read_vendored(base: Path, ref: dict[str, Json]) -> bytes:
    """Read one vendored file, verifying its pinned sha256."""
    raw = (base / ref["vendored"]).read_bytes()
    want = ref["sha256"]
    assert isinstance(want, str)
    got = hashlib.sha256(raw).hexdigest()
    assert got == want, f"{ref['vendored']}: sha {got} != {want}"
    return raw


def _read_artifact(base: Path, entry: dict[str, Json]) -> Json:
    """Read one input artifact (file with sha, or inline JSON)."""
    if "path" in entry:
        raw = (base / entry["path"]).read_bytes()
        want = entry.get("sha256")
        if isinstance(want, str):
            got = hashlib.sha256(raw).hexdigest()
            assert got == want, f"{entry['path']}: sha {got} != {want}"
        return json.loads(raw.decode("utf-8"))
    return copy.deepcopy(entry.get("json"))


class VSession:
    """One live vendored parity session."""

    def __init__(self, record: dict[str, Json]) -> None:
        self.record = record
        self.base = EXPECTED / record["input"]["pathBase"]
        self.bridge: HeadlessBridge | None = None
        self.compiled: Any = None
        self.identity: dict[str, Json] = {}
        self.events: list[Json] = []
        self.listeners: dict[str, list[Json]] = {}
        self.step_results: dict[int, Json] = {}


def _session_inputs(
    entry: dict[str, Json], base: Path, record: dict[str, Json]
) -> tuple[Json, list[Json], dict[str, bytes]]:
    """Resolve base, descriptors and assets of one session input artifact."""
    spec = entry["json"]
    if "base" in spec:
        base_doc = json.loads((base / spec["base"]["path"]).read_bytes().decode("utf-8"))
    else:
        profile_dir = (EXPECTED / record["profile"]["vendored"]).parent
        candidates = sorted(profile_dir.glob("*-base.json"))
        assert len(candidates) == 1, f"ambiguous session base: {candidates}"
        base_doc = json.loads(candidates[0].read_bytes().decode("utf-8"))
    descriptors = [
        {
            "name": spec["descriptors"]["path"],
            "bytes": (base / spec["descriptors"]["path"]).read_bytes(),
        }
    ]
    metrics_path = spec["metrics"]["path"]
    assets = {Path(metrics_path).name: (base / metrics_path).read_bytes()}
    return base_doc, descriptors, assets


def _role_inputs(entry: dict[str, Json], base: Path) -> tuple[Json, list[Json], dict[str, bytes]]:
    """Resolve base, descriptors and assets of one compile-inputs artifact."""
    spec = entry["json"]
    base_doc = json.loads((base / spec["base"]).read_bytes().decode("utf-8"))
    descriptors = [
        {"name": name, "bytes": (base / name).read_bytes()} for name in spec.get("descriptors", [])
    ]
    assets = {Path(name).name: (base / name).read_bytes() for name in spec.get("assets", [])}
    return base_doc, descriptors, assets


def _compile_inputs(
    record: dict[str, Json], base: Path
) -> tuple[Json, Json, list[Json], dict[str, bytes]]:
    """Resolve registry, base, descriptors and asset bag of one record."""
    registry: Json = None
    base_doc: Json = None
    descriptors: list[Json] = []
    assets: dict[str, bytes] = {}
    for entry in record["input"].get("inputArtifacts", []):
        role = entry.get("role")
        if role == "registry":
            registry = _read_artifact(base, entry)
        elif role == "session":
            resolved = _session_inputs(entry, base, record)
            base_doc, session_descriptors, session_assets = resolved
            descriptors.extend(session_descriptors)
            assets.update(session_assets)
        elif role == "compile-inputs":
            resolved = _role_inputs(entry, base)
            base_doc, role_descriptors, role_assets = resolved
            descriptors.extend(role_descriptors)
            assets.update(role_assets)
    vendor_root = EXPECTED / "vendor" / "js"
    if registry is None and not descriptors:
        registry = json.loads(
            (vendor_root / LOT5_DEFAULTS["registry"]).read_bytes().decode("utf-8")
        )
    if base_doc is None:
        base_doc = json.loads((vendor_root / LOT5_DEFAULTS["base"]).read_bytes().decode("utf-8"))
    if not descriptors:
        descriptors = [
            {
                "name": LOT5_DEFAULTS["descriptors"],
                "bytes": (vendor_root / LOT5_DEFAULTS["descriptors"]).read_bytes(),
            }
        ]
    if not assets:
        for path in LOT5_DEFAULTS["assets"].values():
            assets[Path(path).name] = (vendor_root / path).read_bytes()
    return registry, base_doc, descriptors, assets


def make_vsession(record: dict[str, Json]) -> VSession:
    """Build one vendored session (load, compile, snapshot load, activate)."""
    from bpmn_io.profile import (
        compile_profile,
        complete_envelope,
        create_bridge,
        create_descriptor_context,
        load_profile,
    )
    from bpmn_io.profile._ui import compiled_identity

    session = VSession(record)
    base = session.base
    profile_bytes = _read_vendored(EXPECTED, record["profile"])
    profile_doc = json.loads(profile_bytes.decode("utf-8"))
    registry, base_doc, descriptors, assets = _compile_inputs(record, base)
    pins = [
        {"id": entry["id"], "version": entry["version"], "sha256": entry["sha256"]}
        for entry in profile_doc.get("descriptors", [])
    ]
    packages = []
    for bundle in descriptors:
        package_pin = next(
            (pin for pin in pins if pin["sha256"] == hashlib.sha256(bundle["bytes"]).hexdigest()),
            pins[0] if len(pins) == 1 else None,
        )
        assert package_pin is not None, f"no pin matches {bundle['name']}"
        packages.append({**package_pin, "descriptorBytes": bundle["bytes"]})
    context_result = create_descriptor_context(packages)
    assert context_result.status == "ok", context_result
    load_result = load_profile(
        profile_bytes,
        schema_bytes=SCHEMA_BYTES,
        descriptor_pins=pins,
        base_bytes=_raw_base_bytes(record, base),
        asset_bag=assets or None,
        registry=registry,
    )
    assert load_result.status == "ok", load_result
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[union-attr]
        descriptor_context=context_result.payload,  # type: ignore[union-attr]
        base=copy.deepcopy(base_doc),
    )
    if compile_result.status != "ok":
        session.compile_refusal = compile_result  # type: ignore[attr-defined]
        return session
    session.compiled = compile_result.payload  # type: ignore[union-attr]
    session.identity = compiled_identity(session.compiled)
    snapshot = None
    for entry in record["input"].get("inputArtifacts", []):
        if entry.get("role") == "snapshot":
            snapshot = _read_artifact(base, entry)
    if snapshot is None:
        session.bridge = create_bridge(context_result.payload)  # type: ignore[union-attr]
        return session
    bridge = create_bridge(context_result.payload)  # type: ignore[union-attr]
    envelope = complete_envelope(
        session.identity,
        snapshot["envelope"]["tree"],
        snapshot["envelope"].get("bindings", []),
    )
    loaded = bridge.set_definitions(
        envelope, imported_di=copy.deepcopy(snapshot["presentation"]["importedDi"])
    )
    assert loaded.status == "ok", loaded
    activated = bridge.activate_business_profile(session.compiled)
    assert activated.status == "ok", activated
    collected: list[Json] = []
    session.events = collected
    bridge.on_change(collected.append)
    session.bridge = bridge
    return session


def _raw_base_bytes(record: dict[str, Json], base: Path) -> bytes:
    """Return the raw base bytes of one record (compile-inputs or default)."""
    vendor_root = EXPECTED / "vendor" / "js"
    for entry in record["input"].get("inputArtifacts", []):
        if entry.get("role") == "compile-inputs":
            return (base / entry["json"]["base"]).read_bytes()
        if entry.get("role") == "session":
            spec = entry["json"]
            if "base" in spec:
                return (base / spec["base"]["path"]).read_bytes()
            profile_dir = (EXPECTED / record["profile"]["vendored"]).parent
            candidates = sorted(profile_dir.glob("*-base.json"))
            assert len(candidates) == 1, f"ambiguous session base: {candidates}"
            return candidates[0].read_bytes()
    return (vendor_root / LOT5_DEFAULTS["base"]).read_bytes()


def _resolve_at_current(value: Json, session: VSession) -> Json:
    """Replace ``@current`` view markers with the live viewRevision."""
    assert session.bridge is not None
    if value == "@current":
        snapshot = session.bridge.get_snapshot()
        assert snapshot.status == "ok", snapshot
        payload = snapshot.payload  # type: ignore[union-attr]
        assert isinstance(payload, dict)
        return payload["viewRevision"]
    if isinstance(value, dict):
        return {key: _resolve_at_current(entry, session) for key, entry in value.items()}
    if isinstance(value, list):
        return [_resolve_at_current(entry, session) for entry in value]
    return value


def _command_signal(command: Json) -> Json:
    """Return the cancellation signal of one command artifact (or None).

    The sealed ``"signal": "aborted"`` form aborts at the first poll;
    any other form runs uncancelled.
    """
    if isinstance(command, dict) and command.get("signal") == "aborted":
        return lambda: True
    return None


def _run_headless(session: VSession, action: str, request: Json, signal: Json = None) -> Json:
    """Run one headless action; returns the result in ``to_json()`` form."""
    assert session.bridge is not None
    bridge = session.bridge
    resolved = _resolve_at_current(copy.deepcopy(request or {}), session)
    calls = {
        "applyCommands": lambda: bridge.apply_commands(
            base_revision=resolved["baseRevision"],
            expected_view_revision=resolved["expectedViewRevision"],
            commands=resolved["commands"],
            transaction_id=resolved["transactionId"],
            signal=signal,
            codec=None,
        ).to_json(),
        "undo": lambda: bridge.undo(
            expected_revision=resolved["expectedRevision"],
            expected_view_revision=resolved["expectedViewRevision"],
        ).to_json(),
        "redo": lambda: bridge.redo(
            expected_revision=resolved["expectedRevision"],
            expected_view_revision=resolved["expectedViewRevision"],
        ).to_json(),
        "getSnapshot": lambda: bridge.get_snapshot().to_json(),
        "checkField": lambda: bridge.check_field(
            base_revision=resolved["baseRevision"],
            target_id=resolved["targetId"],
            field_id=resolved["fieldId"],
            value=resolved.get("value"),
        ).to_json(),
        "copy": lambda: bridge.copy(
            base_revision=resolved["baseRevision"],
            element_ids=resolved["elementIds"],
        ).to_json(),
        "listEntries": lambda: bridge.list_entries(
            base_revision=resolved["baseRevision"],
            surface=resolved["surface"],
            subject=resolved.get("subject"),
            locale=resolved["locale"],
        ).to_json(),
        "listFields": lambda: bridge.list_fields(
            base_revision=resolved["baseRevision"],
            target_id=resolved["targetId"],
            locale=resolved["locale"],
        ).to_json(),
        "queryReferences": lambda: bridge.query_references(
            base_revision=resolved["baseRevision"],
            target_id=resolved["targetId"],
            field_id=resolved["fieldId"],
            query=resolved["query"],
            offset=resolved["offset"],
            limit=resolved["limit"],
        ).to_json(),
    }
    if action not in calls:
        message = f"unknown vendored action {action!r}"
        raise AssertionError(message)
    return calls[action]()


def _resolve_pointer(document: Json, pointer: str) -> Json:
    """Resolve one RFC 6901 pointer inside a JSON document."""
    node = document
    if pointer == "":
        return node
    for raw in pointer.split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _current_view(session: VSession) -> Json:
    """Return the live viewRevision of one session."""
    assert session.bridge is not None
    snapshot = session.bridge.get_snapshot()
    assert snapshot.status == "ok", snapshot
    payload = snapshot.payload  # type: ignore[union-attr]
    assert isinstance(payload, dict)
    return payload["viewRevision"]


def _current_revision(session: VSession) -> Json:
    """Return the live semanticRevision of one session."""
    assert session.bridge is not None
    stored = session.bridge.get_definitions()
    assert stored.status == "ok", stored
    payload = stored.payload  # type: ignore[union-attr]
    assert isinstance(payload, dict)
    return payload["semanticRevision"]


def run_transaction(session: VSession, record: dict[str, Json]) -> Json:
    """Run one transaction command artifact with its twin history."""
    assert session.bridge is not None
    command = None
    for entry in record["input"].get("inputArtifacts", []):
        if entry.get("role") == "transaction":
            command = entry["json"]
    if command is None:
        artifact = record["input"].get("commandArtifact")
        if isinstance(artifact, dict) and artifact.get("role") == "transaction":
            command = artifact["json"]
    assert command is not None, "no transaction command artifact"
    mark = len(session.events)
    request = _resolve_at_current(copy.deepcopy(command), session)
    # Twin replay liveness: the pinned JS-live `expectedViewRevision` cannot
    # survive the specified reload (layout recomputes from the archived
    # `importedDi`; synthesis is forbidden by render §4/§19 and snapshot
    # restoration is out of scope per commands §13). Resolve it against the
    # reloaded session like `@current`; the pinned `baseRevision` stays exact
    # so the revision guard is still tested byte-for-byte.
    request["expectedViewRevision"] = _current_view(session)
    result = _run_headless(session, "applyCommands", request, _command_signal(command))
    events = copy.deepcopy(session.events[mark:])
    payload = result.get("payload") if isinstance(result, dict) else None
    if (
        isinstance(result, dict)
        and result.get("status") == "ok"
        and isinstance(payload, dict)
        and payload.get("changed") is True
    ):
        undo_mark = len(session.events)
        undo_result = session.bridge.undo(
            expected_revision=_current_revision(session),
            expected_view_revision=_current_view(session),
        ).to_json()
        undo_events = copy.deepcopy(session.events[undo_mark:])
        redo_mark = len(session.events)
        redo_payload = undo_result.get("payload") if isinstance(undo_result, dict) else None
        redo_result = session.bridge.redo(
            expected_revision=undo_result.get("revision", ""),
            expected_view_revision=(redo_payload or {}).get("viewRevision", ""),
        ).to_json()
        redo_events = copy.deepcopy(session.events[redo_mark:])
        history: Json = {
            "undo": {"events": undo_events, "result": undo_result},
            "redo": {"events": redo_events, "result": redo_result},
        }
    else:
        probe_mark = len(session.events)
        probe = session.bridge.undo(
            expected_revision=_current_revision(session),
            expected_view_revision=_current_view(session),
        ).to_json()
        probe_events = copy.deepcopy(session.events[probe_mark:])
        history = {"probe": probe, "probeEvents": probe_events}
    return {"result": result, "events": events, "history": history}


def make_script_session(record: dict[str, Json]) -> VSession:
    """Build one lot-3 script session (profile, descriptors, metrics, base)."""
    from bpmn_io.profile import (
        compile_profile,
        create_bridge,
        create_descriptor_context,
        load_profile,
    )
    from bpmn_io.profile._ui import compiled_identity

    session = VSession(record)
    base = session.base
    (spec,) = [
        entry["json"]
        for entry in record["input"].get("inputArtifacts", [])
        if entry.get("role") == "session"
    ]
    profile_ref = spec["profile"]
    profile_bytes = (base / profile_ref["path"]).read_bytes()
    assert hashlib.sha256(profile_bytes).hexdigest() == profile_ref["sha256"]
    desc_ref = spec["descriptors"]
    desc_bytes = (base / desc_ref["path"]).read_bytes()
    assert hashlib.sha256(desc_bytes).hexdigest() == desc_ref["sha256"]
    metrics_ref = spec["metrics"]
    metrics_bytes = (base / metrics_ref["path"]).read_bytes()
    assert hashlib.sha256(metrics_bytes).hexdigest() == metrics_ref["sha256"]
    profile_dir = (base / profile_ref["path"]).parent
    candidates = sorted(profile_dir.glob("*-base.json"))
    assert len(candidates) == 1, f"ambiguous script base: {candidates}"
    base_bytes = candidates[0].read_bytes()
    profile_doc = json.loads(profile_bytes.decode("utf-8"))
    pins = [
        {key: entry[key] for key in ("id", "version", "sha256")}
        for entry in profile_doc.get("descriptors", [])
    ]
    packages = [
        {**pin, "descriptorBytes": desc_bytes}
        for pin in pins
        if pin["sha256"] == hashlib.sha256(desc_bytes).hexdigest()
    ]
    assert packages, "no pin matches the session descriptors"
    context_result = create_descriptor_context(packages)
    assert context_result.status == "ok", context_result
    load_result = load_profile(
        profile_bytes,
        schema_bytes=SCHEMA_BYTES,
        base_bytes=base_bytes,
        descriptor_pins=pins,
        asset_bag={Path(metrics_ref["path"]).name: metrics_bytes},
    )
    assert load_result.status == "ok", load_result
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[union-attr]
        descriptor_context=context_result.payload,  # type: ignore[union-attr]
        base=json.loads(base_bytes.decode("utf-8")),
    )
    assert compile_result.status == "ok", compile_result
    session.compiled = compile_result.payload  # type: ignore[union-attr]
    session.identity = compiled_identity(session.compiled)
    session.bridge = create_bridge(context_result.payload)  # type: ignore[union-attr]
    return session


#: Read-only query actions seal no listener slice (they emit nothing).
_READ_ONLY_ACTIONS = ("listEntries", "listFields", "checkField", "queryReferences", "copy")


def run_sequence(session: VSession, record: dict[str, Json]) -> Json:
    """Run one sequence command artifact, one observation per step."""
    command = None
    for entry in record["input"].get("inputArtifacts", []):
        if entry.get("role") == "sequence":
            command = entry["json"]
    if command is None:
        artifact = record["input"].get("commandArtifact")
        if isinstance(artifact, dict) and artifact.get("role") == "sequence":
            command = artifact["json"]
    assert command is not None, "no sequence command artifact"
    observations = []
    for item in command.get("steps", []):
        mark = len(session.events)
        request = _resolve_at_current(copy.deepcopy(item.get("request", {})), session)
        if item["action"] == "applyCommands":
            # Same twin replay liveness as transactions: the pinned JS-live
            # view cannot survive reload; the pinned base revision stays exact.
            request["expectedViewRevision"] = _current_view(session)
        result = _run_headless(session, item["action"], request)
        observation: dict[str, Json] = {
            "step": item.get("step"),
            "result": result,
        }
        # Every mutating step seals its slice, empty when it emits nothing.
        if item["action"] not in _READ_ONLY_ACTIONS:
            observation["events"] = copy.deepcopy(session.events[mark:])
        observations.append(observation)
    return {"steps": observations}


_QUERY_ROLES = {
    "queries": None,
    "listEntries": "listEntries",
    "listFields": "listFields",
    "checkField": "checkField",
    "queryReferences": "queryReferences",
    "copy": "copy",
}


def run_queries(session: VSession, record: dict[str, Json]) -> Json:
    """Run every query input artifact, one result per query."""
    results = []
    for entry in record["input"].get("inputArtifacts", []):
        action = _QUERY_ROLES.get(entry.get("role", ""), "skip")
        if action is None:
            results.extend(_run_query_object(session, query) for query in entry["json"])
        elif action != "skip":
            results.extend(_run_headless(session, action, query) for query in entry["json"])
    return {"result": results}


def _run_query_object(session: VSession, query: Json) -> Json:
    """Run one role-queries member, dispatching on its argument shape."""
    if not isinstance(query, dict):
        message = f"query artifact is not an object: {query!r}"
        raise TypeError(message)
    if "surface" in query:
        return _run_headless(session, "listEntries", query)
    if "fieldId" in query and "query" in query:
        return _run_headless(session, "queryReferences", query)
    if "fieldId" in query:
        return _run_headless(session, "checkField", query)
    if "elementIds" in query:
        return _run_headless(session, "copy", query)
    if "targetId" in query:
        return _run_headless(session, "listFields", query)
    message = f"cannot dispatch query artifact: {sorted(query.keys())}"
    raise AssertionError(message)


def _resolve_l3_refs(value: Json, results: dict[int, Json]) -> Json:
    """Resolve ``$ref`` markers of one l3 request against step results."""
    if isinstance(value, dict):
        if set(value.keys()) == {"$ref"}:
            ref = value["$ref"]
            return copy.deepcopy(_resolve_pointer(results[ref["step"]], ref["pointer"]))
        return {key: _resolve_l3_refs(entry, results) for key, entry in value.items()}
    if isinstance(value, list):
        return [_resolve_l3_refs(entry, results) for entry in value]
    return value


def _l3_live_view(bridge: Json) -> Json:
    """Return the live viewRevision of one lot-3 script bridge."""
    snapshot = bridge.get_snapshot().to_json()
    assert snapshot.get("status") == "ok", snapshot
    payload = snapshot.get("payload")
    assert isinstance(payload, dict)
    return payload["viewRevision"]


def _run_l3_call(
    bridge: Json, compiled: Json, call: str, item: Json, results: dict[int, Json]
) -> Json:
    """Run one non-subscription script call; returns its result JSON."""
    from bpmn_io.profile import complete_envelope

    if call == "setDefinitions":
        envelope_wire = _resolve_l3_refs(item["envelope"], results)
        envelope = complete_envelope(
            envelope_wire["profileIdentity"],
            envelope_wire["tree"],
            envelope_wire.get("bindings", []),
        )
        loaded = bridge.set_definitions(envelope).to_json()
        assert loaded.get("status") == "ok", loaded
        assert compiled is not None, "script setDefinitions needs a compiled profile"
        activated = bridge.activate_business_profile(compiled).to_json()
        assert activated.get("status") == "ok", activated
        return loaded
    if call == "applyCommands":
        request = _resolve_l3_refs(item["request"], results)
        # Same twin replay liveness as transactions and sequences: a recorded
        # view chained from the pre-activation load observation (the bridge's
        # documented load exception carries the revision echo, while every
        # post-activation view is the lot-4 digest) cannot denote the live
        # view. Resolve it against the live session; the pinned baseRevision
        # stays exact so the revision guard is still tested byte-for-byte,
        # and the trace $differs/$same relations still verify view evolution.
        # Stale-view refusal stays covered by the native twins sealing a
        # wrong view (history-stale-revisions, history-undo-redo-guards).
        request["expectedViewRevision"] = _l3_live_view(bridge)
        return bridge.apply_commands(
            base_revision=request["baseRevision"],
            expected_view_revision=request["expectedViewRevision"],
            commands=request["commands"],
            transaction_id=request["transactionId"],
            signal=None,
            codec=None,
        ).to_json()
    if call == "getSnapshot":
        return bridge.get_snapshot().to_json()
    if call == "undo":
        request = _resolve_l3_refs(item.get("options", item.get("request", {})), results)
        request["expectedViewRevision"] = _l3_live_view(bridge)
        return bridge.undo(
            expected_revision=request["expectedRevision"],
            expected_view_revision=request["expectedViewRevision"],
        ).to_json()
    if call == "redo":
        request = _resolve_l3_refs(item.get("options", item.get("request", {})), results)
        request["expectedViewRevision"] = _l3_live_view(bridge)
        return bridge.redo(
            expected_revision=request["expectedRevision"],
            expected_view_revision=request["expectedViewRevision"],
        ).to_json()
    message = f"unknown script call {call!r}"
    raise AssertionError(message)


def run_l3_script(session: VSession, record: dict[str, Json]) -> Json:
    """Run one lot-3 transaction script; returns its trace observations."""
    assert session.bridge is not None
    bridge = session.bridge
    script = None
    for entry in record["input"].get("inputArtifacts", []):
        if entry.get("role") == "script":
            script = entry["json"]
    if script is None:
        artifact = record["input"].get("commandArtifact")
        if isinstance(artifact, dict) and artifact.get("role") == "script":
            script = artifact["json"]
    assert script is not None, "no script command artifact"
    assert script.get("format") == "lot3-transaction-script/2", script.get("format")
    trace = []
    results: dict[int, Json] = {}
    session.step_results = results
    for item in script.get("steps", []):
        call = item["call"]
        marks = {name: len(collected) for name, collected in session.listeners.items()}
        if call == "onChange":
            name = item["listener"]
            collected_box: list[Json] = []
            session.listeners[name] = collected_box
            result = bridge.on_change(collected_box.append).to_json()
            observation: dict[str, Json] = {"step": item["step"], "result": result}
        else:
            result = _run_l3_call(bridge, session.compiled, call, item, results)
            observation = {"step": item["step"], "result": result}
            if call != "getSnapshot":
                observation["history"] = {
                    "past": len(bridge.history),
                    "future": len(bridge.redo_history),
                }
        # Every sealed observation carries its listener slice (empty when the
        # call emits nothing); only snapshots omit the history counters.
        observation["events"] = {
            name: copy.deepcopy(session.listeners[name][marks.get(name, 0) :])
            for name in session.listeners
        }
        results[item["step"]] = observation
        trace.append(observation)
    return {"trace": trace}


def compare_l3_trace(
    actual: Json, expected: Json, unsealed: list[Json], results: dict[int, Json]
) -> None:
    """Compare one l3 trace with skips and step relations resolved."""
    from bpmn_io.profile import jcs

    skips = {entry["pointer"] for entry in unsealed if entry.get("artifact") == "trace"}
    merged = _substitute_l3(copy.deepcopy(expected), actual, results, skips, "")
    assert jcs(actual) == jcs(merged), (
        f"l3 trace differs:\nactual ={jcs(actual)[:3000]}\nmerged ={jcs(merged)[:3000]}"
    )


def _substitute_l3(
    expected: Json,
    actual: Json,
    results: dict[int, Json],
    skips: set[str],
    path: str,
) -> Json:
    """Resolve l3 skips and ``$same``/``$differs``/``$ref`` relations."""
    from bpmn_io.profile import jcs

    if path in skips or expected == "unsealed":
        return copy.deepcopy(actual)
    if isinstance(expected, dict):
        for marker in ("$same", "$differs", "$ref"):
            if set(expected.keys()) == {marker}:
                ref = expected[marker]
                target = _resolve_pointer(results[ref["step"]], ref["pointer"])
                if marker == "$differs":
                    assert jcs(actual) != jcs(target), f"differs failed at {path}"
                    return copy.deepcopy(actual)
                assert jcs(actual) == jcs(target), f"same/ref failed at {path}"
                return copy.deepcopy(actual)
        if set(expected.keys()) == {"$snapshot", "$prologue", "$step", "$initial"}:
            message = f"unsupported l3 snapshot marker at {path}"
            raise AssertionError(message)
        assert isinstance(actual, dict), f"l3 parent is not an object at {path}"
        return {
            key: _substitute_l3(entry, actual[key], results, skips, f"{path}/{key}")
            for key, entry in expected.items()
        }
    if isinstance(expected, list):
        assert isinstance(actual, list), f"l3 parent is not a list at {path}"
        assert len(expected) == len(actual), f"l3 list arity differs at {path}"
        return [
            _substitute_l3(e, a, results, skips, f"{path}/{index}")
            for index, (e, a) in enumerate(zip(expected, actual, strict=True))
        ]
    return expected


def _check_type(value: Json, want: str) -> None:
    """Check one ``$unsealed`` type annotation against the actual value."""
    kinds = {
        "string": str,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    assert want in kinds, f"unknown unsealed type {want!r}"
    assert isinstance(value, kinds[want]), f"unsealed type {want} mismatch: {value!r}"
    if want == "number":
        assert not isinstance(value, bool), f"unsealed type {want} mismatch: {value!r}"


def compare_twin(actual: Json, expected: Json, record: dict[str, Json]) -> None:
    """Compare one actual observation with its twin (markers resolved)."""
    from bpmn_io.profile import jcs

    merged = _substitute_twin(copy.deepcopy(expected), actual, record, _snapshot_document(record))
    assert jcs(actual) == jcs(merged), (
        f"twin differs:\nactual ={jcs(actual)[:3000]}\nmerged ={jcs(merged)[:3000]}"
    )


def _snapshot_document(record: dict[str, Json]) -> Json:
    """Return the vendored snapshot artifact of one record (or None)."""
    base = EXPECTED / record["input"]["pathBase"]
    for entry in record["input"].get("inputArtifacts", []):
        if entry.get("role") == "snapshot":
            return _read_artifact(base, entry)
    return None


def _substitute_twin(
    expected: Json, actual: Json, record: dict[str, Json], snapshot: Json = None
) -> Json:
    """Resolve ``$unsealed``/``$equals`` markers of one twin expectation."""
    if isinstance(expected, dict):
        if set(expected.keys()) == {"$unsealed"}:
            return copy.deepcopy(actual)
        if set(expected.keys()) == {"$unsealed", "type"}:
            _check_type(actual, expected["type"])
            return copy.deepcopy(actual)
        if set(expected.keys()) == {"$equals"}:
            ref = expected["$equals"]
            if "member" in ref:
                document = record["expected"] if ref["member"] == "twin" else record["input"]
            else:
                assert ref["input"] == "snapshot", f"unknown $equals input {ref!r}"
                assert snapshot is not None, "no snapshot artifact for $equals input"
                document = snapshot
            resolved = copy.deepcopy(_resolve_pointer(document, ref["pointer"]))
            return _substitute_twin(resolved, actual, record, snapshot)
        assert isinstance(actual, dict), f"twin parent is not an object: {expected!r}"
        return {
            key: _substitute_twin(entry, actual[key], record, snapshot)
            for key, entry in expected.items()
        }
    if isinstance(expected, list):
        assert isinstance(actual, list), f"twin parent is not a list: {expected!r}"
        assert len(expected) == len(actual), "twin list arity differs"
        return [
            _substitute_twin(e, a, record, snapshot) for e, a in zip(expected, actual, strict=True)
        ]
    return expected
