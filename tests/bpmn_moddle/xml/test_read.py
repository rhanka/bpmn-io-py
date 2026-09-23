"""Ported bpmn-moddle read cases (Lot 7).

Transcribes every ``bpmn-moddle/test/spec/xml/read.js`` ``it()`` title: one
test per claim (50 claims, including the two same-file ``when importing
non-xml text`` occurrences, one under ``should handle errors`` and one under
``should read attributes``). Verification mirrors the upstream assertions:
``jsonEqual`` becomes ``json_equal``, ``eql`` becomes ``==``, ``match``
becomes ``re.search`` and promise rejections become
``pytest.raises(ParseError)``. Only the public ``bpmn_io`` API plus the
``tests._matchers`` helper is used.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from bpmn_io import create_moddle
from bpmn_io.moddle_xml import ParseError
from tests._matchers import json_equal

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle
    from bpmn_io.moddle_xml import ParseResult

FIXTURES = (
    Path(__file__).resolve().parent.parent.parent
    / "upstream"
    / "bpmn-moddle"
    / "test"
    / "fixtures"
    / "bpmn"
)


def _moddle() -> BpmnModdle:
    """Create the default six-package BPMN model, as the upstream helper."""
    return create_moddle()


def _from_fixture(
    name: str,
    root: str = "bpmn:Definitions",
    *,
    moddle: BpmnModdle | None = None,
) -> ParseResult:
    """Parse a vendored BPMN fixture, as the upstream ``fromFile`` helper."""
    model = moddle if moddle is not None else _moddle()
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    return model.from_xml(xml, root)


# should import types > bpmn


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "SubProcess#flowElements")
def test_001_sub_process_flow_elements() -> None:
    result = _from_fixture("sub-process-flow-nodes.part.bpmn", "bpmn:SubProcess")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:SubProcess",
            "id": "SubProcess_1",
            "name": "Sub Process 1",
            "flowElements": [
                {"$type": "bpmn:StartEvent", "id": "StartEvent_1", "name": "Start Event 1"},
                {"$type": "bpmn:Task", "id": "Task_1", "name": "Task"},
                {"$type": "bpmn:SequenceFlow", "id": "SequenceFlow_1", "name": ""},
            ],
        },
    )


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/read.js", "SubProcess#flowElements (nested references)"
)
def test_002_sub_process_flow_elements_nested() -> None:
    result = _from_fixture("sub-process.part.bpmn", "bpmn:SubProcess")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:SubProcess",
            "id": "SubProcess_1",
            "name": "Sub Process 1",
            "flowElements": [
                {"$type": "bpmn:StartEvent", "id": "StartEvent_1", "name": "Start Event 1"},
                {"$type": "bpmn:Task", "id": "Task_1", "name": "Task"},
                {"$type": "bpmn:SequenceFlow", "id": "SequenceFlow_1", "name": ""},
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "CompensateEventDefinition")
def test_003_compensate_event_definition() -> None:
    result = _from_fixture(
        "compensate-event-definition.part.bpmn", "bpmn:CompensateEventDefinition"
    )

    assert json_equal(result.root_element, {"$type": "bpmn:CompensateEventDefinition"})
    assert result.root_element.get("waitForCompletion") is True


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "SubProcess#incoming")
def test_004_sub_process_incoming() -> None:
    result = _from_fixture("subprocess-flow-nodes-outgoing.part.bpmn", "bpmn:Process")

    expected_sequence_flow: dict[str, Any] = {
        "$type": "bpmn:SequenceFlow",
        "id": "SequenceFlow_1",
    }
    expected_sub_process: dict[str, Any] = {
        "$type": "bpmn:SubProcess",
        "id": "SubProcess_1",
        "name": "Sub Process 1",
        "flowElements": [{"$type": "bpmn:Task", "id": "Task_1", "name": "Task"}],
    }

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Process",
            "flowElements": [expected_sub_process, expected_sequence_flow],
        },
    )

    flow_elements = result.root_element.get("flowElements")
    assert isinstance(flow_elements, list)
    sub_process, sequence_flow = flow_elements

    assert json_equal(sub_process.get("incoming"), [expected_sequence_flow])
    assert json_equal(sub_process.get("outgoing"), [expected_sequence_flow])
    assert json_equal(sequence_flow.get("sourceRef"), expected_sub_process)
    assert json_equal(sequence_flow.get("targetRef"), expected_sub_process)


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "TimerEventDefinition#expression")
def test_005_timer_event_definition_expression() -> None:
    result = _from_fixture("timerEventDefinition.part.bpmn", "bpmn:TimerEventDefinition")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:TimerEventDefinition",
            "id": "Definition_1",
            "timeCycle": {
                "$type": "bpmn:FormalExpression",
                "id": "TimeCycle_1",
                "body": "1w",
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Documentation")
def test_006_documentation() -> None:
    result = _from_fixture("documentation.bpmn")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Definitions",
            "id": "documentation",
            "targetNamespace": "http://bpmn.io/schema/bpmn",
            "rootElements": [
                {
                    "$type": "bpmn:Process",
                    "id": "Process_1",
                    "documentation": [{"$type": "bpmn:Documentation", "text": "THIS IS A PROCESS"}],
                    "flowElements": [
                        {
                            "$type": "bpmn:SubProcess",
                            "id": "SubProcess_1",
                            "name": "Sub Process 1",
                            "documentation": [
                                {
                                    "$type": "bpmn:Documentation",
                                    "text": "<h1>THIS IS HTML</h1>",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "ThrowEvent#dataInputAssociations")
def test_007_throw_event_data_input_associations() -> None:
    result = _from_fixture("throw-event-dataInputAssociations.part.bpmn", "bpmn:EndEvent")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:EndEvent",
            "id": "EndEvent_1",
            "dataInputAssociations": [
                {"$type": "bpmn:DataInputAssociation", "id": "DataInputAssociation_1"}
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "CatchEvent#dataOutputAssociations")
def test_008_catch_event_data_output_associations() -> None:
    result = _from_fixture("catch-event-dataOutputAssociations.part.bpmn", "bpmn:StartEvent")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:StartEvent",
            "id": "StartEvent_1",
            "dataOutputAssociations": [
                {"$type": "bpmn:DataOutputAssociation", "id": "DataOutputAssociation_1"}
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Escalation + Error")
def test_009_escalation_error() -> None:
    result = _from_fixture("escalation-error.bpmn")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Definitions",
            "id": "test",
            "targetNamespace": "http://bpmn.io/schema/bpmn",
            "rootElements": [
                {"$type": "bpmn:Escalation", "id": "escalation"},
                {"$type": "bpmn:Error", "id": "error"},
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "ExtensionElements")
def test_010_extension_elements() -> None:
    result = _from_fixture("extension-elements.bpmn")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Definitions",
            "id": "test",
            "targetNamespace": "http://bpmn.io/schema/bpmn",
            "extensionElements": {
                "$type": "bpmn:ExtensionElements",
                "values": [
                    {"$type": "vendor:info", "key": "bgcolor", "value": "#ffffff"},
                    {"$type": "vendor:info", "key": "role", "value": "[]"},
                ],
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "ScriptTask")
def test_011_script_task() -> None:
    result = _from_fixture("scriptTask-script.part.bpmn", "bpmn:ScriptTask")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:ScriptTask",
            "id": "ScriptTask_4",
            "scriptFormat": "Javascript",
            "script": 'context.set("FOO", "BAR");',
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "CallActivity#calledElement")
def test_012_call_activity_called_element() -> None:
    result = _from_fixture("callActivity-calledElement.part.bpmn", "bpmn:CallActivity")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:CallActivity",
            "id": "CallActivity_1",
            "calledElement": "otherProcess",
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "ItemDefinition#structureRef")
def test_013_item_definition_structure_ref() -> None:
    result = _from_fixture("itemDefinition-structureRef.part.bpmn", "bpmn:ItemDefinition")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:ItemDefinition",
            "id": "itemDefinition",
            "structureRef": "foo:Service",
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Operation#implementationRef")
def test_014_operation_implementation_ref() -> None:
    result = _from_fixture("operation-implementationRef.part.bpmn", "bpmn:Operation")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Operation",
            "id": "operation",
            "implementationRef": "foo:operation",
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Interface#implementationRef")
def test_015_interface_implementation_ref() -> None:
    result = _from_fixture("interface-implementationRef.part.bpmn", "bpmn:Interface")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Interface",
            "id": "interface",
            "implementationRef": "foo:interface",
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Lane#childLaneSet")
def test_016_lane_child_lane_set() -> None:
    result = _from_fixture("lane-childLaneSets.part.bpmn", "bpmn:Lane")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Lane",
            "id": "Lane_1",
            "name": "Lane",
            "childLaneSet": {
                "$type": "bpmn:LaneSet",
                "id": "LaneSet_2",
                "lanes": [{"$type": "bpmn:Lane", "id": "Lane_2", "name": "Nested Lane"}],
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "SequenceFlow#conditionExpression")
def test_017_sequence_flow_condition_expression() -> None:
    result = _from_fixture("sequenceFlow-conditionExpression.part.bpmn", "bpmn:SequenceFlow")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:SequenceFlow",
            "id": "SequenceFlow_1",
            "conditionExpression": {
                "$type": "bpmn:FormalExpression",
                "body": "${foo > bar}",
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Category")
def test_018_category() -> None:
    result = _from_fixture("category.bpmn")

    root_elements = result.root_element.get("rootElements")
    assert isinstance(root_elements, list)
    category = root_elements[0]

    assert json_equal(
        category,
        {
            "$type": "bpmn:Category",
            "id": "sid-ccc7e63e-916e-4bd0-a9f0-98cbff749195",
            "categoryValue": [
                {
                    "$type": "bpmn:CategoryValue",
                    "id": "sid-afd7e63e-916e-4bd0-a9f0-98cbff749193",
                    "value": "group with label",
                }
            ],
        },
    )


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/read.js", "MultiInstanceLoopCharacteristics#completionCondition"
)
def test_019_multi_instance_completion_condition() -> None:
    result = _from_fixture(
        "multiInstanceLoopCharacteristics-completionCondition.part.bpmn",
        "bpmn:MultiInstanceLoopCharacteristics",
    )

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:MultiInstanceLoopCharacteristics",
            "completionCondition": {
                "$type": "bpmn:FormalExpression",
                "body": "${foo > bar}",
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Operation#messageRef")
def test_020_operation_message_ref() -> None:
    result = _from_fixture("operation-messageRef.bpmn", "bpmn:Definitions")

    expected_element: dict[str, Any] = {
        "$type": "bpmn:Operation",
        "id": "operation",
        "name": "foo",
    }

    assert len(result.references) == 2
    assert result.references[0]["property"] == "bpmn:inMessageRef"
    assert result.references[0]["id"] == "fooInMessage"
    assert json_equal(result.references[0]["element"], expected_element)
    assert result.references[1]["property"] == "bpmn:outMessageRef"
    assert result.references[1]["id"] == "fooOutMessage"
    assert json_equal(result.references[1]["element"], expected_element)


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Association#associationDirection")
def test_021_association_direction() -> None:
    result = _from_fixture("association.part.bpmn", "bpmn:Association")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Association",
            "associationDirection": "None",
            "id": "association",
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Event#eventDefinitionRef")
def test_022_event_definition_ref() -> None:
    result = _from_fixture("event-definition-ref.bpmn")

    event_definition_ref = result.elements_by_id["StartEvent_1"].get("eventDefinitionRef")

    assert json_equal(
        event_definition_ref,
        [
            {
                "$type": "bpmn:TimerEventDefinition",
                "id": "TimerDefinition",
                "timeDate": {"$type": "bpmn:FormalExpression", "body": "date"},
            }
        ],
    )


# should import types > bpmndi


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Extensions")
def test_023_di_extensions() -> None:
    result = _from_fixture("di/bpmnDiagram-extension.part.bpmn", "bpmndi:BPMNDiagram")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmndi:BPMNDiagram",
            "id": "BPMNDiagram_1",
            "plane": {
                "$type": "bpmndi:BPMNPlane",
                "id": "BPMNPlane_1",
                "extension": {
                    "$type": "di:Extension",
                    "values": [{"$type": "vendor:baz", "baz": "BAZ"}],
                },
                "planeElement": [
                    {
                        "$type": "bpmndi:BPMNShape",
                        "id": "BPMNShape_1",
                        "extension": {
                            "$type": "di:Extension",
                            "values": [{"$type": "vendor:bar", "$body": "BAR"}],
                        },
                    },
                    {
                        "$type": "bpmndi:BPMNEdge",
                        "id": "BPMNEdge_1",
                        "extension": {"$type": "di:Extension"},
                    },
                ],
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "BPMNShape#bounds (non-ns-attributes)")
def test_024_shape_bounds_non_ns_attributes() -> None:
    result = _from_fixture("di/bpmnShape.part.bpmn", "bpmndi:BPMNShape")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmndi:BPMNShape",
            "id": "BPMNShape_1",
            "isExpanded": True,
            "bounds": {
                "$type": "dc:Bounds",
                "height": 300.0,
                "width": 300.0,
                "x": 300.0,
                "y": 80.0,
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "BPMNShape#isMarkerVisible")
def test_025_shape_is_marker_visible() -> None:
    result = _from_fixture("di/bpmnShape-isMarkerVisible.part.bpmn", "bpmndi:BPMNShape")

    assert json_equal(
        result.root_element,
        {"$type": "bpmndi:BPMNShape", "id": "BPMNShape_1", "isMarkerVisible": False},
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "BPMNEdge#waypoint")
def test_026_edge_waypoint() -> None:
    result = _from_fixture("di/bpmnEdge-waypoint.part.bpmn", "bpmndi:BPMNEdge")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmndi:BPMNEdge",
            "id": "sid-2365FF07-4092-4B79-976A-AD192FE4E4E9_gui",
            "waypoint": [
                {"$type": "dc:Point", "x": 4905.0, "y": 1545.0},
                {"$type": "dc:Point", "x": 4950.0, "y": 1545.0},
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "Participant#participantMultiplicity")
def test_027_participant_multiplicity() -> None:
    result = _from_fixture("participantMultiplicity.part.bpmn", "bpmn:Participant")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Participant",
            "participantMultiplicity": {
                "$type": "bpmn:ParticipantMultiplicity",
                "id": "sid-a4e85590-bd67-418d-a617-53bcfcfde620",
                "maximum": 2,
                "minimum": 2,
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "BPMNEdge#waypoint (explicit xsi:type)")
def test_028_edge_waypoint_explicit_xsi_type() -> None:
    result = _from_fixture("di/bpmnEdge.part.bpmn", "bpmndi:BPMNEdge")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmndi:BPMNEdge",
            "id": "BPMNEdge_1",
            "waypoint": [
                {"$type": "dc:Point", "x": 388.0, "y": 260.0},
                {"$type": "dc:Point", "x": 420.0, "y": 260.0},
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "BPMNDiagram (nested elements)")
def test_029_diagram_nested_elements() -> None:
    result = _from_fixture("di/bpmnDiagram.part.bpmn", "bpmndi:BPMNDiagram")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmndi:BPMNDiagram",
            "id": "BPMNDiagram_1",
            "plane": {
                "$type": "bpmndi:BPMNPlane",
                "id": "BPMNPlane_1",
                "planeElement": [
                    {
                        "$type": "bpmndi:BPMNShape",
                        "id": "BPMNShape_1",
                        "isExpanded": True,
                        "bounds": {
                            "$type": "dc:Bounds",
                            "height": 300.0,
                            "width": 300.0,
                            "x": 300.0,
                            "y": 80.0,
                        },
                    },
                    {
                        "$type": "bpmndi:BPMNEdge",
                        "id": "BPMNEdge_1",
                        "waypoint": [
                            {"$type": "dc:Point", "x": 388.0, "y": 260.0},
                            {"$type": "dc:Point", "x": 420.0, "y": 260.0},
                        ],
                    },
                ],
            },
        },
    )


# should import references


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "via attributes")
def test_030_references_via_attributes() -> None:
    moddle = _moddle()
    xml = (
        '<bpmn:sequenceFlow xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'sourceRef="FOO_BAR" />'
    )

    result = moddle.from_xml(xml, "bpmn:SequenceFlow")

    assert len(result.references) == 1
    assert result.references[0]["property"] == "bpmn:sourceRef"
    assert result.references[0]["id"] == "FOO_BAR"
    assert json_equal(result.references[0]["element"], {"$type": "bpmn:SequenceFlow"})


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "via elements")
def test_031_references_via_elements() -> None:
    moddle = _moddle()
    xml = (
        '<bpmn:serviceTask xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        "<bpmn:outgoing>OUT_1</bpmn:outgoing>"
        "<bpmn:outgoing>OUT_2</bpmn:outgoing>"
        "</bpmn:serviceTask>"
    )

    result = moddle.from_xml(xml, "bpmn:ServiceTask")

    expected_element: dict[str, Any] = {"$type": "bpmn:ServiceTask"}

    assert len(result.references) == 2
    assert result.references[0]["property"] == "bpmn:outgoing"
    assert result.references[0]["id"] == "OUT_1"
    assert json_equal(result.references[0]["element"], expected_element)
    assert result.references[1]["property"] == "bpmn:outgoing"
    assert result.references[1]["id"] == "OUT_2"
    assert json_equal(result.references[1]["element"], expected_element)


# should import extensions


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "attributes on root")
def test_032_extension_attributes_on_root() -> None:
    moddle = _moddle()
    xml = (
        '<bpmn:sequenceFlow xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:foo="http://foobar" foo:bar="BAR" />'
    )

    result = moddle.from_xml(xml, "bpmn:SequenceFlow")

    assert result.root_element.attrs_.get("foo:bar") == "BAR"


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "elements via bpmn:extensionElements")
def test_033_elements_via_extension_elements() -> None:
    result = _from_fixture("extension-elements.bpmn")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Definitions",
            "id": "test",
            "targetNamespace": "http://bpmn.io/schema/bpmn",
            "extensionElements": {
                "$type": "bpmn:ExtensionElements",
                "values": [
                    {"$type": "vendor:info", "key": "bgcolor", "value": "#ffffff"},
                    {"$type": "vendor:info", "key": "role", "value": "[]"},
                ],
            },
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "generic xml extensions")
def test_034_generic_xml_extensions() -> None:
    moddle = _moddle()
    xml = """
  <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
  <bpmn:definitions
      xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
      xmlns:i18n="http://www.omg.org/spec/BPMN/non-normative/extensions/i18n/1.0"
      id="Definitions_1">
    <bpmn:collaboration id="Collaboration_1">
      <bpmn:extensionElements>
        <i18n:translation target="@name" xml:lang="en">Advertise</i18n:translation>
      </bpmn:extensionElements>
    </bpmn:collaboration>
  </bpmn:definitions>"""

    result = moddle.from_xml(xml)

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Definitions",
            "id": "Definitions_1",
            "rootElements": [
                {
                    "$type": "bpmn:Collaboration",
                    "id": "Collaboration_1",
                    "extensionElements": {
                        "$type": "bpmn:ExtensionElements",
                        "values": [
                            {
                                "$type": "i18n:translation",
                                "target": "@name",
                                "xml:lang": "en",
                                "$body": "Advertise",
                            }
                        ],
                    },
                }
            ],
        },
    )


# should read xml documents


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "empty definitions")
def test_035_empty_definitions() -> None:
    result = _from_fixture("empty-definitions.bpmn")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Definitions",
            "id": "empty-definitions",
            "targetNamespace": "http://bpmn.io/schema/bpmn",
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "empty definitions (default ns)")
def test_036_empty_definitions_default_ns() -> None:
    result = _from_fixture("empty-definitions-default-ns.bpmn")

    assert json_equal(
        result.root_element,
        {
            "$type": "bpmn:Definitions",
            "id": "empty-definitions",
            "targetNamespace": "http://bpmn.io/schema/bpmn",
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "simple process")
def test_037_simple_process() -> None:
    result = _from_fixture("simple.bpmn")

    assert result.root_element.get("id") == "simple"


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "simple process (default ns)")
def test_038_simple_process_default_ns() -> None:
    result = _from_fixture("simple-default-ns.bpmn")

    assert result.root_element.get("id") == "simple"


# should handle errors


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "when importing non-xml text")
def test_039_error_non_xml_text() -> None:
    xml = (FIXTURES / "error" / "no-xml.txt").read_text(encoding="utf-8")

    with pytest.raises(ParseError, match="unparsable content"):
        _moddle().from_xml(xml)


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "when importing non-bpmn xml")
def test_040_error_non_bpmn_xml() -> None:
    xml = (FIXTURES / "error" / "not-bpmn.bpmn").read_text(encoding="utf-8")

    with pytest.raises(
        ParseError, match=re.escape("failed to parse document as <bpmn:Definitions>")
    ) as exc_info:
        _moddle().from_xml(xml)

    warnings = exc_info.value.warnings

    assert len(warnings) == 1
    assert re.search(r"unparsable content <definitions> detected", warnings[0].message)


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "when importing binary")
def test_041_error_binary() -> None:
    xml = (FIXTURES / "error" / "binary.png").read_text(encoding="utf-8", errors="replace")

    with pytest.raises(ParseError, match="unparsable content"):
        _moddle().from_xml(xml)


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/read.js", "when importing bpmn:Extension (missing definition)"
)
def test_042_error_missing_extension_definition() -> None:
    result = _from_fixture("error/extension-definition-missing.bpmn")

    assert len(result.warnings) == 1
    assert result.warnings[0].message == "unresolved reference <ino:tInnovator>"


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "when importing invalid bpmn")
def test_043_error_invalid_bpmn() -> None:
    result = _from_fixture("error/undeclared-ns-child.bpmn")

    assert len(result.warnings) == 1


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/read.js", "when importing invalid categoryValue / reference"
)
def test_044_error_invalid_category_value() -> None:
    result = _from_fixture("error/categoryValue.bpmn")

    assert len(result.warnings) == 2

    assert result.warnings[0].message == (
        "unparsable content <categoryValue> detected\n"
        "\tline: 2\n"
        "\tcolumn: 2\n"
        "\tnested error: unrecognized element <bpmn:categoryValue>"
    )
    assert result.warnings[1].message == (
        "unresolved reference <sid-afd7e63e-916e-4bd0-a9f0-98cbff749193>"
    )


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/read.js", "when importing valid bpmn / unrecognized element"
)
def test_045_error_unrecognized_element() -> None:
    result = _from_fixture("error/unrecognized-child.bpmn")

    assert len(result.warnings) == 1


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "when importing duplicate ids")
def test_046_error_duplicate_ids() -> None:
    result = _from_fixture("error/duplicate-ids.bpmn")

    assert len(result.warnings) == 1
    assert "duplicate ID <test>" in result.warnings[0].message


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "when importing non UTF-8 files")
def test_047_error_bad_encoding() -> None:
    result = _from_fixture("error/bad-encoding.bpmn")

    assert len(result.warnings) == 1
    assert re.search(r"unsupported document encoding <windows-1252>", result.warnings[0].message)


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/read.js", "when importing broken diagram / xmlns redeclaration"
)
def test_048_error_xmlns_redeclaration() -> None:
    result = _from_fixture("error/xmlns-redeclaration.bpmn")

    assert len(result.warnings) == 2
    assert re.search(r"attribute <xmlns> already defined", result.warnings[0].message)
    assert re.search(r"attribute <id> already defined", result.warnings[1].message)

    assert result.root_element.attrs_.get("xmlns") == "http://www.omg.org/spec/BPMN/20100524/MODEL"
    assert result.root_element.get("id") == "a10"


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/read.js", "when importing invalid attributes")
def test_049_error_invalid_attributes() -> None:
    result = _from_fixture("error/invalid-attributes.bpmn")

    assert len(result.warnings) == 2
    assert re.search(r"illegal first char attribute name", result.warnings[0].message)
    assert re.search(r"missing attribute value", result.warnings[1].message)

    assert json_equal(
        result.elements_by_id["Process_1"],
        {"$type": "bpmn:Process", "id": "Process_1"},
    )


# should read attributes (upstream repeats the errors-case title in another
# describe; claimed once above per the claim-once convention)


def test_050_attrs_odd_namespaces() -> None:
    result = _from_fixture("attrs.bpmn")

    assert len(result.warnings) == 1
    assert re.search(r"illegal first char attribute name", result.warnings[0].message)

    assert json_equal(
        result.root_element.attrs_,
        {
            "xmlns:bpmn2": "http://www.omg.org/spec/BPMN/20100524/MODEL",
            "xmlns:color_1.0": "http://colors",
            "xmlns:.color": "http://colors",
        },
    )
    assert json_equal(result.root_element, {"$type": "bpmn:Definitions"})
