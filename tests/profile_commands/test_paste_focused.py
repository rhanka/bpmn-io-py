"""Synthetic paste-fragment tests (check (h), no lot-3 dependency).

Compiles a paste entry over the grid profile documents by hand (a
``CompiledProfile`` with a UI index plus one paste entry and recipe) and
validates fragment compilation: ID reallocation, internal reference
rewrite, external validation, collision and admission refusals.
"""

from __future__ import annotations

import copy

from bpmn_io.profile._commands import (
    CommandError,
    build_stage_index,
    prepare_command,
)
from bpmn_io.profile._compiler import CompiledProfile
from bpmn_io.profile._ui import build_ui_index
from tests.profile_commands import harness


def _paste_setup() -> tuple[harness.Setup, CompiledProfile, dict[str, object]]:
    case = harness.read_case("surface-palette-entries-grid")
    setup = harness.make_setup(case)
    assert setup.compiled is not None, getattr(setup, "compile_refusal", None)
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    profile = copy.deepcopy(setup.validated.profile)  # type: ignore[union-attr]
    assert isinstance(profile, dict)
    profile["recipes"].append(
        {
            "id": "paste-task",
            "phase": "create",
            "parameters": [
                {"name": "owner", "type": "element", "required": True},
                {"name": "key", "type": "string", "required": True},
            ],
            "select": {"from": "owner", "via": "self", "order": "id"},
            "when": {"op": "true"},
            "steps": [{"op": "bind", "as": "x"}],
            "writes": [],
        }
    )
    profile["ui"].append(
        {
            "id": "task-paste",
            "surface": "paste",
            "label": "label",
            "when": {"op": "true"},
            "recipe": "paste-task",
            "group": "basic",
            "order": 5,
            "upstreamEntries": [],
            "parameters": [
                {"name": "owner", "source": "owner"},
                {"name": "key", "source": "key"},
            ],
            "icon": {"theme": "plain", "glyph": "task"},
        }
    )
    index = build_ui_index(profile)
    recipes = {str(recipe["id"]): recipe for recipe in profile["recipes"]}
    compiled = CompiledProfile(
        profile_digest="synthetic",
        notions={
            "task": {
                "recognition": {"op": "true"},
                "nativeTypes": ["bpmn:ServiceTask"],
            }
        },
        recipes=recipes,
        rules={},
        descriptor_digest="",
        registry_digest="",
        ui=index,
    )
    assert setup.context is not None
    return setup, compiled, dict(setup.context.types)


def _prepare(
    _setup: harness.Setup,
    compiled: CompiledProfile,
    types: dict[str, object],
    command: dict[str, object],
    tree: dict[str, object],
) -> str:
    typed = {k: v for k, v in types.items() if isinstance(v, dict)}
    try:
        prepared = prepare_command(
            compiled,
            tree,
            build_stage_index(tree),
            command,
            typed,  # type: ignore[arg-type]
        )
    except CommandError as exc:
        return exc.code
    return f"ok:{prepared.recipe_id}"


def _fragment(*roots: dict[str, object]) -> dict[str, object]:
    return {"fragmentVersion": "1", "sourceRevision": "r", "elements": list(roots)}


def test_paste_reallocates_ids() -> None:
    """Pasted roots land on the owner with stable reallocated IDs."""
    from bpmn_io.profile._c14n import jcs
    from bpmn_io.profile._stable_id import allocate_stable_id

    setup, compiled, types = _paste_setup()
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = copy.deepcopy(setup.bridge.envelope.tree)
    outcome = _prepare(
        setup,
        compiled,
        types,
        {
            "command": "surface",
            "entry": "task-paste",
            "context": {"owner": "Process_1", "key": "k-paste"},
            "fragment": _fragment(
                {
                    "property": "flowElements",
                    "element": {
                        "$type": "bpmn:Task",
                        "id": "Old_1",
                        "name": "Blue",
                    },
                }
            ),
        },
        tree,
    )
    assert outcome == "ok:paste-task"
    want_id = allocate_stable_id("Process_1", "paste", jcs(["k-paste", "Old_1"]))
    assert want_id.startswith("g_")
    flow = tree["rootElements"][0]["flowElements"]
    assert [element["id"] for element in flow] == ["Task_1", want_id]
    assert flow[1]["name"] == "Blue"


def test_paste_key_reuse_collides() -> None:
    """Replaying a paste key collides with the staged IDs."""
    setup, compiled, types = _paste_setup()
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = copy.deepcopy(setup.bridge.envelope.tree)
    command = {
        "command": "surface",
        "entry": "task-paste",
        "context": {"owner": "Process_1", "key": "k-same"},
        "fragment": _fragment(
            {
                "property": "flowElements",
                "element": {"$type": "bpmn:Task", "id": "Old_1"},
            }
        ),
    }
    assert _prepare(setup, compiled, types, command, tree) == "ok:paste-task"
    assert _prepare(setup, compiled, types, command, tree) == "id-collision"


def test_paste_dangling_external_ref_refuses() -> None:
    """A fragment reference to a missing stage element refuses."""
    setup, compiled, types = _paste_setup()
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = copy.deepcopy(setup.bridge.envelope.tree)
    assert (
        _prepare(
            setup,
            compiled,
            types,
            {
                "command": "surface",
                "entry": "task-paste",
                "context": {"owner": "Process_1", "key": "k-flow"},
                "fragment": _fragment(
                    {
                        "property": "flowElements",
                        "element": {
                            "$type": "bpmn:SequenceFlow",
                            "id": "Flow_9",
                            "sourceRef": "Ghost_9",
                            "targetRef": "Task_1",
                        },
                    }
                ),
            },
            tree,
        )
        == "reference-dangling"
    )


def test_paste_wrong_type_ref_refuses() -> None:
    """An external reference of an unadmitted type refuses."""
    setup, compiled, types = _paste_setup()
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = copy.deepcopy(setup.bridge.envelope.tree)
    assert (
        _prepare(
            setup,
            compiled,
            types,
            {
                "command": "surface",
                "entry": "task-paste",
                "context": {"owner": "Process_1", "key": "k-type"},
                "fragment": _fragment(
                    {
                        "property": "flowElements",
                        "element": {
                            "$type": "bpmn:SequenceFlow",
                            "id": "Flow_9",
                            "sourceRef": "Process_1",
                            "targetRef": "Task_1",
                        },
                    }
                ),
            },
            tree,
        )
        == "profile-type"
    )


def test_paste_unadmitted_property_refuses() -> None:
    """A root typed outside the owner property admission refuses."""
    setup, compiled, types = _paste_setup()
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = copy.deepcopy(setup.bridge.envelope.tree)
    assert (
        _prepare(
            setup,
            compiled,
            types,
            {
                "command": "surface",
                "entry": "task-paste",
                "context": {"owner": "Process_1", "key": "k-prop"},
                "fragment": _fragment(
                    {
                        "property": "artifacts",
                        "element": {"$type": "bpmn:Task", "id": "Old_2"},
                    }
                ),
            },
            tree,
        )
        == "profile-type"
    )


def test_paste_missing_fragment_refuses() -> None:
    """A paste entry without its fragment sibling refuses."""
    setup, compiled, types = _paste_setup()
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = copy.deepcopy(setup.bridge.envelope.tree)
    assert (
        _prepare(
            setup,
            compiled,
            types,
            {
                "command": "surface",
                "entry": "task-paste",
                "context": {"owner": "Process_1", "key": "k-nofrag"},
            },
            tree,
        )
        == "profile-ui-parameters"
    )


def test_paste_rewrites_internal_refs() -> None:
    """Fragment-internal references follow the reallocated IDs."""
    from bpmn_io.profile._c14n import jcs
    from bpmn_io.profile._stable_id import allocate_stable_id

    setup, compiled, types = _paste_setup()
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = copy.deepcopy(setup.bridge.envelope.tree)
    outcome = _prepare(
        setup,
        compiled,
        types,
        {
            "command": "surface",
            "entry": "task-paste",
            "context": {"owner": "Process_1", "key": "k-link"},
            "fragment": _fragment(
                {
                    "property": "artifacts",
                    "element": {
                        "$type": "bpmn:TextAnnotation",
                        "id": "Note_9",
                        "text": "see task",
                    },
                },
                {
                    "property": "artifacts",
                    "element": {
                        "$type": "bpmn:Association",
                        "id": "Assoc_9",
                        "sourceRef": "Note_9",
                        "targetRef": "Task_1",
                    },
                },
            ),
        },
        tree,
    )
    assert outcome == "ok:paste-task"
    note_id = allocate_stable_id("Process_1", "paste", jcs(["k-link", "Note_9"]))
    assoc_id = allocate_stable_id("Process_1", "paste", jcs(["k-link", "Assoc_9"]))
    artifacts = tree["rootElements"][0]["artifacts"]
    assert [element["id"] for element in artifacts] == [note_id, assoc_id]
    assert artifacts[1]["sourceRef"] == note_id
    assert artifacts[1]["targetRef"] == "Task_1"
