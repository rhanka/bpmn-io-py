"""Shared harness for the lot-5 headless command expectations.

Implements the setup of binding spec section 8.2 and the step runner of
section 8.3: descriptor context, profile load, compilation, bridge load and
activation, then one bridge call per step with ``$current``/``$saved``
placeholder resolution and ``$unsealed``-aware comparison. Imports the
library under test (unlike ``expected/derive_helper.py``, which stays
standalone).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.profile import HeadlessBridge

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "expected"
ROOT = HERE.parent.parent
CONTRACTS = ROOT / "contracts" / "profile-mechanism" / "1"
ARTIFACTS = EXPECTED / "artifacts"

SCHEMA_BYTES = (CONTRACTS / "profile-mechanism-1.schema.json").read_bytes()
BASE_BYTES = (ARTIFACTS / "neutral-base.lot5.json").read_bytes()
BASE_DOCUMENT = json.loads(BASE_BYTES.decode("utf-8"))
DEFAULT_DESCRIPTOR_BYTES = (ARTIFACTS / "neutral-descriptors.lot5.json").read_bytes()
DEFAULT_DESCRIPTOR_PIN = json.loads(
    (EXPECTED / "fixture-descriptors.json").read_text(encoding="utf-8")
)["expected"]["pin"]

Json = Any


def read_case(stem: str) -> dict[str, Json]:
    """Load one native harness expectation file by stem."""
    value = json.loads((EXPECTED / f"{stem}.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def native_stems() -> list[str]:
    """Return every native harness stem (fixtures and vendored excluded)."""
    found = []
    for path in sorted(EXPECTED.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        if path.stem.startswith("fixture-"):
            continue
        profile = value.get("profile")
        if isinstance(profile, dict) and "vendored" in profile:
            continue
        found.append(path.stem)
    return found


def apply_profile_delta(profile: dict[str, Json], delta: list[Json]) -> dict[str, Json]:
    """Apply an RFC 6902 delta (add/replace/remove/test) to a deep copy."""
    from tests.profile_commands.expected.derive_helper import apply_patch

    return apply_patch(profile, delta)  # type: ignore[return-value]


def composed_profile(case: dict[str, Json]) -> dict[str, Json]:
    """Compose the case profile (fixture composition plus case delta)."""
    profile_ref = case["input"]["profile"]
    fixture_name = profile_ref["fixture"]
    fixture = json.loads((EXPECTED / f"{fixture_name}.json").read_text(encoding="utf-8"))
    source = fixture["input"]["source"]
    from tests.profile_commands.expected.derive_helper import compose_source

    composed = compose_source(source)
    assert isinstance(composed, dict)
    return apply_profile_delta(composed, profile_ref.get("delta", []))


def profile_artifact_bytes(case: dict[str, Json]) -> bytes:
    """Return the raw committed profile bytes of one case."""
    artifact = case["input"]["profile"]["artifact"]
    return (EXPECTED / artifact).read_bytes()


class Setup:
    """The live objects of one case setup (section 8.2)."""

    def __init__(self) -> None:
        self.context: Any = None
        self.validated: Any = None
        self.compiled: Any = None
        self.identity: dict[str, Json] = {}
        self.bridge: HeadlessBridge | None = None
        self.base_revision: str = ""
        self.saved: dict[str, Json] = {}
        self.listeners: dict[str, list[Json]] = {}


def make_setup(case: dict[str, Json]) -> Setup:
    """Run the section 8.2 setup; returns live objects (no comparison)."""
    from bpmn_io.profile import (
        compile_profile,
        create_bridge,
        create_descriptor_context,
        load_profile,
    )

    setup = Setup()
    case_input = case["input"]
    bridge_input = case_input.get("bridge", {})
    packages: list[dict[str, Json]] = []
    if "descriptorPackages" in bridge_input:
        for record in bridge_input["descriptorPackages"]:
            raw = (ROOT / record["file"]).read_bytes()
            package = dict(record["pin"])
            package["descriptorBytes"] = raw
            packages.append(package)
    else:
        package = dict(DEFAULT_DESCRIPTOR_PIN)
        package["descriptorBytes"] = DEFAULT_DESCRIPTOR_BYTES
        packages = [package]
    context_result = create_descriptor_context(packages)
    assert context_result.status == "ok", context_result
    setup.context = context_result.payload
    pins = [
        {"id": entry["id"], "version": entry["version"], "sha256": entry["sha256"]}
        for entry in packages
    ]
    load_result = load_profile(
        profile_artifact_bytes(case),
        schema_bytes=SCHEMA_BYTES,
        base_bytes=BASE_BYTES,
        descriptor_pins=pins,
    )
    if load_result.status != "ok":
        setup.validated = None
        setup.load_refusal = load_result  # type: ignore[attr-defined]
        return setup
    setup.validated = load_result.payload
    compile_result = compile_profile(
        setup.validated,
        descriptor_context=setup.context,
        base=copy.deepcopy(BASE_DOCUMENT),
    )
    if compile_result.status != "ok":
        setup.compiled = None
        setup.compile_refusal = compile_result  # type: ignore[attr-defined]
        return setup
    setup.compiled = compile_result.payload
    from bpmn_io.profile._ui import compiled_identity

    setup.identity = compiled_identity(setup.compiled)
    document = case_input.get("document")
    if document is None:
        setup.bridge = create_bridge(setup.context)
        return setup
    bridge = create_bridge(setup.context)
    from bpmn_io.profile import complete_envelope

    envelope = complete_envelope(setup.identity, document["tree"], document.get("bindings", []))
    loaded = bridge.set_definitions(envelope, imported_di=document.get("importedDi"))
    setup.setup_load = loaded  # type: ignore[attr-defined]
    activated = bridge.activate_business_profile(setup.compiled)
    setup.setup_activate = activated  # type: ignore[attr-defined]
    setup.bridge = bridge
    setup.base_revision = envelope.semantic_revision
    return setup


def _resolve_pointer(document: Json, pointer: str) -> Json:
    """Resolve one RFC 6901 pointer inside a JSON document."""
    node = document
    if pointer == "":
        return node
    for raw in pointer.split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _resolve_current(setup: Setup, value: Json) -> Json:
    """Resolve ``$current``/``$saved`` placeholders inside step arguments."""
    if isinstance(value, dict):
        if set(value.keys()) == {"$current"}:
            assert setup.bridge is not None
            snapshot = setup.bridge.get_snapshot()
            assert snapshot.status == "ok", snapshot
            payload = snapshot.payload  # type: ignore[union-attr]
            assert isinstance(payload, dict)
            key = value["$current"]
            assert key in payload, key
            return copy.deepcopy(payload[key])
        if "$saved" in value:
            return copy.deepcopy(_resolve_pointer(setup.saved[value["$saved"]], value["pointer"]))
        return {key: _resolve_current(setup, entry) for key, entry in value.items()}
    if isinstance(value, list):
        return [_resolve_current(setup, entry) for entry in value]
    return value


def _make_signal(setup: Setup, spec: Json) -> Callable[[], bool]:
    """Build the sync signal callable of one step (section 8.3)."""
    assert setup.bridge is not None
    bridge = setup.bridge
    calls = {"count": 0}
    results: dict[str, list[Json]] = {}

    def _poll() -> bool:
        index = calls["count"]
        calls["count"] += 1
        kind = spec["kind"]
        if kind == "constant":
            return bool(spec["returns"])
        if kind == "sequence":
            values = spec["values"]
            return bool(values[min(index, len(values) - 1)])
        if kind == "reenter":
            for call in spec["calls"]:
                outcome = run_step(setup, {"op": call["op"], "args": call.get("args", {})})
                results.setdefault(call["op"], []).append(outcome)
            return bool(spec["returns"])
        if kind == "dispose":
            bridge.dispose()
            return bool(spec["returns"])
        message = f"unknown signal kind {kind!r}"
        raise AssertionError(message)

    poll: Callable[[], bool] = _poll
    poll.calls = calls  # type: ignore[attr-defined]
    poll.results = results  # type: ignore[attr-defined]
    return poll


def _step_apply(setup: Setup, bridge: HeadlessBridge, _step: Json, args: Json) -> Json:
    """Run one ``apply_commands`` step with its signal wiring."""
    signal_spec = args.pop("signal", None)
    signal = _make_signal(setup, signal_spec) if signal_spec is not None else None
    result = bridge.apply_commands(
        base_revision=args["baseRevision"],
        expected_view_revision=args["expectedViewRevision"],
        commands=args["commands"],
        transaction_id=args["transactionId"],
        signal=signal,
        codec=None,
    )
    actual = result.to_json()
    if signal_spec is not None:
        actual = {
            **actual,
            "__signal__": {
                "calls": signal.calls["count"],  # type: ignore[attr-defined]
                "results": signal.results,  # type: ignore[attr-defined]
            },
        }
    return actual


def _step_revision_pair(_setup: Setup, bridge: HeadlessBridge, step: Json, args: Json) -> Json:
    """Run one ``undo``/``redo`` step."""
    if step["op"] == "undo":
        result = bridge.undo(
            expected_revision=args["expectedRevision"],
            expected_view_revision=args["expectedViewRevision"],
        )
    else:
        result = bridge.redo(
            expected_revision=args["expectedRevision"],
            expected_view_revision=args["expectedViewRevision"],
        )
    return result.to_json()


def _step_snapshot(setup: Setup, bridge: HeadlessBridge, step: Json, args: Json) -> Json:
    """Run one snapshot/session query step."""
    _ = args
    op = step["op"]
    if op == "get_snapshot":
        return bridge.get_snapshot().to_json()
    if op == "get_definitions":
        return bridge.get_definitions().to_json()
    if op == "dispose":
        return bridge.dispose().to_json()
    if op == "activate":
        assert setup.compiled is not None
        return bridge.activate_business_profile(setup.compiled).to_json()
    message = f"unknown snapshot op {op!r}"
    raise AssertionError(message)


def _step_queries(setup: Setup, bridge: HeadlessBridge, step: Json, args: Json) -> Json:
    """Run one read-only query step."""
    _ = setup
    op = step["op"]
    if op == "list_entries":
        result = bridge.list_entries(
            base_revision=args["baseRevision"],
            surface=args["surface"],
            subject=args.get("subject"),
            locale=args["locale"],
        )
        return result.to_json()
    if op == "list_fields":
        result = bridge.list_fields(
            base_revision=args["baseRevision"],
            target_id=args["targetId"],
            locale=args["locale"],
        )
        return result.to_json()
    if op == "check_field":
        result = bridge.check_field(
            base_revision=args["baseRevision"],
            target_id=args["targetId"],
            field_id=args["fieldId"],
            value=args.get("value"),
        )
        return result.to_json()
    if op == "query_references":
        result = bridge.query_references(
            base_revision=args["baseRevision"],
            target_id=args["targetId"],
            field_id=args["fieldId"],
            query=args["query"],
            offset=args["offset"],
            limit=args["limit"],
        )
        return result.to_json()
    if op == "copy":
        result = bridge.copy(
            base_revision=args["baseRevision"],
            element_ids=args["elementIds"],
        )
        return result.to_json()
    message = f"unknown query op {op!r}"
    raise AssertionError(message)


def _step_load(setup: Setup, bridge: HeadlessBridge, step: Json, args: Json) -> Json:
    """Run one ``set_definitions`` step."""
    from bpmn_io.profile import complete_envelope

    _ = step
    document = args["document"]
    envelope = complete_envelope(setup.identity, document["tree"], document.get("bindings", []))
    result = bridge.set_definitions(envelope, imported_di=document.get("importedDi"))
    return result.to_json()


def _step_local(setup: Setup, bridge: HeadlessBridge, step: Json, args: Json) -> Json:
    """Run one local step (localize, listener, event dump)."""
    from bpmn_io.profile import localize as localize_fn

    _ = bridge
    op = step["op"]
    if op == "localize":
        assert setup.compiled is not None
        return localize_fn(setup.compiled, args["key"], args["locale"]).to_json()
    if op == "on_change":
        assert setup.bridge is not None
        name = args["collect"]
        collected: list[Json] = []
        setup.listeners[name] = collected
        return setup.bridge.on_change(collected.append).to_json()
    if op == "events":
        return {"events": copy.deepcopy(setup.listeners[args["name"]])}
    message = f"unknown local op {op!r}"
    raise AssertionError(message)


_STEP_GROUPS: dict[str, str] = {
    "apply_commands": "apply",
    "undo": "pair",
    "redo": "pair",
    "get_snapshot": "snapshot",
    "get_definitions": "snapshot",
    "dispose": "snapshot",
    "activate": "snapshot",
    "list_entries": "query",
    "list_fields": "query",
    "check_field": "query",
    "query_references": "query",
    "copy": "query",
    "set_definitions": "load",
    "localize": "local",
    "on_change": "local",
    "events": "local",
}


def run_step(setup: Setup, step: dict[str, Json]) -> Json:
    """Run one step; returns the actual result in ``to_json()`` form."""
    assert setup.bridge is not None
    bridge = setup.bridge
    op = step["op"]
    group = _STEP_GROUPS.get(op)
    if group is None:
        message = f"unknown step op {op!r}"
        raise AssertionError(message)
    args = _resolve_current(setup, copy.deepcopy(step.get("args", {})))
    if group == "apply":
        actual = _step_apply(setup, bridge, step, args)
    elif group == "pair":
        actual = _step_revision_pair(setup, bridge, step, args)
    elif group == "snapshot":
        actual = _step_snapshot(setup, bridge, step, args)
    elif group == "query":
        actual = _step_queries(setup, bridge, step, args)
    elif group == "load":
        actual = _step_load(setup, bridge, step, args)
    else:
        actual = _step_local(setup, bridge, step, args)
    if "save" in step:
        setup.saved[step["save"]] = actual
    return actual


def _substitute_unsealed(expected: Json, actual: Json) -> Json:
    """Replace every ``{"$unsealed": reason}`` marker with the actual member."""
    if isinstance(expected, dict):
        if set(expected.keys()) == {"$unsealed"}:
            return copy.deepcopy(actual)
        assert isinstance(actual, dict), f"marker parent is not an object: {expected!r}"
        return {key: _substitute_unsealed(entry, actual[key]) for key, entry in expected.items()}
    if isinstance(expected, list):
        assert isinstance(actual, list), f"marker parent is not a list: {expected!r}"
        assert len(expected) == len(actual), f"list arity differs: {expected!r}"
        return [_substitute_unsealed(e, a) for e, a in zip(expected, actual, strict=True)]
    return expected


def compare_result(actual: Json, expected: Json) -> None:
    """Compare one actual result with its sealed expectation (byte equality)."""
    from bpmn_io.profile import jcs

    merged = _substitute_unsealed(copy.deepcopy(expected), actual)
    assert jcs(actual) == jcs(merged), (
        f"actual != expected:\nactual  ={jcs(actual)[:3000]}\nmerged  ={jcs(merged)[:3000]}"
    )


def check_relational(setup: Setup, actual: Json, spec: dict[str, Json]) -> None:
    """Check the ``equal``/``differ`` relations of one step."""
    from bpmn_io.profile import jcs

    for entry in spec.get("equal", []):
        left = _resolve_pointer(actual, entry["pointer"])
        right = _resolve_pointer(setup.saved[entry["saved"]], entry["savedPointer"])
        assert jcs(left) == jcs(right), f"equal relation failed at {entry['pointer']}"
    for entry in spec.get("differ", []):
        left = _resolve_pointer(actual, entry["pointer"])
        right = _resolve_pointer(setup.saved[entry["saved"]], entry["savedPointer"])
        assert jcs(left) != jcs(right), f"differ relation failed at {entry['pointer']}"


def check_signal(actual: Json, spec: dict[str, Json]) -> None:
    """Check the ``signal`` contract of one step (poll counts and re-entry)."""
    from bpmn_io.profile import jcs

    meta = actual.get("__signal__", {})
    assert meta.get("calls", 0) >= spec["minCalls"], (
        f"signal polled {meta.get('calls', 0)} times, need {spec['minCalls']}"
    )
    for op, want in spec.get("results", {}).items():
        for outcome in meta.get("results", {}).get(op, []):
            merged = _substitute_unsealed(copy.deepcopy(want), outcome)
            assert jcs(outcome) == jcs(merged), f"reentrant {op} outcome differs"
