"""Ported bpmn-moddle roundtrip cases (Lot 7).

Transcribes every ``bpmn-moddle/test/spec/xml/roundtrip.js`` ``it()`` title:
one test per claim (43 claims, including the two same-file ``event
definitions`` vendor occurrences, yaoqiang vs bizagi). Each case parses a
fixture (pre-validating the input, as the upstream ``fromValidFile`` helper),
serializes it back and validates the output with ``validate(xml)`` through
``lxml`` against the OMG XSDs vendored with the fixtures (see
``docs/xsd-divergences.md``). Only the public ``bpmn_io`` API is used.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from lxml import etree

from bpmn_io import create_moddle

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle
    from bpmn_io.moddle.base import AnyModdleElement, ModdleElement
    from bpmn_io.moddle_xml import ParseResult

FIXTURES = (
    Path(__file__).resolve().parent.parent.parent
    / "upstream"
    / "bpmn-moddle"
    / "test"
    / "fixtures"
    / "bpmn"
)
XSD_FIXTURES = (
    Path(__file__).resolve().parent.parent.parent
    / "upstream"
    / "bpmn-moddle"
    / "test"
    / "fixtures"
    / "xsd"
)
OMG_XSD = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "tests"
    / "oracle"
    / "node_modules"
    / "bpmn-moddle"
    / "resources"
    / "bpmn"
    / "xsd"
)


@cache
def _schema() -> etree.XMLSchema:
    """Compile the vendored ``BPMN20.xsd`` with absolute OMG ``schemaLocation``.

    The fixture XSD dangles (``../../../resources/bpmn/xsd/`` does not exist
    next to the fixtures); the locations are rewritten to the OMG XSDs shipped
    inside the vendored ``bpmn-moddle`` npm package, so no network is needed.
    """
    text = (XSD_FIXTURES / "BPMN20.xsd").read_text(encoding="utf-8")
    fixed = text.replace(
        "../../../resources/bpmn/xsd/BPMNDI.xsd",
        (OMG_XSD / "BPMNDI.xsd").resolve().as_uri(),
    )
    fixed = fixed.replace(
        "../../../resources/bpmn/xsd/Semantic.xsd",
        (OMG_XSD / "Semantic.xsd").resolve().as_uri(),
    )
    fixed = fixed.replace("Vendor.xsd", (XSD_FIXTURES / "Vendor.xsd").resolve().as_uri())
    document = etree.fromstring(fixed.encode("utf-8"))
    return etree.XMLSchema(document)


def _validate(xml: str) -> None:
    """Assert ``xml`` validates against ``BPMN20.xsd`` (the ``validate`` port)."""
    assert xml, "XML is not defined"
    document = etree.fromstring(xml.encode("utf-8"))
    schema = _schema()
    assert schema.validate(document), str(schema.error_log)


def _moddle() -> BpmnModdle:
    """Create the default six-package BPMN model, as the upstream helper."""
    return create_moddle()


def _from_valid_fixture(
    name: str,
    root: str = "bpmn:Definitions",
    *,
    moddle: BpmnModdle | None = None,
) -> ParseResult:
    """Validate a fixture input and parse it, as ``fromValidFile`` does."""
    model = moddle if moddle is not None else _moddle()
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    _validate(xml)
    return model.from_xml(xml, root)


def _serialize(element: ModdleElement | AnyModdleElement) -> str:
    """Serialize ``element`` formatted, as the upstream ``toXML`` helper."""
    return _moddle().to_xml(element, {"format": True}).xml


def _roundtrip(name: str, root: str = "bpmn:Definitions") -> str:
    """Validate a fixture, parse it and return the validated serialization."""
    result = _from_valid_fixture(name, root)
    xml = _serialize(result.root_element)
    _validate(xml)
    return xml


# should serialize valid BPMN 2.0 xml after read


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "home-made bpmn model")
def test_001_home_made_model() -> None:
    moddle = _moddle()
    definitions = moddle.create("bpmn:Definitions", {"targetNamespace": "http://foo"})
    process_element = moddle.create("bpmn:Process")
    service_task = moddle.create("bpmn:ServiceTask", {"name": "MyService Task"})

    flow_elements = process_element.get("flowElements")
    assert isinstance(flow_elements, list)
    flow_elements.append(service_task)
    root_elements = definitions.get("rootElements")
    assert isinstance(root_elements, list)
    root_elements.append(process_element)

    xml = moddle.to_xml(definitions, {"format": True}).xml

    _validate(xml)


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "obscure ids model")
def test_002_obscure_ids_model() -> None:
    moddle = _moddle()
    definitions = moddle.create(
        "bpmn:Definitions",
        {
            "xmlns:foo": "http://foo-ns",
            "targetNamespace": "http://foo",
            "rootElements": [
                moddle.create("bpmn:Message", {"id": "foo_bar"}),
                moddle.create("bpmn:Message", {"id": "foo-bar"}),
                moddle.create("bpmn:Message", {"id": "foo1bar"}),
                moddle.create("bpmn:Message", {"id": "Foo1bar"}),
                moddle.create("bpmn:Message", {"id": "_foo_bar"}),
                moddle.create("bpmn:Message", {"id": "_foo-bar"}),
                moddle.create("bpmn:Message", {"id": "_11"}),
            ],
        },
    )

    xml = moddle.to_xml(definitions, {"format": True}).xml

    _validate(xml)


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "ioSpecification")
def test_003_io_specification() -> None:
    moddle = _moddle()
    definitions = moddle.create("bpmn:Definitions", {"targetNamespace": "http://foo"})
    process_element = moddle.create("bpmn:Process")
    data_input = moddle.create("bpmn:DataInput", {"id": "DataInput_FOO"})
    input_set = moddle.create("bpmn:InputSet", {"dataInputRefs": [data_input]})
    output_set = moddle.create("bpmn:OutputSet")
    io_specification = moddle.create(
        "bpmn:InputOutputSpecification",
        {
            "inputSets": [input_set],
            "outputSets": [output_set],
            "dataInputs": [data_input],
        },
    )
    service_task = moddle.create(
        "bpmn:ServiceTask", {"name": "MyService Task", "ioSpecification": io_specification}
    )

    flow_elements = process_element.get("flowElements")
    assert isinstance(flow_elements, list)
    flow_elements.append(service_task)
    root_elements = definitions.get("rootElements")
    assert isinstance(root_elements, list)
    root_elements.append(process_element)

    xml = moddle.to_xml(definitions, {"format": True}).xml

    _validate(xml)


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "properties")
def test_004_properties() -> None:
    moddle = _moddle()
    definitions = moddle.create("bpmn:Definitions", {"targetNamespace": "http://foo"})
    process_element = moddle.create("bpmn:Process")
    prop = moddle.create("bpmn:Property", {"id": "Property_112", "name": "__targetRef_placeholder"})
    service_task = moddle.create(
        "bpmn:ServiceTask", {"name": "MyService Task", "properties": [prop]}
    )

    flow_elements = process_element.get("flowElements")
    assert isinstance(flow_elements, list)
    flow_elements.append(service_task)
    root_elements = definitions.get("rootElements")
    assert isinstance(root_elements, list)
    root_elements.append(process_element)

    xml = moddle.to_xml(definitions, {"format": True}).xml

    _validate(xml)


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "extension attributes")
def test_005_extension_attributes() -> None:
    _roundtrip("extension-attributes.bpmn")


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/roundtrip.js", "extension attributes on expression"
)
def test_006_extension_attributes_on_expression() -> None:
    result = _from_valid_fixture(
        "expression-extension.part.bpmn", "bpmn:ResourceAssignmentExpression"
    )

    xml = _serialize(result.root_element)

    assert (
        '<bpmn:expression id="ID_0hnlswl" myNs:expressionType="Constant">fgdfgdfg</bpmn:expression>'
    ) in xml

    _validate(xml)


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/roundtrip.js", "multi instance loop characteristics"
)
def test_007_multi_instance_loop_characteristics() -> None:
    _roundtrip("multiInstanceLoopCharacteristics.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "Expression without xsi:type")
def test_008_expression_without_xsi_type() -> None:
    xml = _roundtrip("expression-plain.bpmn")

    assert 'xsi:type="bpmn:tExpression' not in xml


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/roundtrip.js", "documentation / extensionElements order"
)
def test_009_documentation_extension_elements_order() -> None:
    _roundtrip("documentation-extension-elements.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "activity children order")
def test_010_activity_children_order() -> None:
    _roundtrip("activity-children.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "lane children order")
def test_011_lane_children_order() -> None:
    _roundtrip("lane-children.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "conversation children order")
def test_012_conversation_children_order() -> None:
    _roundtrip("conversation-children.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "process children order")
def test_013_process_children_order() -> None:
    _roundtrip("process-children.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "definitions children order")
def test_014_definitions_children_order() -> None:
    _roundtrip("definitions-children.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "ioSpecification children order")
def test_015_io_specification_children_order() -> None:
    _roundtrip("inputOutputSpecification-children.bpmn")


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/roundtrip.js", "dataInputAssociation assignment order"
)
def test_016_data_input_association_assignment_order() -> None:
    _roundtrip("data-input-association.assignment.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "LinkEventDefinition#target")
def test_017_link_event_definition_target() -> None:
    _roundtrip("link-event-definition-target.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "Participant#interfaceRef")
def test_018_participant_interface_ref() -> None:
    _roundtrip("participant-interfaceRef.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "ResourceRole#resourceRef")
def test_019_resource_role_resource_ref() -> None:
    _roundtrip("potentialOwner.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "Operation#messageRef")
def test_020_operation_message_ref() -> None:
    xml = _roundtrip("operation-messageRef.bpmn")

    assert "<bpmn:inMessageRef>fooInMessage</bpmn:inMessageRef>" in xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "di extensions")
def test_021_di_extensions() -> None:
    xml = _roundtrip("di-extension.bpmn")

    assert '<vendor:baz baz="BAZ" />' in xml
    assert "<vendor:bar>BAR</vendor:bar>" in xml
    assert "<di:extension />" in xml


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/roundtrip.js", "complex processElement / extensionElements"
)
def test_022_complex_process_element() -> None:
    _roundtrip("complex.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "category")
def test_023_category() -> None:
    xml = _roundtrip("category.bpmn")

    assert "sid-afd7e63e-916e-4bd0-a9f0-98cbff749193" in xml
    assert "group with label" in xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "choreography task")
def test_024_choreography_task() -> None:
    _roundtrip("choreography-task.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "simple processElement")
def test_025_simple_process_element() -> None:
    _roundtrip("simple.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "xsi:type")
def test_026_xsi_type() -> None:
    _roundtrip("xsi-type.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "ad-hoc subprocess")
def test_027_adhoc_subprocess() -> None:
    _roundtrip("ad-hoc.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "colors")
def test_028_colors() -> None:
    _roundtrip("example-colors.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "nested default namespace prefix")
def test_029_nested_default_namespace_prefix() -> None:
    xml = _roundtrip("nested-default-namespace-prefix.bpmn")

    assert '<Entry key="A" value="B" />' in xml


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/roundtrip.js", "nested elements no (default) namespace prefix"
)
def test_030_nested_no_namespace_prefix() -> None:
    xml = _roundtrip("nested-no-namespace-prefix.bpmn")

    assert '<Entry key="A" value="B" />' in xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "conflicting ns prefix")
def test_031_conflicting_ns_prefix() -> None:
    _roundtrip("namespace-prefix-collision.bpmn")


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/roundtrip.js", "local namespace declaration / re-definition"
)
def test_032_local_namespace_redefinition() -> None:
    xml = _roundtrip("redundant-ns-declaration.bpmn")

    assert 'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"' not in xml
    assert (
        '<BPMNDiagram xmlns="http://www.omg.org/spec/BPMN/20100524/DI" id="BPMNDiagram_1">' in xml
    )


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "local namespace exports")
def test_033_local_namespace_exports() -> None:
    expected_xml = (FIXTURES / "namespace-redefinition.bpmn").read_text(encoding="utf-8")

    result = _from_valid_fixture("namespace-redefinition.bpmn")

    assert _serialize(result.root_element) == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "xml:lang attribute")
def test_034_xml_lang_attribute() -> None:
    result = _from_valid_fixture("xml-lang.bpmn")

    assert result.warnings == [], [w.message for w in result.warnings]

    _validate(_serialize(result.root_element))


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "i18n")
def test_035_i18n() -> None:
    _roundtrip("i18n.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "BPMN in color properties")
def test_036_bpmn_in_color_properties() -> None:
    result = _from_valid_fixture("bpmn-in-color.bpmn")

    assert result.warnings == [], [w.message for w in result.warnings]

    _validate(_serialize(result.root_element))


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "event definition ref")
def test_037_event_definition_ref() -> None:
    _roundtrip("event-definition-ref.bpmn")


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/roundtrip.js", "operation ref on message event definition"
)
def test_038_operation_ref_message_event() -> None:
    expected_xml = (FIXTURES / "operation-ref-message-event-definition.bpmn").read_text(
        encoding="utf-8"
    )

    result = _from_valid_fixture("operation-ref-message-event-definition.bpmn")
    xml = _serialize(result.root_element)

    _validate(xml)
    assert xml == expected_xml


@pytest.mark.upstream(
    "bpmn-moddle/test/spec/xml/roundtrip.js",
    "operation ref as an attribute on tasks and io binding",
)
def test_039_operation_ref_as_attribute() -> None:
    expected_xml = (FIXTURES / "operation-ref-as-attribute.bpmn").read_text(encoding="utf-8")

    result = _from_valid_fixture("operation-ref-as-attribute.bpmn")
    xml = _serialize(result.root_element)

    _validate(xml)
    assert xml == expected_xml


# vendor


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "complex processElement")
def test_040_vendor_signavio_complex() -> None:
    _roundtrip("vendor/signavio-complex-no-extensions.bpmn")


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "event definitions")
def test_041_vendor_yaoqiang_event_definitions() -> None:
    result = _from_valid_fixture("vendor/yaoqiang-event-definitions.bpmn")

    assert result.warnings == [], [w.message for w in result.warnings]

    _validate(_serialize(result.root_element))


def test_042_vendor_bizagi_event_definitions() -> None:
    result = _from_valid_fixture("vendor/bizagi-nested-ns-definition.bpmn")

    assert result.warnings == [], [w.message for w in result.warnings]

    _validate(_serialize(result.root_element))


@pytest.mark.upstream("bpmn-moddle/test/spec/xml/roundtrip.js", "local namespace declaration")
def test_043_vendor_case_agile_local_ns() -> None:
    result = _from_valid_fixture("vendor/case-agile-local-ns-declaration.bpmn")

    assert result.warnings == [], [w.message for w in result.warnings]

    _validate(_serialize(result.root_element))
