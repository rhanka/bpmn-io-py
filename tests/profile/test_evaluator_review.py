"""Evaluator review regressions (finding #3).

Expectations come from DESIGN R3.3 §2.2/§2.5 tables: ``assignable`` uses
native descriptor inheritance (a Task is not a Process), ``reference``
selects the referenced targets, ``recognizes`` evaluates the notion,
``reachable`` decides directed bounded reachability, and render
traversals outside an export context refuse with ``profile-value-context``.
"""

from __future__ import annotations

from typing import Any

_LINK_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Defs_1">'
    '<bpmn:process id="P1"><bpmn:task id="T1" name="T" />'
    '<bpmn:sequenceFlow id="F1" sourceRef="T1" targetRef="T2" />'
    '<bpmn:task id="T2" name="U" /></bpmn:process>'
    "</bpmn:definitions>"
)


def _native_link() -> object:
    from bpmn_io import create_moddle

    moddle = create_moddle()
    result = moddle.from_xml(_LINK_XML)
    assert result.root_element is not None
    return result.root_element


def _native_tasks() -> tuple[object, object, object]:
    from bpmn_io import create_moddle

    moddle = create_moddle()
    task = moddle.create("bpmn:Task", {"id": "T1"})
    service = moddle.create("bpmn:ServiceTask", {"id": "S1"})
    process = moddle.create("bpmn:Process", {"id": "P1"})
    return task, service, process


def test_assignable_uses_native_inheritance() -> None:
    """A Task is not assignable to Process; a ServiceTask is a Task."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    task, service, process = _native_tasks()
    context = make_read_context(process)
    exact = {"op": "typeIs", "binding": "self", "type": "bpmn:Process", "mode": "exact"}
    assignable = {"op": "typeIs", "binding": "self", "type": "bpmn:Process", "mode": "assignable"}
    task_result = evaluate_predicate(assignable, context, {"self": task})
    assert task_result.status == "ok"
    assert task_result.payload is False  # type: ignore[union-attr]
    exact_result = evaluate_predicate(exact, context, {"self": task})
    assert exact_result.payload is False  # type: ignore[union-attr]
    service_assignable = {
        "op": "typeIs",
        "binding": "self",
        "type": "bpmn:Task",
        "mode": "assignable",
    }
    service_result = evaluate_predicate(service_assignable, context, {"self": service})
    assert service_result.status == "ok"
    assert service_result.payload is True  # type: ignore[union-attr]
    service_exact = {"op": "typeIs", "binding": "self", "type": "bpmn:Task", "mode": "exact"}
    assert evaluate_predicate(service_exact, context, {"self": service}).payload is False  # type: ignore[union-attr]


def test_assignable_dict_tree_falls_back_to_exact() -> None:
    """Plain-dict elements without hierarchy degrade to exact matching."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    task = {"$type": "bpmn:Task", "id": "T1"}
    context = make_read_context({"$type": "bpmn:Definitions", "rootElements": [task]})
    assignable = {"op": "typeIs", "binding": "self", "type": "bpmn:Process", "mode": "assignable"}
    result = evaluate_predicate(assignable, context, {"self": task})
    assert result.status == "ok"
    assert result.payload is False  # type: ignore[union-attr]


def _dict_graph() -> dict[str, Any]:
    task_one = {"$type": "bpmn:Task", "id": "T1"}
    task_two = {"$type": "bpmn:Task", "id": "T2"}
    flow = {"$type": "bpmn:SequenceFlow", "id": "F1", "sourceRef": "T1", "targetRef": "T2"}
    return {"$type": "bpmn:Definitions", "rootElements": [task_one, task_two, flow]}


def test_reference_selects_targets_not_source() -> None:
    """A reference traversal selects the referenced elements."""
    from bpmn_io.profile import select
    from bpmn_io.profile._evaluate import make_read_context

    graph = _dict_graph()
    context = make_read_context(graph)
    flow = graph["rootElements"][2]
    selector = {"from": "edge", "via": "reference", "property": "sourceRef", "order": "id"}
    result = select(selector, context, {"edge": flow})
    assert result.status == "ok"
    payload = result.payload  # type: ignore[union-attr]
    assert [handle.element_id for handle in payload] == ["T1"]


def test_reference_resolves_native_element_objects() -> None:
    """Native reference properties holding elements resolve directly."""
    from bpmn_io.profile import select
    from bpmn_io.profile._evaluate import make_read_context

    context = make_read_context(_native_link())
    flow = context.by_id["F1"]
    selector = {"from": "edge", "via": "reference", "property": "sourceRef", "order": "id"}
    result = select(selector, context, {"edge": flow})
    assert result.status == "ok"
    payload = result.payload  # type: ignore[union-attr]
    assert [handle.element_id for handle in payload] == ["T1"]
    task = context.by_id["T1"]
    inverse = {
        "from": "node",
        "via": "inverseReference",
        "property": "sourceRef",
        "order": "id",
    }
    inverted = select(inverse, context, {"node": task})
    assert inverted.status == "ok"
    inv_payload = inverted.payload  # type: ignore[union-attr]
    assert [handle.element_id for handle in inv_payload] == ["F1"]


def test_inverse_reference_finds_referrers() -> None:
    """An inverse traversal selects the elements pointing at the base."""
    from bpmn_io.profile import select
    from bpmn_io.profile._evaluate import make_read_context

    graph = _dict_graph()
    context = make_read_context(graph)
    task = graph["rootElements"][0]
    selector = {
        "from": "node",
        "via": "inverseReference",
        "property": "sourceRef",
        "order": "id",
    }
    result = select(selector, context, {"node": task})
    assert result.status == "ok"
    payload = result.payload  # type: ignore[union-attr]
    assert [handle.element_id for handle in payload] == ["F1"]


def _annotation_tree() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    task = {"$type": "bpmn:Task", "id": "T1"}
    note = {"$type": "bpmn:TextAnnotation", "id": "N1", "text": "hello"}
    root = {"$type": "bpmn:Definitions", "rootElements": [task, note]}
    return root, task, note


_AID_NOTIONS = {
    "aid": {
        "recognition": {
            "op": "typeIs",
            "binding": "self",
            "type": "bpmn:TextAnnotation",
            "mode": "exact",
        }
    }
}


def test_recognizes_evaluates_the_notion() -> None:
    """``recognizes`` runs the notion recognition on the bound element."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    root, task, note = _annotation_tree()
    context = make_read_context(root, notions=_AID_NOTIONS)
    predicate = {"op": "recognizes", "binding": "item", "notion": "aid"}
    assert evaluate_predicate(predicate, context, {"item": note}).payload is True  # type: ignore[union-attr]
    assert evaluate_predicate(predicate, context, {"item": task}).payload is False  # type: ignore[union-attr]


def test_recognizes_unknown_notion_refuses() -> None:
    """An undeclared notion refuses with ``profile-symbol``."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    root, _task, note = _annotation_tree()
    context = make_read_context(root)
    predicate = {"op": "recognizes", "binding": "item", "notion": "ghost"}
    result = evaluate_predicate(predicate, context, {"item": note})
    assert result.status == "refused"
    assert result.code == "profile-symbol"  # type: ignore[union-attr]


def test_reachable_follows_resolved_edges() -> None:
    """Reachability follows sourceRef to targetRef edges within hop bounds."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    graph = _dict_graph()
    context = make_read_context(graph)
    tasks = {element["id"]: element for element in graph["rootElements"]}
    bindings = {"one": tasks["T1"], "two": tasks["T2"]}
    predicate = {
        "op": "reachable",
        "from": {"from": "one", "via": "self", "order": "id"},
        "to": {"from": "two", "via": "self", "order": "id"},
        "edgeTypes": ["bpmn:SequenceFlow"],
        "minHops": 1,
    }
    result = evaluate_predicate(predicate, context, bindings)
    assert result.status == "ok"
    assert result.payload is True  # type: ignore[union-attr]


def test_reachable_reports_direction_and_bounds() -> None:
    """Reverse direction fails and hop bounds are enforced."""
    from bpmn_io.profile import evaluate_predicate
    from bpmn_io.profile._evaluate import make_read_context

    graph = _dict_graph()
    context = make_read_context(graph)
    tasks = {element["id"]: element for element in graph["rootElements"]}
    backward = {
        "op": "reachable",
        "from": {"from": "two", "via": "self", "order": "id"},
        "to": {"from": "one", "via": "self", "order": "id"},
        "edgeTypes": ["bpmn:SequenceFlow"],
        "minHops": 1,
    }
    bindings = {"one": tasks["T1"], "two": tasks["T2"]}
    assert evaluate_predicate(backward, context, bindings).payload is False  # type: ignore[union-attr]
    too_far = {
        "op": "reachable",
        "from": {"from": "one", "via": "self", "order": "id"},
        "to": {"from": "two", "via": "self", "order": "id"},
        "edgeTypes": ["bpmn:SequenceFlow"],
        "minHops": 2,
    }
    assert evaluate_predicate(too_far, context, bindings).payload is False  # type: ignore[union-attr]


def test_render_traversal_refuses_outside_export() -> None:
    """Pages/occurrences/semantic refuse without a render context."""
    from bpmn_io.profile import select
    from bpmn_io.profile._evaluate import make_read_context

    context = make_read_context(_native_link())
    for via in ("pages", "occurrences", "semantic"):
        selector = {"from": "root", "via": via, "order": "page-occurrence"}
        if via == "semantic":
            selector["order"] = "id"
        result = select(selector, context, {})
        assert result.status == "refused", via
        assert result.code == "profile-value-context"  # type: ignore[union-attr]
