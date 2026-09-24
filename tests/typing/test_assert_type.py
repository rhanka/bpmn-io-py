"""Static narrowing sample for the generated stub (explicit mypy target).

The repository mypy gate (``packages = ["bpmn_io"]``) does not cover
``tests/`` by design, so this file is not part of that gate: check it with
``python -m mypy tests/typing/test_assert_type.py``. The ``static_*`` samples
below never run (their stub-only names exist for type-checking only); the
``test_*`` functions assert the same behavior at runtime under pytest.

The stub-only names below cannot be imported at runtime (they exist solely in
``types.pyi``), hence the file-wide TC004 exemption: ``assert_type`` evaluates
its type argument at runtime, but the ``static_*`` samples never execute.
"""
# ruff: noqa: TC004

from __future__ import annotations

from typing import TYPE_CHECKING, assert_type, cast

from bpmn_io.bpmn_moddle.simple import create_moddle
from bpmn_io.bpmn_moddle.types import is_a
from bpmn_io.moddle.base import ModdleElement

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle.types import (
        BpmndiBPMNEdge,
        BpmndiBPMNShape,
        BpmnExclusiveGateway,
        BpmnProcess,
        BpmnSequenceFlow,
        BpmnServiceTask,
        BpmnStartEvent,
        BpmnTask,
        DcBounds,
        DcPoint,
        DiDiagramElement,
        DiShape,
        TypedBpmnModdle,
    )


def static_create_sample() -> None:
    """Literal create() calls carry their element type (static only)."""
    model = cast("TypedBpmnModdle", create_moddle())

    task = model.create("bpmn:Task", {"name": "T"})
    assert_type(task, BpmnTask)
    assert_type(task.name, str)

    service = model.create("bpmn:ServiceTask")
    assert_type(service, BpmnServiceTask)

    process = model.create("bpmn:Process")
    assert_type(process, BpmnProcess)

    gateway = model.create("bpmn:ExclusiveGateway")
    assert_type(gateway, BpmnExclusiveGateway)

    flow = model.create("bpmn:SequenceFlow")
    assert_type(flow, BpmnSequenceFlow)

    event = model.create("bpmn:StartEvent")
    assert_type(event, BpmnStartEvent)

    shape = model.create("bpmndi:BPMNShape")
    assert_type(shape, BpmndiBPMNShape)

    edge = model.create("bpmndi:BPMNEdge")
    assert_type(edge, BpmndiBPMNEdge)

    bounds = model.create("dc:Bounds")
    assert_type(bounds, DcBounds)

    point = model.create("dc:Point")
    assert_type(point, DcPoint)

    diagram_shape = model.create("di:Shape")
    assert_type(diagram_shape, DiShape)

    diagram_element = model.create("di:DiagramElement")
    assert_type(diagram_element, DiDiagramElement)


def static_fallback_sample() -> None:
    """A plain str still creates, typed as the generic element (static only)."""
    model = cast("TypedBpmnModdle", create_moddle())
    name: str = "bpmn:ServiceTask"
    element = model.create(name)
    assert_type(element, ModdleElement)


def static_is_a_sample() -> None:
    """is_a() narrows the element type in the positive branch (static only)."""
    model = cast("TypedBpmnModdle", create_moddle())
    element: ModdleElement = model.create("bpmn:Process")
    assert_type(element, ModdleElement)
    if is_a(element, "bpmn:Task"):
        assert_type(element, BpmnTask)
    else:
        assert_type(element, ModdleElement)


def test_create_literal_sample() -> None:
    """Runtime behavior behind the static create() sample."""
    model = create_moddle()
    expected = [
        "bpmn:Task",
        "bpmn:ServiceTask",
        "bpmn:Process",
        "bpmn:ExclusiveGateway",
        "bpmn:SequenceFlow",
        "bpmn:StartEvent",
        "bpmndi:BPMNShape",
        "bpmndi:BPMNEdge",
        "dc:Bounds",
        "dc:Point",
        "di:Shape",
        "di:DiagramElement",
    ]
    for qualname in expected:
        element = model.create(qualname)
        assert element.type_ == qualname
        assert isinstance(element, ModdleElement)
    task = model.create("bpmn:Task", {"name": "T"})
    assert task.get("name") == "T"


def test_create_fallback() -> None:
    """Runtime behavior behind the static fallback sample."""
    model = create_moddle()
    name = "bpmn:ServiceTask"
    element = model.create(name)
    assert element.type_ == "bpmn:ServiceTask"
    assert isinstance(element, ModdleElement)


def test_is_a_narrows() -> None:
    """Runtime behavior behind the static is_a() sample."""
    model = create_moddle()
    element = model.create("bpmn:Process")
    assert is_a(element, "bpmn:Process")
    assert not is_a(element, "bpmn:Task")
    assert not is_a(None, "bpmn:Task")
