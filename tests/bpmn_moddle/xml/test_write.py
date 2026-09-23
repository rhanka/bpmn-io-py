"""Ported bpmn-moddle write cases (Lot 7).

Transcribes every ``bpmn-moddle/test/spec/xml/write.js`` ``it()`` title: one
test per claim (35 claims). Verification mirrors the upstream assertions as
``to_xml`` string equality (preamble skipped, as the upstream helper).
Only the public ``bpmn_io`` API is used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bpmn_io import create_moddle

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle
    from bpmn_io.moddle.base import ModdleElement


def _moddle() -> BpmnModdle:
    """Create the default six-package BPMN model, as the upstream helper."""
    return create_moddle()


def _write(
    moddle: BpmnModdle,
    element: ModdleElement,
    *,
    formatted: bool = False,
) -> str:
    """Serialize ``element`` without the XML preamble, as the upstream helper."""
    return moddle.to_xml(element, {"preamble": False, "format": formatted}).xml


# should export types > bpmn


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "Definitions (empty)")
def test_001_definitions_empty() -> None:
    moddle = _moddle()
    definitions = moddle.create("bpmn:Definitions")

    expected_xml = '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" />'

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "Definitions (participant + interface)")
def test_002_definitions_participant_interface() -> None:
    moddle = _moddle()
    interface_element = moddle.create("bpmn:Interface", {"id": "Interface_1"})
    participant_element = moddle.create(
        "bpmn:Participant", {"id": "Process_1", "interfaceRef": [interface_element]}
    )
    collaboration_element = moddle.create(
        "bpmn:Collaboration", {"participants": [participant_element]}
    )
    definitions = moddle.create(
        "bpmn:Definitions",
        {
            "targetNamespace": "http://bpmn.io/bpmn",
            "rootElements": [interface_element, collaboration_element],
        },
    )

    expected_xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'targetNamespace="http://bpmn.io/bpmn">'
        '<bpmn:interface id="Interface_1" />'
        "<bpmn:collaboration>"
        '<bpmn:participant id="Process_1">'
        "<bpmn:interfaceRef>Interface_1</bpmn:interfaceRef>"
        "</bpmn:participant>"
        "</bpmn:collaboration>"
        "</bpmn:definitions>"
    )

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "ScriptTask#script")
def test_003_script_task_script() -> None:
    moddle = _moddle()
    script_task = moddle.create(
        "bpmn:ScriptTask",
        {
            "id": "ScriptTask_1",
            "scriptFormat": "JavaScript",
            "script": 'context.set("FOO", "&nbsp;");',
        },
    )

    expected_xml = (
        '<bpmn:scriptTask xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="ScriptTask_1" scriptFormat="JavaScript">'
        '<bpmn:script>context.set("FOO", "&amp;nbsp;");</bpmn:script>'
        "</bpmn:scriptTask>"
    )

    assert _write(moddle, script_task) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "Task with null property")
def test_004_task_null_property() -> None:
    moddle = _moddle()
    task = moddle.create("bpmn:Task", {"id": "Task_1", "default": None})

    expected_xml = (
        '<bpmn:task xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Task_1" />'
    )

    assert _write(moddle, task) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "SequenceFlow#conditionExpression")
def test_005_sequence_flow_condition_expression() -> None:
    moddle = _moddle()
    sequence_flow = moddle.create("bpmn:SequenceFlow", {"id": "SequenceFlow_1"})
    sequence_flow.set(
        "conditionExpression",
        moddle.create("bpmn:FormalExpression", {"body": "${ foo < bar }"}),
    )

    expected_xml = (
        '<bpmn:sequenceFlow xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'id="SequenceFlow_1">\n'
        '  <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">'
        "${ foo &lt; bar }</bpmn:conditionExpression>\n"
        "</bpmn:sequenceFlow>\n"
    )

    assert _write(moddle, sequence_flow, formatted=True) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "MultiInstanceLoopCharacteristics")
def test_006_multi_instance_loop_characteristics() -> None:
    moddle = _moddle()
    loop_characteristics = moddle.create(
        "bpmn:MultiInstanceLoopCharacteristics",
        {
            "loopCardinality": moddle.create("bpmn:FormalExpression", {"body": "${ foo < bar }"}),
            "loopDataInputRef": moddle.create("bpmn:Property", {"id": "loopDataInputRef"}),
            "loopDataOutputRef": moddle.create("bpmn:Property", {"id": "loopDataOutputRef"}),
            "inputDataItem": moddle.create("bpmn:DataInput", {"id": "inputDataItem"}),
            "outputDataItem": moddle.create("bpmn:DataOutput", {"id": "outputDataItem"}),
            "complexBehaviorDefinition": [
                moddle.create("bpmn:ComplexBehaviorDefinition", {"id": "complexBehaviorDefinition"})
            ],
            "completionCondition": moddle.create("bpmn:FormalExpression", {"body": "${ done }"}),
            "isSequential": True,
            "behavior": "One",
            "oneBehaviorEventRef": moddle.create(
                "bpmn:CancelEventDefinition", {"id": "oneBehaviorEventRef"}
            ),
            "noneBehaviorEventRef": moddle.create(
                "bpmn:MessageEventDefinition", {"id": "noneBehaviorEventRef"}
            ),
        },
    )

    expected_xml = (
        "<bpmn:multiInstanceLoopCharacteristics "
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'isSequential="true" '
        'behavior="One" '
        'oneBehaviorEventRef="oneBehaviorEventRef" '
        'noneBehaviorEventRef="noneBehaviorEventRef">'
        '<bpmn:loopCardinality xsi:type="bpmn:tFormalExpression">'
        "${ foo &lt; bar }</bpmn:loopCardinality>"
        "<bpmn:loopDataInputRef>loopDataInputRef</bpmn:loopDataInputRef>"
        "<bpmn:loopDataOutputRef>loopDataOutputRef</bpmn:loopDataOutputRef>"
        '<bpmn:inputDataItem id="inputDataItem" />'
        '<bpmn:outputDataItem id="outputDataItem" />'
        '<bpmn:complexBehaviorDefinition id="complexBehaviorDefinition" />'
        '<bpmn:completionCondition xsi:type="bpmn:tFormalExpression">'
        "${ done }</bpmn:completionCondition>"
        "</bpmn:multiInstanceLoopCharacteristics>"
    )

    assert _write(moddle, loop_characteristics) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "LinkEventDefinition")
def test_007_link_event_definition() -> None:
    moddle = _moddle()
    definition = moddle.create("bpmn:LinkEventDefinition", {"name": ""})

    expected_xml = (
        "<bpmn:linkEventDefinition "
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" name="" />'
    )

    assert _write(moddle, definition) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "StandardLoopCharacteristics")
def test_008_standard_loop_characteristics() -> None:
    moddle = _moddle()
    loop_characteristics = moddle.create(
        "bpmn:StandardLoopCharacteristics",
        {
            "testBefore": True,
            "loopMaximum": 100,
            "loopCondition": moddle.create("bpmn:FormalExpression", {"body": "${ foo < bar }"}),
        },
    )

    expected_xml = (
        "<bpmn:standardLoopCharacteristics "
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'testBefore="true" '
        'loopMaximum="100">'
        '<bpmn:loopCondition xsi:type="bpmn:tFormalExpression">'
        "${ foo &lt; bar }</bpmn:loopCondition>"
        "</bpmn:standardLoopCharacteristics>"
    )

    assert _write(moddle, loop_characteristics) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "Process")
def test_009_process() -> None:
    moddle = _moddle()
    process_element = moddle.create(
        "bpmn:Process",
        {
            "id": "Process_1",
            "flowElements": [moddle.create("bpmn:Task", {"id": "Task_1"})],
            "properties": [moddle.create("bpmn:Property", {"name": "foo"})],
            "laneSets": [moddle.create("bpmn:LaneSet", {"id": "LaneSet_1"})],
            "monitoring": moddle.create("bpmn:Monitoring"),
            "artifacts": [
                moddle.create(
                    "bpmn:TextAnnotation",
                    {"id": "TextAnnotation_1", "text": "FOOBAR"},
                )
            ],
            "resources": [moddle.create("bpmn:PotentialOwner", {"name": "Walter"})],
        },
    )

    expected_xml = (
        '<bpmn:process xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="Process_1">'
        "<bpmn:monitoring />"
        '<bpmn:property name="foo" />'
        '<bpmn:laneSet id="LaneSet_1" />'
        '<bpmn:task id="Task_1" />'
        '<bpmn:textAnnotation id="TextAnnotation_1">'
        "<bpmn:text>FOOBAR</bpmn:text>"
        "</bpmn:textAnnotation>"
        '<bpmn:potentialOwner name="Walter" />'
        "</bpmn:process>"
    )

    assert _write(moddle, process_element) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "Activity")
def test_010_activity() -> None:
    moddle = _moddle()
    activity = moddle.create(
        "bpmn:Activity",
        {
            "id": "Activity_1",
            "properties": [
                moddle.create("bpmn:Property", {"name": "FOO"}),
                moddle.create("bpmn:Property", {"name": "BAR"}),
            ],
            "resources": [moddle.create("bpmn:HumanPerformer", {"name": "Walter"})],
            "dataInputAssociations": [
                moddle.create("bpmn:DataInputAssociation", {"id": "Input_1"})
            ],
            "dataOutputAssociations": [
                moddle.create("bpmn:DataOutputAssociation", {"id": "Output_1"})
            ],
            "ioSpecification": moddle.create("bpmn:InputOutputSpecification"),
        },
    )

    expected_xml = (
        '<bpmn:activity xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="Activity_1">'
        "<bpmn:ioSpecification />"
        '<bpmn:property name="FOO" />'
        '<bpmn:property name="BAR" />'
        '<bpmn:dataInputAssociation id="Input_1" />'
        '<bpmn:dataOutputAssociation id="Output_1" />'
        '<bpmn:humanPerformer name="Walter" />'
        "</bpmn:activity>"
    )

    assert _write(moddle, activity) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "BaseElement#documentation")
def test_011_base_element_documentation() -> None:
    moddle = _moddle()
    definitions = moddle.create("bpmn:Definitions", {"id": "Definitions_1"})

    docs = definitions.get("documentation")
    assert isinstance(docs, list)
    docs.append(moddle.create("bpmn:Documentation", {"textFormat": "xyz", "text": "FOO\nBAR"}))
    docs.append(moddle.create("bpmn:Documentation", {"text": "<some /><html></html>"}))

    expected_xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="Definitions_1">'
        '<bpmn:documentation textFormat="xyz">FOO\nBAR</bpmn:documentation>'
        "<bpmn:documentation>&lt;some /&gt;&lt;html&gt;&lt;/html&gt;</bpmn:documentation>"
        "</bpmn:definitions>"
    )

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "CallableElement#ioSpecification")
def test_012_callable_element_io_specification() -> None:
    moddle = _moddle()
    callable_element = moddle.create(
        "bpmn:CallableElement",
        {
            "id": "Callable_1",
            "ioSpecification": moddle.create("bpmn:InputOutputSpecification"),
        },
    )

    expected_xml = (
        "<bpmn:callableElement "
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Callable_1">'
        "<bpmn:ioSpecification />"
        "</bpmn:callableElement>"
    )

    assert _write(moddle, callable_element) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "ResourceRole#resourceRef")
def test_013_resource_role_resource_ref() -> None:
    moddle = _moddle()
    role = moddle.create(
        "bpmn:ResourceRole",
        {
            "id": "Callable_1",
            "resourceRef": moddle.create("bpmn:Resource", {"id": "REF"}),
        },
    )

    expected_xml = (
        '<bpmn:resourceRole xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="Callable_1">'
        "<bpmn:resourceRef>REF</bpmn:resourceRef>"
        "</bpmn:resourceRole>"
    )

    assert _write(moddle, role) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "ResourceAssignmentExpression")
def test_014_resource_assignment_expression() -> None:
    moddle = _moddle()
    expression = moddle.create("bpmn:FormalExpression", {"body": "${ foo < bar }"})
    assignment = moddle.create(
        "bpmn:ResourceAssignmentExpression", {"id": "FOO BAR", "expression": expression}
    )

    expected_xml = (
        "<bpmn:resourceAssignmentExpression "
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'id="FOO BAR">'
        '<bpmn:expression xsi:type="bpmn:tFormalExpression">'
        "${ foo &lt; bar }"
        "</bpmn:expression>"
        "</bpmn:resourceAssignmentExpression>"
    )

    assert _write(moddle, assignment) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "CallActivity#calledElement")
def test_015_call_activity_called_element() -> None:
    moddle = _moddle()
    call_activity = moddle.create(
        "bpmn:CallActivity", {"id": "CallActivity_1", "calledElement": "otherProcess"}
    )

    expected_xml = (
        "<bpmn:callActivity "
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="CallActivity_1" calledElement="otherProcess" />'
    )

    assert _write(moddle, call_activity) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "ItemDefinition#structureRef")
def test_016_item_definition_structure_ref() -> None:
    moddle = _moddle()
    item_definition = moddle.create(
        "bpmn:ItemDefinition",
        {"id": "serviceInput", "structureRef": "service:CelsiusToFahrenheitSoapIn"},
    )

    expected_xml = (
        '<bpmn:itemDefinition xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="serviceInput" '
        'structureRef="service:CelsiusToFahrenheitSoapIn" />'
    )

    assert _write(moddle, item_definition) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "ItemDefinition#structureRef with ns")
def test_017_item_definition_structure_ref_ns() -> None:
    moddle = _moddle()
    item_definition = moddle.create(
        "bpmn:ItemDefinition",
        {
            "xmlns:xs": "http://xml-types",
            "id": "xsdBool",
            "isCollection": True,
            "itemKind": "Information",
            "structureRef": "xs:tBool",
        },
    )

    expected_xml = (
        '<bpmn:itemDefinition xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:xs="http://xml-types" '
        'id="xsdBool" '
        'itemKind="Information" '
        'structureRef="xs:tBool" '
        'isCollection="true" />'
    )

    assert _write(moddle, item_definition) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "Operation#implementationRef")
def test_018_operation_implementation_ref() -> None:
    moddle = _moddle()
    operation = moddle.create(
        "bpmn:Operation", {"id": "operation", "implementationRef": "foo:operation"}
    )

    expected_xml = (
        '<bpmn:operation xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="operation" '
        'implementationRef="foo:operation" />'
    )

    assert _write(moddle, operation) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "Interface#implementationRef")
def test_019_interface_implementation_ref() -> None:
    moddle = _moddle()
    iface = moddle.create(
        "bpmn:Interface", {"id": "interface", "implementationRef": "foo:interface"}
    )

    expected_xml = (
        '<bpmn:interface xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="interface" '
        'implementationRef="foo:interface" />'
    )

    assert _write(moddle, iface) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "Collaboration")
def test_020_collaboration() -> None:
    moddle = _moddle()
    participant = moddle.create("bpmn:Participant", {"id": "Participant_1"})
    text_annotation = moddle.create("bpmn:TextAnnotation", {"id": "TextAnnotation_1"})
    collaboration = moddle.create(
        "bpmn:Collaboration",
        {
            "id": "Collaboration_1",
            "participants": [participant],
            "artifacts": [text_annotation],
        },
    )

    expected_xml = (
        '<bpmn:collaboration xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="Collaboration_1">'
        '<bpmn:participant id="Participant_1" />'
        '<bpmn:textAnnotation id="TextAnnotation_1" />'
        "</bpmn:collaboration>"
    )

    assert _write(moddle, collaboration) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "ExtensionElements")
def test_021_extension_elements() -> None:
    moddle = _moddle()
    extension_elements = moddle.create("bpmn:ExtensionElements")
    foo = moddle.create_any("vendor:foo", "http://vendor", {"key": "FOO", "value": "BAR"})
    values = extension_elements.get("values")
    assert isinstance(values, list)
    values.append(foo)
    definitions = moddle.create("bpmn:Definitions", {"extensionElements": extension_elements})

    expected_xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:vendor="http://vendor">'
        "<bpmn:extensionElements>"
        '<vendor:foo key="FOO" value="BAR" />'
        "</bpmn:extensionElements>"
        "</bpmn:definitions>"
    )

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "Operation#messageRef")
def test_022_operation_message_ref() -> None:
    moddle = _moddle()
    in_message = moddle.create("bpmn:Message", {"id": "fooInMessage"})
    out_message = moddle.create("bpmn:Message", {"id": "fooOutMessage"})
    operation = moddle.create(
        "bpmn:Operation",
        {"id": "operation", "inMessageRef": in_message, "outMessageRef": out_message},
    )

    expected_xml = (
        '<bpmn:operation xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="operation">'
        "<bpmn:inMessageRef>fooInMessage</bpmn:inMessageRef>"
        "<bpmn:outMessageRef>fooOutMessage</bpmn:outMessageRef>"
        "</bpmn:operation>"
    )

    assert _write(moddle, operation) == expected_xml


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/write.js", "AdHocSubProcess#cancelRemainingInstances"
)
def test_023_adhoc_cancel_remaining() -> None:
    moddle = _moddle()
    operation = moddle.create("bpmn:AdHocSubProcess", {"cancelRemainingInstances": False})

    expected_xml = (
        "<bpmn:adHocSubProcess "
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'cancelRemainingInstances="false" />'
    )

    assert _write(moddle, operation) == expected_xml


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/write.js",
    "AdHocSubProcess#cancelRemainingInstances (default value not exported)",
)
def test_024_adhoc_cancel_remaining_default() -> None:
    moddle = _moddle()
    operation = moddle.create("bpmn:AdHocSubProcess", {"cancelRemainingInstances": True})

    expected_xml = (
        '<bpmn:adHocSubProcess xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" />'
    )

    assert _write(moddle, operation) == expected_xml


# should export types > bpmndi


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "BPMNDiagram")
def test_025_bpmn_diagram() -> None:
    moddle = _moddle()
    diagram = moddle.create("bpmndi:BPMNDiagram", {"name": "FOO", "resolution": 96.5})

    expected_xml = (
        '<bpmndi:BPMNDiagram xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'name="FOO" '
        'resolution="96.5" />'
    )

    assert _write(moddle, diagram) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "BPMNShape")
def test_026_bpmn_shape() -> None:
    moddle = _moddle()
    bpmn_shape = moddle.create(
        "bpmndi:BPMNShape",
        {
            "bounds": moddle.create(
                "dc:Bounds", {"x": 100.0, "y": 200.0, "width": 50.0, "height": 50.0}
            )
        },
    )

    expected_xml = (
        '<bpmndi:BPMNShape xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC">'
        '<dc:Bounds x="100" y="200" width="50" height="50" />'
        "</bpmndi:BPMNShape>"
    )

    assert _write(moddle, bpmn_shape) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "BPMNShape (colored)")
def test_027_bpmn_shape_colored() -> None:
    moddle = _moddle()
    bpmn_shape = moddle.create("bpmndi:BPMNShape", {"fill": "#ff0000", "stroke": "#00ff00"})

    expected_xml = (
        '<bpmndi:BPMNShape xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:bioc="http://bpmn.io/schema/bpmn/biocolor/1.0" '
        'bioc:stroke="#00ff00" bioc:fill="#ff0000" />'
    )

    assert _write(moddle, bpmn_shape) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "BPMNEdge (colored)")
def test_028_bpmn_edge_colored() -> None:
    moddle = _moddle()
    bpmn_edge = moddle.create("bpmndi:BPMNEdge", {"fill": "#ff0000", "stroke": "#00ff00"})

    expected_xml = (
        '<bpmndi:BPMNEdge xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:bioc="http://bpmn.io/schema/bpmn/biocolor/1.0" '
        'bioc:stroke="#00ff00" bioc:fill="#ff0000" />'
    )

    assert _write(moddle, bpmn_edge) == expected_xml


# should export extensions


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "manually added custom namespace")
def test_029_manual_custom_namespace() -> None:
    moddle = _moddle()
    definitions = moddle.create("bpmn:Definitions")
    definitions.set("xmlns:foo", "http://foobar")

    expected_xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:foo="http://foobar" />'
    )

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "attributes on root")
def test_030_attributes_on_root() -> None:
    moddle = _moddle()
    definitions = moddle.create("bpmn:Definitions")
    definitions.set("xmlns:foo", "http://foobar")
    definitions.set("foo:bar", "BAR")

    expected_xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:foo="http://foobar" foo:bar="BAR" />'
    )

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "attributes on nested element")
def test_031_attributes_on_nested_element() -> None:
    moddle = _moddle()
    signal = moddle.create("bpmn:Signal", {"foo:bar": "BAR"})
    definitions = moddle.create(
        "bpmn:Definitions", {"rootElements": [signal], "xmlns:foo": "http://foobar"}
    )

    expected_xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:foo="http://foobar">'
        '<bpmn:signal foo:bar="BAR" />'
        "</bpmn:definitions>"
    )

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/write.js", "attributes and namespace on nested element"
)
def test_032_attributes_namespace_nested() -> None:
    moddle = _moddle()
    signal = moddle.create("bpmn:Signal", {"xmlns:foo": "http://foobar", "foo:bar": "BAR"})
    definitions = moddle.create("bpmn:Definitions", {"rootElements": [signal]})

    expected_xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        '<bpmn:signal xmlns:foo="http://foobar" foo:bar="BAR" />'
        "</bpmn:definitions>"
    )

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/write.js", "attributes and namespace on root + nested element"
)
def test_033_attributes_namespace_root_nested() -> None:
    moddle = _moddle()
    signal = moddle.create("bpmn:Signal", {"xmlns:foo": "http://foobar", "foo:bar": "BAR"})
    definitions = moddle.create(
        "bpmn:Definitions", {"xmlns:foo": "http://foobar", "rootElements": [signal]}
    )

    expected_xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:foo="http://foobar">'
        '<bpmn:signal foo:bar="BAR" />'
        "</bpmn:definitions>"
    )

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/write.js", "elements via bpmn:extensionElements")
def test_034_elements_via_extension_elements() -> None:
    moddle = _moddle()
    vendor_bg_color = moddle.create_any(
        "vendor:info", "http://vendor", {"key": "bgcolor", "value": "#ffffff"}
    )
    vendor_role = moddle.create_any("vendor:info", "http://vendor", {"key": "role", "value": "[]"})
    extension_elements = moddle.create(
        "bpmn:ExtensionElements", {"values": [vendor_bg_color, vendor_role]}
    )
    definitions = moddle.create("bpmn:Definitions", {"extensionElements": extension_elements})

    expected_xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:vendor="http://vendor">'
        "<bpmn:extensionElements>"
        '<vendor:info key="bgcolor" value="#ffffff" />'
        '<vendor:info key="role" value="[]" />'
        "</bpmn:extensionElements>"
        "</bpmn:definitions>"
    )

    assert _write(moddle, definitions) == expected_xml


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/write.js", "nested elements via bpmn:extensionElements"
)
def test_035_nested_elements_via_extension_elements() -> None:
    moddle = _moddle()
    camunda_ns = "http://camunda.org/schema/1.0/bpmn"
    input_parameter = moddle.create_any(
        "camunda:inputParameter",
        camunda_ns,
        {"name": "assigneeEntity", "$body": "user"},
    )
    input_output = moddle.create_any(
        "camunda:inputOutput", camunda_ns, {"$children": [input_parameter]}
    )
    extension_elements = moddle.create("bpmn:ExtensionElements", {"values": [input_output]})
    user_task = moddle.create("bpmn:UserTask", {"extensionElements": extension_elements})

    expected_xml = (
        '<bpmn:userTask xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:camunda="' + camunda_ns + '">'
        "<bpmn:extensionElements>"
        "<camunda:inputOutput>"
        '<camunda:inputParameter name="assigneeEntity">user</camunda:inputParameter>'
        "</camunda:inputOutput>"
        "</bpmn:extensionElements>"
        "</bpmn:userTask>"
    )

    assert _write(moddle, user_task) == expected_xml
