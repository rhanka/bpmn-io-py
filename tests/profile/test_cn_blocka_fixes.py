"""Block A corrections owned by the lot-3 code job (seal findings B1-B10).

Each probe restores the pinned schema or the DESIGN rule the seal records in
``spec/SPEC_PROFILE_CN_PY.md`` §2.2. Fixtures are the vendored neutral
contracts and the sealed ``cn`` descriptor/base artifacts, never
implementation output.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bpmn_io.profile._compiler import DescriptorContext
from bpmn_io.profile._loader import ValidatedProfile

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).resolve().parent.parent.parent
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"
CN_ART = ROOT / "tests" / "profile_cn" / "expected" / "artifacts"


def _read(path: Path) -> bytes:
    return path.read_bytes()


def _neutral_profile() -> dict[str, Any]:
    profile = json.loads((MECHANISM / "neutral-profile.json").read_text(encoding="utf-8"))
    assert isinstance(profile, dict)
    return profile


def _load(profile: dict[str, Any]) -> ValidatedProfile:
    from bpmn_io.profile import load_profile

    loaded = load_profile(
        json.dumps(profile).encode("utf-8"),
        schema_bytes=(MECHANISM / "profile-mechanism-1.schema.json").read_bytes(),
    )
    assert loaded.status == "ok", loaded
    assert isinstance(loaded.payload, ValidatedProfile)
    return loaded.payload


def _neutral_context() -> DescriptorContext:
    from bpmn_io.profile import create_descriptor_context

    profile = _neutral_profile()
    raw = (MECHANISM / "neutral-descriptors.json").read_bytes()
    packages = [{**entry, "descriptorBytes": raw} for entry in profile["descriptors"]]
    result = create_descriptor_context(packages)  # type: ignore[arg-type]
    assert result.status == "ok", result
    assert isinstance(result.payload, DescriptorContext)
    return result.payload


def _neutral_base() -> dict[str, Any]:
    base = json.loads((MECHANISM / "neutral-base.json").read_text(encoding="utf-8"))
    assert isinstance(base, dict)
    return base


def _cn_context() -> DescriptorContext:
    import hashlib

    from bpmn_io.profile import create_descriptor_context

    raw = (CN_ART / "cn-descriptors.json").read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    packages = [
        {
            "id": doc["id"],
            "version": "fixture-1",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "descriptorBytes": raw,
        }
    ]
    result = create_descriptor_context(packages)
    assert result.status == "ok", result
    assert isinstance(result.payload, DescriptorContext)
    return result.payload


def _cn_base() -> dict[str, Any]:
    base = json.loads((CN_ART / "cn-base.json").read_text(encoding="utf-8"))
    assert isinstance(base, dict)
    return base


def _rule_profile(mutate: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    """Return the neutral profile with its first rule replaced by ``mutate``."""
    profile = _neutral_profile()
    rules = profile["rules"]
    assert isinstance(rules, list)
    assert rules
    first = copy.deepcopy(rules[0])
    assert isinstance(first, dict)
    profile["rules"] = [mutate(first)]
    return profile


def test_b1_count_reads_select_key() -> None:
    """A schema-valid ``count`` (``select`` key) compiles (B1)."""
    from bpmn_io.profile import compile_profile

    def _mutate(rule: dict[str, Any]) -> dict[str, Any]:
        rule["assert"] = {
            "op": "count",
            "select": {
                "from": "self",
                "via": "children",
                "property": "flowElements",
                "where": {"op": "true"},
                "order": "id",
            },
            "min": 0,
        }
        return rule

    compiled = compile_profile(_load(_rule_profile(_mutate)))
    assert compiled.status == "ok", compiled


def test_b1_reachable_reads_from_to_keys() -> None:
    """A schema-valid ``reachable`` (``from``/``to`` keys) compiles (B1)."""
    from bpmn_io.profile import compile_profile

    selector = {"from": "self", "via": "self", "where": {"op": "true"}, "order": "id"}

    def _mutate(rule: dict[str, Any]) -> dict[str, Any]:
        rule["assert"] = {
            "op": "reachable",
            "from": selector,
            "to": selector,
            "edgeTypes": ["bpmn:SequenceFlow"],
            "minHops": 0,
        }
        return rule

    compiled = compile_profile(_load(_rule_profile(_mutate)))
    assert compiled.status == "ok", compiled


def test_b1_count_select_evaluates() -> None:
    """The evaluator counts through the ``select`` key (B1)."""
    from bpmn_io.bpmn_moddle.simple import create_moddle
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    moddle = create_moddle()
    task = moddle.create("bpmn:Task", {"id": "T1"})
    process = moddle.create("bpmn:Process", {"id": "P1"})
    process.set("flowElements", [task])
    context = make_read_context(process)
    result = evaluate_predicate(
        {
            "op": "count",
            "select": {
                "from": "root",
                "via": "descendants",
                "where": {
                    "op": "typeIs",
                    "binding": "self",
                    "type": "bpmn:Task",
                    "mode": "exact",
                },
                "order": "id",
            },
            "min": 1,
        },
        context,
        {},
    )
    assert result.status == "ok", result
    assert result.payload is True  # type: ignore[attr-defined]


def test_b1_reachable_from_to_evaluates() -> None:
    """The evaluator walks reachability through ``from``/``to`` (B1)."""
    from bpmn_io.bpmn_moddle.simple import create_moddle
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    moddle = create_moddle()
    start = moddle.create("bpmn:Task", {"id": "A"})
    end = moddle.create("bpmn:Task", {"id": "B"})
    flow = moddle.create("bpmn:SequenceFlow", {"id": "F1"})
    flow.set("sourceRef", start)
    flow.set("targetRef", end)
    process = moddle.create("bpmn:Process", {"id": "P1"})
    process.set("flowElements", [start, end, flow])
    context = make_read_context(process)
    itself = {"from": "root", "via": "self", "where": {"op": "true"}, "order": "id"}
    result = evaluate_predicate(
        {
            "op": "reachable",
            "from": itself,
            "to": itself,
            "edgeTypes": ["bpmn:SequenceFlow"],
            "minHops": 0,
        },
        context,
        {},
    )
    assert result.status == "ok", result
    assert result.payload is True  # type: ignore[attr-defined]


def test_b2_inverse_reference_admits_referring_type() -> None:
    """``inverseReference`` is admitted when some descriptor type declares it (B2)."""
    from bpmn_io.profile import compile_profile

    def _mutate(rule: dict[str, Any]) -> dict[str, Any]:
        rule["select"] = {
            "from": "self",
            "via": "inverseReference",
            "property": "sourceRef",
            "where": {"op": "true"},
            "order": "id",
        }
        return rule

    # ``bpmn:Process`` declares no reference, but ``bpmn:SequenceFlow`` (and
    # ``bpmn:Association``) declare ``sourceRef``: the traversal is admitted.
    compiled = compile_profile(
        _load(_rule_profile(_mutate)),
        descriptor_context=_neutral_context(),
        base=_neutral_base(),
    )
    assert compiled.status == "ok", compiled


def test_b2_inverse_reference_unknown_property_refuses() -> None:
    """``inverseReference`` over a property no type declares still refuses (B2)."""
    from bpmn_io.profile import compile_profile

    def _mutate(rule: dict[str, Any]) -> dict[str, Any]:
        rule["select"] = {
            "from": "self",
            "via": "inverseReference",
            "property": "noSuchReferenceAnywhere",
            "where": {"op": "true"},
            "order": "id",
        }
        return rule

    compiled = compile_profile(_load(_rule_profile(_mutate)), descriptor_context=_neutral_context())
    assert compiled.status == "refused", compiled
    assert compiled.code == "profile-type"  # type: ignore[union-attr]


def _ensure_recipe() -> dict[str, Any]:
    """Return one normalize recipe with two support ensures plus its writes."""
    return {
        "id": "ensure-one",
        "phase": "normalize",
        "parameters": [],
        "select": {
            "from": "root",
            "via": "all",
            "where": {"op": "typeIs", "binding": "self", "type": "bpmn:Process", "mode": "exact"},
            "order": "id",
        },
        "when": {"op": "true"},
        "writes": [
            {"binding": "root", "path": "/rootElements", "mode": "create"},
            {"binding": "envelope", "path": "/bindings", "mode": "binding"},
            {"binding": "collaboration", "path": "/participants", "mode": "create"},
            {"binding": "main", "path": "/processRef", "mode": "reference"},
        ],
        "steps": [
            {
                "op": "ensure",
                "as": "collaboration",
                "type": "bpmn:Collaboration",
                "parent": "root",
                "property": "rootElements",
                "owner": "self",
                "role": "collaboration",
                "ownerId": {"op": "id", "binding": "root"},
                "slot": "collaboration",
                "key": {"op": "id", "binding": "self"},
                "fields": [{"name": "name", "value": {"op": "literal", "value": "c"}}],
            },
            {
                "op": "ensure",
                "as": "main",
                "type": "bpmn:Participant",
                "parent": "collaboration",
                "property": "participants",
                "owner": "self",
                "role": "main-participant",
                "ownerId": {"op": "id", "binding": "self"},
                "slot": "main-participant",
                "key": {"op": "literal", "value": "main-participant"},
                "fields": [{"name": "name", "value": {"op": "literal", "value": "m"}}],
            },
            {
                "op": "assignRef",
                "target": "main",
                "path": "/processRef",
                "mode": "replace",
                "values": [{"op": "id", "binding": "self"}],
            },
        ],
    }


def _profile_with_recipes(recipes: list[dict[str, Any]]) -> dict[str, Any]:
    profile = _neutral_profile()
    existing = profile["recipes"]
    assert isinstance(existing, list)
    profile["recipes"] = [*existing, *recipes]
    return profile


def test_b3_ensure_compiles_with_demands_and_alias() -> None:
    """A support ensure compiles: demands, binding write and ``as`` alias (B3)."""
    from bpmn_io.profile import compile_profile

    compiled = compile_profile(
        _load(_profile_with_recipes([_ensure_recipe()])),
        descriptor_context=_cn_context(),
        base=_cn_base(),
    )
    assert compiled.status == "ok", compiled


def test_b3_ensure_non_support_type_refuses_producer() -> None:
    """An ensure of a non-support native type refuses ``profile-producer`` (B3)."""
    from bpmn_io.profile import compile_profile

    recipe = _ensure_recipe()
    assert isinstance(recipe["steps"][0], dict)
    recipe["steps"][0]["type"] = "bpmn:Task"
    compiled = compile_profile(
        _load(_profile_with_recipes([recipe])),
        descriptor_context=_cn_context(),
        base=_cn_base(),
    )
    assert compiled.status == "refused", compiled
    assert compiled.code == "profile-producer"  # type: ignore[union-attr]


def test_b3_ensure_missing_binding_write_refuses_write_set() -> None:
    """An ensure recipe without its envelope binding write refuses (B3/CR-06)."""
    from bpmn_io.profile import compile_profile

    recipe = _ensure_recipe()
    recipe["writes"] = [dict(recipe["writes"][0])]
    compiled = compile_profile(
        _load(_profile_with_recipes([recipe])),
        descriptor_context=_cn_context(),
        base=_cn_base(),
    )
    assert compiled.status == "refused", compiled
    assert compiled.code == "profile-write-set"  # type: ignore[union-attr]


def test_b4_identical_demands_coalesce() -> None:
    """Duplicate identical demands compile against one declared write (B4)."""
    from bpmn_io.profile import compile_profile

    recipe = _ensure_recipe()
    recipe["steps"] = [
        {
            "op": "set",
            "target": "self",
            "path": "/name",
            "value": {"op": "literal", "value": "n"},
        },
        {
            "op": "set",
            "target": "self",
            "path": "/name",
            "value": {"op": "literal", "value": "n"},
        },
    ]
    recipe["writes"] = [{"binding": "self", "path": "/name", "mode": "set"}]
    compiled = compile_profile(
        _load(_profile_with_recipes([recipe])),
        descriptor_context=_cn_context(),
        base=_cn_base(),
    )
    assert compiled.status == "ok", compiled


def test_b5_owner_resolves_json_trees() -> None:
    """``owner`` follows the containing element of plain JSON trees (B5)."""
    from bpmn_io.profile import select
    from bpmn_io.profile._evaluate import make_read_context

    tree = {
        "$type": "bpmn:Definitions",
        "id": "D1",
        "rootElements": [
            {
                "$type": "bpmn:Process",
                "id": "P1",
                "flowElements": [{"$type": "bpmn:Task", "id": "T1"}],
            }
        ],
    }
    context = make_read_context(tree)
    task = context.by_id["T1"]
    result = select(
        {"from": "task", "via": "owner", "where": {"op": "true"}, "order": "id"},
        context,
        {"task": task},
    )
    assert result.status == "ok", result
    handles = result.payload  # type: ignore[attr-defined]
    assert [handle.element_id for handle in handles] == ["P1"]


def test_b6_descriptor_facets_kept() -> None:
    """The descriptor index keeps ``many``/``single`` facets (B6)."""
    context = _cn_context()
    assert context.types["bpmn:Task"]["many"] == ("incoming", "outgoing")
    assert context.types["bpmn:Process"]["single"] == ("ioSpecification",)
    assert context.types["bpmn:CallActivity"].get("many", ()) == ()
    assert context.types["bpmn:CallActivity"].get("single", ()) == ()


def test_b7_compiled_profile_carries_identity_types_producers() -> None:
    """Compilation records identity, type index and producer matrix (B7)."""
    from bpmn_io.profile import compile_profile

    compiled = compile_profile(
        _load(_neutral_profile()),
        descriptor_context=_neutral_context(),
        base=_neutral_base(),
    )
    assert compiled.status == "ok", compiled
    payload = compiled.payload  # type: ignore[attr-defined]
    assert payload.identity["mechanismVersion"] == "1"
    assert payload.identity["profile"] == "neutral/1"
    assert len(payload.identity["sha256"]) == 64
    assert payload.types["bpmn:Task"]["id"] is True
    assert "code" in payload.producers[("bpmn:Task", "name")]


def test_b7_compiled_without_context_signals_descriptor_mismatch() -> None:
    """A profile compiled without context/base carries no C/N index (B7)."""
    from bpmn_io.profile import compile_profile

    compiled = compile_profile(_load(_neutral_profile()))
    assert compiled.status == "ok", compiled
    payload = compiled.payload  # type: ignore[attr-defined]
    assert payload.types is None
    assert payload.producers is None


def test_b8_envelope_shape_before_integrity() -> None:
    """Shape (version/identity/revision readable) precedes integrity (B8)."""
    from bpmn_io.profile._envelope import check_envelope_integrity, check_envelope_shape

    envelope = {
        "documentVersion": "1",
        "profileIdentity": {
            "mechanismVersion": "1",
            "schemaVersion": "1.0.0",
            "profile": "neutral/1",
            "version": "1.1.0",
            "sha256": "0" * 64,
            "base": {"id": "b", "version": "1.0.0", "sha256": "1" * 64},
            "descriptors": [{"id": "d", "version": "1.0.0", "sha256": "2" * 64}],
        },
        "tree": {"$type": "bpmn:Definitions"},
        "bindings": [],
        "semanticRevision": "not-a-revision",
    }
    assert check_envelope_shape(envelope) is None
    assert check_envelope_integrity(envelope) == "profile-schema"
    assert check_envelope_shape({**envelope, "documentVersion": "9"}) == (
        "document-version-unsupported"
    )


def test_b10_descriptor_digest_uses_sorted_pins() -> None:
    """The context digest is H(pins sorted by id) with {id, version, sha256} (B10)."""
    import hashlib

    from bpmn_io.profile import create_descriptor_context
    from bpmn_io.profile._c14n import digest

    raw_a = (MECHANISM / "neutral-descriptors.json").read_bytes()
    profile = _neutral_profile()
    pins = list(profile["descriptors"])
    assert len(pins) == 1
    extra_doc = {
        "types": {
            "bpmn:ZZZFixture": {
                "id": True,
                "scalars": ["id", "name"],
                "containment": {},
                "references": {},
            }
        }
    }
    raw_b = json.dumps(extra_doc).encode("utf-8")
    cn_pin = {
        "id": "aaa-fixture-descriptors/1",
        "version": "fixture-1",
        "sha256": hashlib.sha256(raw_b).hexdigest(),
    }
    packages = [
        {**pins[0], "descriptorBytes": raw_a},
        {**cn_pin, "descriptorBytes": raw_b},
    ]
    result = create_descriptor_context(packages)  # type: ignore[arg-type]
    assert result.status == "ok", result
    want = digest(
        sorted(
            [
                cn_pin,
                {
                    "id": pins[0]["id"],
                    "version": pins[0]["version"],
                    "sha256": pins[0]["sha256"],
                },
            ],
            key=lambda pin: str(pin["id"]).encode("utf-16-be"),
        )
    )
    assert result.payload.digest == want  # type: ignore[attr-defined]


def test_carried_resolve_pointer_requires_known_pointers() -> None:
    """A missing ``known_pointers`` set raises ``TypeError`` (block A review)."""
    import pytest

    from bpmn_io.profile._lint.index import resolve_pointer

    with pytest.raises(TypeError):
        resolve_pointer({}, "some-id", "/rootElements/0")
