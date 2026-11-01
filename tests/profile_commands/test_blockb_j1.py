"""Block-B mirror J1: activation applies the DESIGN section 3.3 matrix in order."""

from __future__ import annotations

import copy
import dataclasses

import pytest

from bpmn_io.profile._bridge import HeadlessBridge
from bpmn_io.profile._envelope import complete_envelope
from bpmn_io.profile._ui import compiled_identity

_TREE = {
    "$type": "bpmn:Definitions",
    "id": "D_1",
    "targetNamespace": "urn:x",
    "rootElements": [
        {"$type": "bpmn:Process", "id": "P_1", "flowElements": []},
    ],
}


def _setup() -> tuple[object, object]:
    """Compile the real neutral lot-5 profile with its context."""
    from bpmn_io.profile import (
        compile_profile,
        create_descriptor_context,
        load_profile,
    )
    from tests.profile_commands import harness as _harness

    raw = (_harness.EXPECTED / "artifacts/profiles/neutral-lot5.json").read_bytes()
    package = dict(_harness.DEFAULT_DESCRIPTOR_PIN)
    package["descriptorBytes"] = _harness.DEFAULT_DESCRIPTOR_BYTES
    context_result = create_descriptor_context([package])
    assert context_result.status == "ok", context_result.to_json()
    pins = [{"id": package["id"], "version": package["version"], "sha256": package["sha256"]}]
    load_result = load_profile(
        raw,
        schema_bytes=_harness.SCHEMA_BYTES,
        base_bytes=_harness.BASE_BYTES,
        descriptor_pins=pins,
        asset_bag=dict(_harness.METRICS_BAG),
    )
    assert load_result.status == "ok", load_result.to_json()
    compile_result = compile_profile(
        load_result.payload,  # type: ignore[union-attr]
        descriptor_context=context_result.payload,  # type: ignore[union-attr]
        base=copy.deepcopy(_harness.BASE_DOCUMENT),
    )
    assert compile_result.status == "ok", compile_result.to_json()
    return context_result.payload, compile_result.payload  # type: ignore[return-value]


def _loaded(context: object, identity: dict[str, object]) -> HeadlessBridge:
    """Return one bridge loaded with the given document identity."""
    from bpmn_io.profile import create_bridge

    session = create_bridge(context)  # type: ignore[arg-type]
    loaded = session.set_definitions(complete_envelope(identity, copy.deepcopy(_TREE), []))
    assert getattr(loaded, "status", None) == "ok", getattr(loaded, "to_json", lambda: loaded)()
    assert isinstance(session, HeadlessBridge)
    return session


def _offered(compiled: object, mutate: object) -> object:
    """Return a compiled handle carrying the mutated identity."""
    identity = copy.deepcopy(compiled_identity(compiled))  # type: ignore[arg-type]
    mutate(identity)  # type: ignore[operator]
    return dataclasses.replace(compiled, identity=identity)  # type: ignore[type-var]


def _refused(session: HeadlessBridge, offered: object, code: str, plan: object = None) -> None:
    before = session.get_snapshot()
    out = session.activate_business_profile(offered, explicit_migration_plan=plan)  # type: ignore[arg-type]
    assert getattr(out, "status", None) == "refused"
    assert getattr(out, "code", None) == code
    assert session.get_snapshot().to_json() == before.to_json()


def test_j1_exact_identity_match_succeeds() -> None:
    """P = D in every dimension accepts."""
    context, compiled = _setup()
    session = _loaded(context, compiled_identity(compiled))
    out = session.activate_business_profile(compiled)  # type: ignore[arg-type]
    assert getattr(out, "status", None) == "ok"


def test_j1_exact_match_with_plan_succeeds() -> None:
    """A plan argument alone is void: an exact match still succeeds."""
    context, compiled = _setup()
    session = _loaded(context, compiled_identity(compiled))
    out = session.activate_business_profile(compiled, explicit_migration_plan=False)  # type: ignore[arg-type]
    assert getattr(out, "status", None) == "ok"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        # Rows 4/5 precede rows 8/9: this runtime supports mechanism "1"
        # and schema "1.0.0" only, so an unsupported offered value refuses
        # with the ordered unsupported code, not the migration code.
        (
            lambda identity: identity.update({"mechanismVersion": "2"}),
            "mechanism-version-unsupported",
        ),
        (
            lambda identity: identity.update({"schemaVersion": "9.9.9"}),
            "profile-schema-version",
        ),
        (
            lambda identity: identity.update({"base": {**identity["base"], "version": "tampered"}}),
            "base-mismatch",
        ),
        (
            lambda identity: identity.update(
                {"descriptors": [{**identity["descriptors"][0], "version": "tampered"}]}
            ),
            "descriptor-mismatch",
        ),
        (lambda identity: identity.update({"profile": "other/1"}), "profile-major-mismatch"),
        (lambda identity: identity.update({"version": "2.0.0"}), "profile-major-mismatch"),
        (
            lambda identity: identity.update({"sha256": "0" * 64}),
            "profile-digest-mismatch",
        ),
        (
            lambda identity: identity.update({"version": "1.6.1"}),
            "profile-patch-migration-required",
        ),
        (
            lambda identity: identity.update({"version": "1.7.0"}),
            "profile-minor-migration-required",
        ),
        (
            lambda identity: identity.update({"version": "1.5.0"}),
            "profile-minor-downgrade-required",
        ),
        (
            lambda identity: identity.update({"version": "1.6"}),
            "profile-source-unavailable",
        ),
    ],
)
def test_j1_matrix_rows_refuse_with_exact_code(mutate: object, code: str) -> None:
    """Each section 3.3 identity change refuses with its matrix code."""
    context, compiled = _setup()
    session = _loaded(context, compiled_identity(compiled))
    offered = _offered(compiled, mutate)
    _refused(session, offered, code)


def test_j1_patch_downgrade_refuses() -> None:
    """A document newer patch against an older offered patch refuses."""
    context, compiled = _setup()
    newer = copy.deepcopy(compiled_identity(compiled))
    newer["version"] = "1.6.1"
    session = _loaded(context, newer)
    _refused(session, compiled, "profile-patch-downgrade-required")


def test_j1_digest_conflict_never_waived_by_plan() -> None:
    """A same-version digest conflict refuses even with a plan supplied."""
    context, compiled = _setup()
    session = _loaded(context, compiled_identity(compiled))
    offered = _offered(compiled, lambda identity: identity.update({"sha256": "0" * 64}))
    _refused(session, offered, "profile-digest-mismatch", plan={"migration": "note"})


@pytest.mark.parametrize("plan", [False, "note", {"migration": "note"}])
def test_j1_plan_alone_never_migrates(plan: object) -> None:
    """A plan, token or flag alone never counts as migration."""
    context, compiled = _setup()
    session = _loaded(context, compiled_identity(compiled))
    offered = _offered(compiled, lambda identity: identity.update({"version": "1.6.1"}))
    _refused(session, offered, "profile-patch-migration-required", plan=plan)


def test_j1_plan_false_never_migrates_major() -> None:
    """Plan false alone never migrates a major change."""
    context, compiled = _setup()
    session = _loaded(context, compiled_identity(compiled))
    offered = _offered(compiled, lambda identity: identity.update({"version": "2.0.0"}))
    _refused(session, offered, "profile-major-mismatch", plan=False)
