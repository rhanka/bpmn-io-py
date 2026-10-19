"""Synthetic command-validation tests on the grid profile (no lot-3).

Exercises checks (a)-(h) of ``prepare_command`` directly: closed record
shapes, entry/upstream/field resolution, context sources, handle checks,
``ui.when`` and field authorization, value typing and paste compilation.
Staging and recipe execution stay with the sealed case runner.
"""

from __future__ import annotations

import pytest

from bpmn_io.profile._commands import (
    CommandError,
    build_stage_index,
    prepare_command,
)
from tests.profile_commands import harness


def _grid() -> harness.Setup:
    case = harness.read_case("surface-palette-entries-grid")
    setup = harness.make_setup(case)
    assert setup.compiled is not None, getattr(setup, "compile_refusal", None)
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    return setup


def _prepare(setup: harness.Setup, command: dict[str, object]) -> str:
    assert setup.compiled is not None
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = setup.bridge.envelope.tree
    try:
        prepared = prepare_command(setup.compiled, tree, build_stage_index(tree), command, {})
    except CommandError as exc:
        return exc.code
    return f"ok:{prepared.recipe_id}"


def test_surface_ok() -> None:
    """A well-formed palette command prepares its recipe."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "surface",
                "entry": "task-create",
                "context": {"owner": "Process_1", "key": "k1", "value": "Draft"},
            },
        )
        == "ok:create-task"
    )


def test_bare_recipe_refuses() -> None:
    """A record without a command member is not a UI entry."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {"recipe": "create-task", "parameters": {}},
        )
        == "transaction-entry-unsupported"
    )


def test_unknown_entry_refuses() -> None:
    """An unlisted surface entry refuses."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "surface",
                "entry": "no-such-entry",
                "context": {"owner": "Process_1", "key": "k", "value": "v"},
            },
        )
        == "profile-symbol"
    )


def test_unlisted_upstream_refuses() -> None:
    """An upstream ID outside the compiled map refuses."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "upstream",
                "upstream": "create.ghost",
                "context": {"owner": "Process_1", "key": "k", "value": "v"},
            },
        )
        == "transaction-entry-unsupported"
    )


def test_extra_context_member_refuses() -> None:
    """A context with a member outside the bound sources refuses."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "surface",
                "entry": "task-create",
                "context": {
                    "owner": "Process_1",
                    "key": "k1",
                    "value": "Draft",
                    "extra": "x",
                },
            },
        )
        == "profile-ui-parameters"
    )


def test_missing_context_source_refuses() -> None:
    """A context missing a bound source refuses."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "surface",
                "entry": "task-create",
                "context": {"owner": "Process_1", "key": "k1"},
            },
        )
        == "profile-ui-parameters"
    )


def test_dangling_handle_refuses() -> None:
    """A handle missing from the stage refuses."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "surface",
                "entry": "task-create",
                "context": {"owner": "Ghost_9", "key": "k1", "value": "Draft"},
            },
        )
        == "reference-dangling"
    )


def test_when_false_refuses() -> None:
    """An entry whose listing predicate is false refuses programmatically."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "surface",
                "entry": "aid-create",
                "context": {"owner": "Task_1", "key": "k1", "value": "Aid"},
            },
        )
        == "profile-producer"
    )


def test_coerced_value_refuses() -> None:
    """A value that would need coercion refuses."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "surface",
                "entry": "task-create",
                "context": {"owner": "Process_1", "key": "k1", "value": 7},
            },
        )
        == "profile-type"
    )


def test_field_command_ok() -> None:
    """A well-formed field command prepares its recipe."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "field",
                "notion": "task",
                "field": "name",
                "context": {"target": "Task_1", "value": "Renamed"},
            },
        )
        == "ok:rename"
    )


def test_field_unknown_notion_refuses() -> None:
    """A field naming an undeclared notion refuses."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "field",
                "notion": "ghost",
                "field": "name",
                "context": {"target": "Task_1", "value": "x"},
            },
        )
        == "profile-symbol"
    )


def test_field_unrecognized_target_refuses() -> None:
    """A field whose target is not recognized as the notion refuses."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "field",
                "notion": "task",
                "field": "name",
                "context": {"target": "Process_1", "value": "x"},
            },
        )
        == "profile-type"
    )


def test_field_omitted_value_refuses() -> None:
    """A field command omitting a bound value refuses."""
    setup = _grid()
    assert (
        _prepare(
            setup,
            {
                "command": "field",
                "notion": "task",
                "field": "name",
                "context": {"target": "Task_1"},
            },
        )
        == "profile-ui-parameters"
    )


def test_delete_intent_flags() -> None:
    """Delete and replace surfaces plan with explicit deletion intent."""
    setup = _grid()
    assert setup.compiled is not None
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = setup.bridge.envelope.tree
    prepared = prepare_command(
        setup.compiled,
        tree,
        build_stage_index(tree),
        {
            "command": "surface",
            "entry": "task-create",
            "context": {"owner": "Process_1", "key": "k1", "value": "Draft"},
        },
        {},
    )
    assert prepared.deletion_intent is False
    assert prepared.subject_id == "Process_1"
    assert prepared.params == {"owner": "Process_1", "key": "k1", "name": "Draft"}


def test_non_object_command_refuses() -> None:
    """A non-object batch member is not a UI entry."""
    setup = _grid()
    assert setup.compiled is not None
    assert setup.bridge is not None
    assert setup.bridge.envelope is not None
    tree = setup.bridge.envelope.tree
    with pytest.raises(CommandError) as excinfo:
        prepare_command(setup.compiled, tree, build_stage_index(tree), ["surface"], {})
    assert excinfo.value.code == "transaction-entry-unsupported"
