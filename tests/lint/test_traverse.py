"""Ported tests for ``bpmn_io.lint.traverse`` (upstream ``test/spec/traverse-spec.mjs``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bpmn_io.lint.testers.helper import create_moddle, read_moddle
from bpmn_io.lint.traverse import traverse
from tests.conftest import upstream_dir

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement

SPEC = upstream_dir("bpmnlint") / "test" / "spec"


def _logger(hooks: list[str] | None = None) -> tuple[list[str], dict[str, object]]:
    nodes: list[str] = []
    selected = hooks if hooks is not None else ["enter"]
    log: dict[str, object] = {}
    for hook in selected:

        def _record(node: ModdleElement, _hook: str = hook) -> None:
            element_id = node.get("id")
            label = node.type_ + (f"#{element_id}" if element_id else "")
            nodes.append(f"{label} - {_hook}")

        log[hook] = _record
    return nodes, log


_ONE_NODE_XML = """
<?xml version="1.0" encoding="UTF-8"?>
<definitions
    xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
    id="Definitions"
    targetNamespace="http://bpmn.io/bpmn">
</definitions>
"""

_GENERIC_XML = """
<?xml version="1.0" encoding="UTF-8"?>
<definitions
    xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
    xmlns:asd="http://asd"
    id="Definitions"
    targetNamespace="http://bpmn.io/bpmn">
  <extensionElements>
    <asd:foo bar="BAR" />
  </extensionElements>
</definitions>
"""

_PROCESS_XML = """
<?xml version="1.0" encoding="UTF-8"?>
<definitions
    xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
    id="Definitions"
    targetNamespace="http://bpmn.io/bpmn">
  <process id="Process_1"/>
</definitions>
"""

_TWO_PROCESSES_XML = """
<?xml version="1.0" encoding="UTF-8"?>
<definitions
    xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
    id="Definitions"
    targetNamespace="http://bpmn.io/bpmn">
  <bpmn:process id="Process_1">
    <bpmn:task id="Task_1" />
  </bpmn:process>
  <bpmn:process id="Process_2">
    <bpmn:task id="Task_2" />
  </bpmn:process>
</definitions>
"""


@pytest.mark.upstream(
    "bpmnlint/test/spec/traverse-spec.mjs",
    "traverse > traversal > should traverse diagram with one node",
)
def test_traverse_one_node() -> None:
    root = create_moddle(_ONE_NODE_XML)["root"]
    nodes, log = _logger()
    traverse(root, log)
    assert nodes == ["bpmn:Definitions#Definitions - enter"]


@pytest.mark.upstream(
    "bpmnlint/test/spec/traverse-spec.mjs",
    "traverse > traversal > should traverse diagram with generic element",
)
def test_traverse_generic_element() -> None:
    root = create_moddle(_GENERIC_XML)["root"]
    nodes, log = _logger()
    traverse(root, log)
    assert nodes == [
        "bpmn:Definitions#Definitions - enter",
        "bpmn:ExtensionElements - enter",
        "asd:foo - enter",
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/traverse-spec.mjs",
    "traverse > traversal > should traverse diagram with collaboration",
)
def test_traverse_collaboration() -> None:
    root = read_moddle(SPEC / "diagram.bpmn")["root"]
    nodes, log = _logger()
    traverse(root, log)
    assert nodes == [
        "bpmn:Definitions#sid-38422fae-e03e-43a3-bef4-bd33b32041b2 - enter",
        "bpmn:Collaboration#Collaboration_0wzd2dx - enter",
        "bpmn:Participant#Participant_03hz6qm - enter",
        "bpmn:Participant#Participant_1w6hx42 - enter",
        "bpmn:MessageFlow#MessageFlow_1ofxm38 - enter",
        "bpmn:Process#Process_1 - enter",
        "bpmndi:BPMNDiagram#BpmnDiagram_1 - enter",
        "bpmndi:BPMNPlane#BpmnPlane_1 - enter",
        "bpmndi:BPMNShape#Participant_03hz6qm_di - enter",
        "dc:Bounds - enter",
        "bpmndi:BPMNEdge#MessageFlow_1ofxm38_di - enter",
        "dc:Point - enter",
        "dc:Point - enter",
        "bpmndi:BPMNShape#Participant_1sh3ce3_di - enter",
        "dc:Bounds - enter",
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/traverse-spec.mjs",
    "traverse > traversal > should traverse diagram with simple process",
)
def test_traverse_simple_process() -> None:
    root = read_moddle(SPEC / "process-diagram.bpmn")["root"]
    nodes, log = _logger()
    traverse(root, log)
    assert nodes == [
        "bpmn:Definitions#Definitions_1 - enter",
        "bpmn:Process#Process_1 - enter",
        "bpmn:StartEvent#Event_1 - enter",
        "bpmn:Task#Activity_1 - enter",
        "bpmn:SequenceFlow#Flow_1 - enter",
        "bpmndi:BPMNDiagram#BpmnDiagram_1 - enter",
        "bpmndi:BPMNPlane#BpmnPlane_1 - enter",
        "bpmndi:BPMNEdge#Flow_1_di - enter",
        "dc:Point - enter",
        "dc:Point - enter",
        "bpmndi:BPMNShape#Event_1_di - enter",
        "dc:Bounds - enter",
        "bpmndi:BPMNLabel - enter",
        "dc:Bounds - enter",
        "bpmndi:BPMNShape#Activity_1_di - enter",
        "dc:Bounds - enter",
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/traverse-spec.mjs",
    "traverse > enter/leave hooks > should <enter> and <leave>",
)
def test_traverse_enter_and_leave() -> None:
    root = create_moddle(_PROCESS_XML)["root"]
    nodes, log = _logger(["enter", "leave"])
    traverse(root, log)
    assert nodes == [
        "bpmn:Definitions#Definitions - enter",
        "bpmn:Process#Process_1 - enter",
        "bpmn:Process#Process_1 - leave",
        "bpmn:Definitions#Definitions - leave",
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/traverse-spec.mjs",
    "traverse > enter/leave hooks > should <leave> only",
)
def test_traverse_leave_only() -> None:
    root = create_moddle(_PROCESS_XML)["root"]
    nodes, log = _logger(["leave"])
    traverse(root, log)
    assert nodes == [
        "bpmn:Process#Process_1 - leave",
        "bpmn:Definitions#Definitions - leave",
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/traverse-spec.mjs",
    "traverse > enter/leave hooks > should <enter> and <leave> generic element",
)
def test_traverse_enter_leave_generic() -> None:
    root = create_moddle(_GENERIC_XML)["root"]
    nodes, log = _logger(["enter", "leave"])
    traverse(root, log)
    assert nodes == [
        "bpmn:Definitions#Definitions - enter",
        "bpmn:ExtensionElements - enter",
        "asd:foo - enter",
        "asd:foo - leave",
        "bpmn:ExtensionElements - leave",
        "bpmn:Definitions#Definitions - leave",
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/traverse-spec.mjs",
    "traverse > sub-tree skipping > should skip if <enter> returns false",
)
def test_traverse_skip_subtree() -> None:
    root = create_moddle(_TWO_PROCESSES_XML)["root"]
    nodes, log = _logger(["enter", "leave"])

    def enter(node: ModdleElement) -> object:
        log["enter"](node)
        if node.get("id") == "Process_1":
            return False
        return None

    traverse(root, enter=enter, leave=log["leave"])
    assert nodes == [
        "bpmn:Definitions#Definitions - enter",
        "bpmn:Process#Process_1 - enter",
        "bpmn:Process#Process_1 - leave",
        "bpmn:Process#Process_2 - enter",
        "bpmn:Task#Task_2 - enter",
        "bpmn:Task#Task_2 - leave",
        "bpmn:Process#Process_2 - leave",
        "bpmn:Definitions#Definitions - leave",
    ]


@pytest.mark.upstream(
    "bpmnlint/test/spec/traverse-spec.mjs",
    "traverse > sub-tree skipping > should skip if node is simple type",
)
def test_traverse_skip_simple_type() -> None:
    xml = """
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    xmlns:stm="http://about:blank/schema/bpmn/stm"
    id="Definitions"
    targetNamespace="http://bpmn.io/bpmn">
  <bpmn:process id="Process_1">
    <bpmn:task id="Task_1">
      <bpmn:extensionElements>
        <stm:SimpleTypeParameters>
          <stm:p1>hello world</stm:p1>
          <stm:p2>true</stm:p2>
          <stm:p3>1</stm:p3>
          <stm:p4>1.2</stm:p4>
        </stm:SimpleTypeParameters>
      </bpmn:extensionElements>
    </bpmn:task>
  </bpmn:process>
</bpmn:definitions>
"""
    stm_package: dict[str, object] = {
        "name": "SimpleTypeModdle",
        "uri": "http://about:blank/schema/bpmn/stm",
        "prefix": "stm",
        "xml": {"tagAlias": "lowerCase"},
        "types": [
            {
                "name": "SimpleTypeParameters",
                "superClass": ["Element"],
                "properties": [
                    {"name": "p1", "type": "String"},
                    {"name": "p2", "type": "Boolean"},
                    {"name": "p3", "type": "Integer"},
                    {"name": "p4", "type": "Real"},
                ],
            },
        ],
    }
    root = create_moddle(xml, {"stm": stm_package})["root"]
    nodes, log = _logger(["enter", "leave"])
    traverse(root, log)
    assert nodes == [
        "bpmn:Definitions#Definitions - enter",
        "bpmn:Process#Process_1 - enter",
        "bpmn:Task#Task_1 - enter",
        "bpmn:ExtensionElements - enter",
        "stm:SimpleTypeParameters - enter",
        "stm:SimpleTypeParameters - leave",
        "bpmn:ExtensionElements - leave",
        "bpmn:Task#Task_1 - leave",
        "bpmn:Process#Process_1 - leave",
        "bpmn:Definitions#Definitions - leave",
    ]
