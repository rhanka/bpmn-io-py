"""Case-driven lot-3 harness runner (lot-3 binding §9).

Every sealed harness record under ``tests/profile_cn/expected/<case>.json``
runs through its bound public call with byte-exact comparison (zero
tolerance). Operations whose implementation is still pending are marked
``xfail(strict=True)`` naming the missing piece; the mark comes off with
the implementation.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from bpmn_io.profile import (
    GATES,
    Authority,
    allocate_stable_id,
    apply_plan,
    bind_supports,
    compile_profile,
    complete,
    create_descriptor_context,
    create_read_context,
    import_projection,
    jcs,
    load_profile,
    normalize,
    plan_recipe,
    propose_support_bindings,
    remap_ids,
    sort_placements,
)
from bpmn_io.profile._c14n import jcs_bytes

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "tests" / "profile_cn" / "expected"
MECH = ROOT / "contracts" / "profile-mechanism" / "1"

#: Operations with no implementation yet: value is the strict-xfail reason.
PENDING = {
    "validate": (
        "no Block-A validate(compiled, wire-envelope, phase, readiness_policy) "
        "binding in this branch (binding §9 runner row, §6.9); sealed JS-owned values kept"
    ),
}

_CASE_FILES = sorted(EXPECTED.glob("*.json"))
_CASE_OPS = {
    path.stem: json.loads(path.read_text(encoding="utf-8"))["operation"] for path in _CASE_FILES
}

_VARIANT_TABLE: dict[str, dict[str, str]] = {}
_COMPILED: dict[str, object] = {}


def _variant_table() -> dict[str, dict[str, str]]:
    """Return the variant load table (parity manifest plus the MECH roots)."""
    if not _VARIANT_TABLE:
        manifest = json.loads((EXPECTED / "parity" / "manifest.json").read_text(encoding="utf-8"))
        for row in manifest["profiles"]:
            _VARIANT_TABLE[row["variant"]] = {
                "profile": row["path"],
                "descriptors": row["descriptorBytes"]["path"],
                "base": row["baseBytes"]["path"],
            }
        _VARIANT_TABLE["neutral"] = {
            "profile": "contracts/profile-mechanism/1/neutral-profile.json",
            "descriptors": "contracts/profile-mechanism/1/neutral-descriptors.json",
            "base": "contracts/profile-mechanism/1/neutral-base.json",
        }
        _VARIANT_TABLE["grid"] = {
            "profile": "contracts/profile-mechanism/1/neutral-grid-profile.json",
            "descriptors": "contracts/profile-mechanism/1/neutral-descriptors.json",
            "base": "contracts/profile-mechanism/1/neutral-base.json",
        }
    return _VARIANT_TABLE


def _profile_parts(ref: object) -> tuple[bytes, bytes, bytes]:
    """Return (profile, descriptor, base) bytes for a variant name or record."""
    if isinstance(ref, str):
        row = _variant_table()[ref]
        return (
            (ROOT / row["profile"]).read_bytes(),
            (ROOT / row["descriptors"]).read_bytes(),
            (ROOT / row["base"]).read_bytes(),
        )
    assert isinstance(ref, dict)
    profile_path = ref["vendored"]
    assert isinstance(profile_path, str)
    desc = ref["descriptorBytes"]
    base = ref["baseBytes"]
    assert isinstance(desc, dict)
    assert isinstance(base, dict)
    return (
        (ROOT / profile_path).read_bytes(),
        (ROOT / desc["path"]).read_bytes(),
        (ROOT / base["path"]).read_bytes(),
    )


def _try_compile(ref: object, *, without_context: bool = False) -> object:
    """Return the raw compile PureResult for a variant name (no assertion)."""
    profile_bytes, desc_bytes, base_bytes = _profile_parts(ref)
    schema_bytes = (MECH / "profile-mechanism-1.schema.json").read_bytes()
    validated = load_profile(profile_bytes, schema_bytes=schema_bytes, base_bytes=base_bytes)
    assert validated.status == "ok", validated
    profile = json.loads(profile_bytes.decode("utf-8"))
    if without_context:
        return compile_profile(validated.payload)
    packages = [{**entry, "descriptorBytes": desc_bytes} for entry in profile["descriptors"]]
    context = create_descriptor_context(packages)
    assert context.status == "ok", context
    return compile_profile(
        validated.payload,
        descriptor_context=context.payload,
        base=json.loads(base_bytes.decode("utf-8")),
    )


def _compiled(ref: object, *, without_context: bool = False) -> object:
    """Build (and cache) the compiled profile for a case profile reference."""
    key = jcs(ref) + ("|bare" if without_context else "|full")
    hit = _COMPILED.get(key)
    if hit is not None:
        return hit
    made = _try_compile(ref, without_context=without_context)
    assert made.status == "ok", made
    _COMPILED[key] = made.payload
    return made.payload


def _authority(record: object) -> object:
    """Build the Authority, passing invalid records through for refusal."""
    if isinstance(record, dict) and set(record) == {"actor", "activation", "deletionIntent"}:
        return Authority(
            actor=record["actor"],
            activation=record["activation"],
            deletion_intent=record["deletionIntent"],
        )
    return record


def _recipe(compiled: object, ref: object) -> object:
    """Resolve a recipe id against the compiled recipes (or take it verbatim)."""
    if not isinstance(ref, str):
        return ref
    recipes = compiled.recipes
    assert isinstance(recipes, dict)
    for record in recipes.values():
        assert isinstance(record, dict)
        if record.get("id") == ref:
            return record
    msg = f"unknown recipe {ref!r}"
    raise AssertionError(msg)


def _assert_holey(expected: object, actual: object, path: str = "$") -> None:
    """Compare with ``{"$unsealed": reason}`` holes filled from the actual value."""
    if isinstance(expected, dict) and set(expected) == {"$unsealed"}:
        return
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert set(actual) == set(expected), path
        for key, want in expected.items():
            _assert_holey(want, actual[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, (list, tuple)), path
        assert len(actual) == len(expected), path
        for index, want in enumerate(expected):
            _assert_holey(want, actual[index], f"{path}[{index}]")
        return
    assert jcs(expected) == jcs(actual), path


def _pure_wire(outcome: object) -> dict[str, object]:
    """Return the comparable wire of a PureResult (raw payload kept)."""
    assert hasattr(outcome, "status")
    if outcome.status == "ok":
        return {
            "status": "ok",
            "payload": outcome.payload,
            "diagnostics": list(outcome.diagnostics),
        }
    return {"status": "refused", "code": outcome.code, "diagnostics": list(outcome.diagnostics)}


def _plain(node: object) -> object:
    """Convert mappings (including proxies) to plain JSON values."""
    if isinstance(node, Mapping):
        return {key: _plain(value) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_plain(value) for value in node]
    return node


def _assert_complete_fixed_point(
    compiled: object, first: dict[str, object], activation: str
) -> None:
    """Rerun complete on its payload (mode retained): empty delta, same revision."""
    rerun = complete(compiled, first["payload"], "retained", activation=activation).to_json()
    assert rerun["status"] == "ok"
    assert jcs(rerun["payload"]) == jcs(first["payload"])
    assert rerun["report"]["entries"] == []
    assert rerun["baseRevision"] == rerun["revision"] == first["revision"]


def _run_complete(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one complete case with its fixed-point rerun."""
    assert isinstance(case["profile"], (str, dict))
    compiled = _compiled(
        case["profile"], without_context=record.get("compile") == "without-descriptor-context"
    )
    frozen = jcs(record)
    activation = record.get("activation") or "edit"
    assert isinstance(activation, str)
    actual = complete(compiled, record["envelope"], record["mode"], activation=activation).to_json()
    assert jcs(record) == frozen
    assert jcs(actual) == jcs(case["expected"]), case["case"]
    if case.get("fixedPoint") and actual["status"] == "ok":
        assert isinstance(actual, dict)
        _assert_complete_fixed_point(compiled, actual, activation)


def _run_plan(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one plan_recipe+apply_plan case through the bound §9 calls."""
    compiled = _compiled(case["profile"])
    frozen = jcs(record)
    made = create_read_context(compiled, record["envelope"], stage="load")
    assert made.status == "ok", getattr(made, "code", made)
    outcome = plan_recipe(
        _recipe(compiled, record["recipe"]),
        made.payload,
        record["params"],
        _authority(record["authority"]),
    )
    assert jcs(record) == frozen
    assert jcs(_pure_wire(outcome)) == jcs(case["expected"]["plan"]), case["case"]
    if "apply" in case["expected"]:
        assert outcome.status == "ok"
        applied = apply_plan(outcome.payload, record["envelope"]["tree"], record["envelope"])
        assert jcs(applied.to_json()) == jcs(case["expected"]["apply"]), case["case"]
        assert jcs(record) == frozen


def _run_apply(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one apply_plan case over its staged tree."""
    frozen = jcs(record)
    tree = record.get("stagedTree", record["envelope"]["tree"])
    outcome = apply_plan(record["plan"], tree, record["envelope"])
    assert jcs(record) == frozen
    assert jcs(outcome.to_json()) == jcs(case["expected"]["apply"]), case["case"]


def _compile_names(record: dict[str, object]) -> list[str]:
    """Return the variant names of a compile_profile case input."""
    if "variant" in record:
        assert isinstance(record["variant"], str)
        return [record["variant"]]
    assert isinstance(record["variants"], list)
    return list(record["variants"])


def _run_compile(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one compile_profile case, including the compiled identities."""
    names = _compile_names(record)
    outcomes = [_try_compile(name) for name in names]
    wires = [_pure_wire(outcome) for outcome in outcomes]
    actual = wires[0] if len(wires) == 1 else wires
    _assert_holey(case["expected"], actual)
    identities = [outcome.payload.identity for outcome in outcomes if outcome.status == "ok"]
    if len(names) == 1:
        if identities:
            assert jcs(identities[0]) == jcs(case["compiledIdentity"]), case["case"]
    else:
        assert len(case["compiledIdentities"]) == len(names), case["case"]
        for position, name in enumerate(names):
            entry = case["compiledIdentities"][position]
            assert entry["variant"] == name, case["case"]
            assert jcs(identities[position]) == jcs(entry["identity"]), case["case"]


def _run_sort(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one sort_placements case."""
    assert jcs(sort_placements(record["placements"])) == jcs(case["expected"]), case["case"]


def _assert_normalize_fixed_point(
    compiled: object,
    first: dict[str, object],
    intent: object,
    activation: str,
) -> None:
    """Rerun normalize on its payload: empty delta, same revision and placements."""
    rerun = normalize(
        compiled, first["payload"]["envelope"], intent, activation=activation
    ).to_json()
    assert rerun["status"] == "ok"
    assert jcs(rerun["payload"]["envelope"]) == jcs(first["payload"]["envelope"])
    assert jcs(rerun["payload"]["placements"]) == jcs(first["payload"]["placements"])
    assert rerun["report"]["entries"] == []
    assert rerun["baseRevision"] == rerun["revision"] == first["revision"]


def _run_normalize(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one normalize case with its fixed-point rerun."""
    compiled = _compiled(case["profile"])
    frozen = jcs(record)
    activation = record.get("activation") or "edit"
    assert isinstance(activation, str)
    actual = normalize(
        compiled, record["envelope"], record.get("placementIntent"), activation=activation
    ).to_json()
    assert jcs(record) == frozen
    assert jcs(actual) == jcs(case["expected"]), case["case"]
    if case.get("fixedPoint") and actual["status"] == "ok":
        assert isinstance(actual, dict)
        _assert_normalize_fixed_point(compiled, actual, record.get("placementIntent"), activation)


def _run_bind(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one bind_supports case through the bound §9 call."""
    compiled = _compiled(case["profile"])
    frozen = jcs(record)
    activation = record.get("activation") or "edit"
    assert isinstance(activation, str)
    actual = bind_supports(
        compiled, record["envelope"], record["bindings"], activation=activation
    ).to_json()
    assert jcs(record) == frozen
    assert jcs(actual) == jcs(case["expected"]), case["case"]


def _run_import(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one import_projection case through the bound §9 call."""
    compiled = _compiled(case["profile"])
    frozen = jcs(record)
    source = record["source"]["text"].encode("utf-8")
    actual = import_projection(compiled, source, source_format="native-json").to_json()
    assert jcs(record) == frozen
    assert jcs(actual) == jcs(case["expected"]), case["case"]


def _run_transport(case: dict[str, object], record: dict[str, object]) -> None:
    """Run the python hops of one cross-runtime transport case (§9 row)."""
    compiled = _compiled(case["profile"])
    frozen = jcs(record)
    route = record["transportRoute"]["route"]
    activations = record["transportRoute"]["activations"]
    hop_results = case["expected"]["hopResults"]
    assert len(route) == len(activations) == len(hop_results)
    sealed_text = case["expected"]["transportBytes"]["text"]
    assert isinstance(sealed_text, str)
    sealed_envelope = json.loads(sealed_text)
    assert isinstance(sealed_envelope, dict)
    assert case["expected"]["transport"]["route"] == record["transportRoute"]["route"]
    for number, (runtime, activation) in enumerate(zip(route, activations, strict=True)):
        if runtime != "python":
            continue
        hop_input = record["envelope"] if number == 0 else sealed_envelope
        assert isinstance(activation, str)
        actual = normalize(compiled, hop_input, activation=activation).to_json()
        assert jcs(actual) == jcs(hop_results[number]), (case["case"], number)
        carried = actual["payload"]["envelope"] if actual["status"] == "ok" else actual
        grown = jcs_bytes(carried)
        assert grown.decode("utf-8") == sealed_text, (case["case"], number)
        hop_sha = case["expected"]["transport"]["hops"][number]["outputSha256"]
        assert hashlib.sha256(grown).hexdigest() == hop_sha, (case["case"], number)
    assert jcs(record) == frozen


def _run_remap(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one remap_ids case through the bound §9 call."""
    compiled = _compiled(case["profile"])
    frozen = jcs(record)
    activation = record.get("activation") or "edit"
    assert isinstance(activation, str)
    actual = remap_ids(
        compiled,
        record["envelope"],
        record["importedDi"],
        record["command"],
        activation=activation,
    ).to_json()
    assert jcs(record) == frozen
    assert jcs(actual) == jcs(case["expected"]), case["case"]


def _run_propose(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one propose_support_bindings case through the bound §9 call."""
    compiled = _compiled(case["profile"])
    frozen = jcs(record)
    outcome = propose_support_bindings(
        compiled, record["envelope"], provenance=record["provenance"]
    )
    assert jcs(record) == frozen
    assert jcs(_pure_wire(outcome)) == jcs(case["expected"]), case["case"]


def _run_gates(case: dict[str, object], _record: dict[str, object]) -> None:
    """Run the gate-table case against GATES."""
    assert jcs(_plain(GATES)) == jcs(case["expected"]), case["case"]


def _run_stable(case: dict[str, object], record: dict[str, object]) -> None:
    """Run one stable-id/1 vector case."""
    ids = [
        allocate_stable_id(item["owner"], item["slot"], item["key"])
        for item in record["allocations"]
    ]
    assert jcs(ids) == jcs(case["expected"]), case["case"]


_RUNNERS = {
    "complete": _run_complete,
    "normalize": _run_normalize,
    "plan_recipe+apply_plan": _run_plan,
    "apply_plan": _run_apply,
    "bind_supports": _run_bind,
    "compile_profile": _run_compile,
    "import_projection": _run_import,
    "normalize_transport": _run_transport,
    "propose_support_bindings": _run_propose,
    "remap_ids": _run_remap,
    "sort_placements": _run_sort,
    "gates": _run_gates,
    "stable-id/1": _run_stable,
}


def _params() -> list[pytest.ParamSet]:
    """Build one parameter per harness record (pending ops stay strict-xfail)."""
    items = []
    for path in _CASE_FILES:
        operation = _CASE_OPS[path.stem]
        marks = []
        if operation in PENDING:
            marks.append(pytest.mark.xfail(strict=True, reason=PENDING[operation]))
        items.append(pytest.param(path.stem, marks=marks, id=path.stem))
    return items


@pytest.mark.parametrize("case_id", _params())
def test_cn_case(case_id: str) -> None:
    """Run one sealed lot-3 harness record through its bound call."""
    path = EXPECTED / f"{case_id}.json"
    case = json.loads(path.read_text(encoding="utf-8"))
    assert case["case"] == case_id
    assert case["author"] == "spec-seal"
    record = copy.deepcopy(case["input"])
    operation = case["operation"]
    assert operation not in PENDING, f"pending operation reached the runner: {operation}"
    runner = _RUNNERS.get(operation)
    assert runner is not None, f"no runner for operation {operation!r}"
    runner(case, record)


def test_every_harness_record_consumed() -> None:
    """Every sealed harness record runs through the case driver above."""
    on_disk = sorted(path.stem for path in EXPECTED.glob("*.json"))
    assert on_disk == sorted(_CASE_OPS)
    assert set(_CASE_OPS.values()) - set(PENDING) <= set(_RUNNERS)
