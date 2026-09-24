"""Ported bpmn-moddle camunda integration cases (Lot 7).

Transcribes every ``bpmn-moddle/test/integration/camunda/{read,write,
roundtrip}.js`` ``it()`` title: one test per claim (5 read + 5 write + 1
roundtrip). The roundtrip case validates its output with ``validate(xml)``
through ``lxml`` against the OMG XSDs vendored with the fixtures (see
``docs/xsd-divergences.md``). Only the public ``bpmn_io`` API plus the
``tests._matchers`` helper is used.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from lxml import etree

from bpmn_io import create_moddle
from tests._matchers import json_equal

if TYPE_CHECKING:
    from bpmn_io.bpmn_moddle import BpmnModdle
    from bpmn_io.moddle.base import AnyModdleElement, ModdleElement

FIXTURES = (
    Path(__file__).resolve().parent.parent.parent / "upstream" / "bpmn-moddle" / "test" / "fixtures"
)
XSD_FIXTURES = FIXTURES / "xsd"
OMG_XSD = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "tests"
    / "upstream"
    / "bpmn-moddle"
    / "resources"
    / "bpmn"
    / "xsd"
)


def _moddle() -> BpmnModdle:
    """Create the model with the ``camunda`` extension package, as upstream."""
    descriptor: dict[str, Any] = json.loads(
        (FIXTURES / "json" / "model" / "camunda.json").read_text(encoding="utf-8")
    )
    return create_moddle({"camunda": descriptor})


def _read_fixture(name: str, root: str) -> ModdleElement | AnyModdleElement:
    """Parse a vendored camunda fixture, as the upstream ``fromFile`` helper."""
    xml = (FIXTURES / "bpmn" / name).read_text(encoding="utf-8")
    return _moddle().from_xml(xml, root).root_element


@cache
def _schema() -> etree.XMLSchema:
    """Compile the vendored ``BPMN20.xsd`` with absolute OMG ``schemaLocation``."""
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
    return etree.XMLSchema(etree.fromstring(fixed.encode("utf-8")))


def _validate(xml: str) -> None:
    """Assert ``xml`` validates against ``BPMN20.xsd`` (the ``validate`` port)."""
    assert xml, "XML is not defined"
    document = etree.fromstring(xml.encode("utf-8"))
    schema = _schema()
    assert schema.validate(document), str(schema.error_log)


# camunda extension > read > should recognize camunda types


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/read.js", "InputOutput - list")
def test_001_read_list() -> None:
    root_element = _read_fixture(
        "extension/camunda/inputOutput-list.part.bpmn", "camunda:InputOutput"
    )

    assert json_equal(
        root_element,
        {
            "$type": "camunda:InputOutput",
            "outputParameters": [
                {
                    "$type": "camunda:OutputParameter",
                    "name": "var1",
                    "definition": {
                        "$type": "camunda:List",
                        "items": [
                            {"$type": "camunda:Value", "value": "${1+1}"},
                            {"$type": "camunda:Value", "value": "${1+2}"},
                            {"$type": "camunda:Value", "value": "${1+3}"},
                        ],
                    },
                }
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/read.js", "InputOutput - map")
def test_002_read_map() -> None:
    root_element = _read_fixture(
        "extension/camunda/inputOutput-map.part.bpmn", "camunda:InputOutput"
    )

    assert json_equal(
        root_element,
        {
            "$type": "camunda:InputOutput",
            "inputParameters": [
                {
                    "$type": "camunda:InputParameter",
                    "name": "var1",
                    "definition": {
                        "$type": "camunda:Map",
                        "entries": [
                            {
                                "$type": "camunda:Entry",
                                "key": "a",
                                "value": {
                                    "$type": "camunda:List",
                                    "items": [
                                        {
                                            "$type": "camunda:Value",
                                            "value": "stringInListNestedInMap",
                                        },
                                        {
                                            "$type": "camunda:Value",
                                            "value": "${ 'b' }",
                                        },
                                    ],
                                },
                            }
                        ],
                    },
                }
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/read.js", "InputOutput - mixed")
def test_003_read_mixed() -> None:
    root_element = _read_fixture(
        "extension/camunda/inputOutput-mixed.part.bpmn", "camunda:InputOutput"
    )

    assert json_equal(
        root_element,
        {
            "$type": "camunda:InputOutput",
            "inputParameters": [
                {
                    "$type": "camunda:InputParameter",
                    "name": "var1",
                    "definition": {
                        "$type": "camunda:List",
                        "items": [
                            {
                                "$type": "camunda:Value",
                                "value": "constantStringValue",
                            },
                            {"$type": "camunda:Value", "value": "${ 'elValue' }"},
                            {
                                "$type": "camunda:Script",
                                "scriptFormat": "Groovy",
                                "source": 'return "scriptValue";',
                            },
                        ],
                    },
                }
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/read.js", "InputOutput - plain")
def test_004_read_plain() -> None:
    root_element = _read_fixture(
        "extension/camunda/inputOutput-plain.part.bpmn", "camunda:InputOutput"
    )

    assert json_equal(
        root_element,
        {
            "$type": "camunda:InputOutput",
            "inputParameters": [
                {
                    "$type": "camunda:InputParameter",
                    "name": "var2",
                    "value": "stringConstantValue",
                }
            ],
        },
    )


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/read.js", "InputOutput - script")
def test_005_read_script() -> None:
    root_element = _read_fixture(
        "extension/camunda/inputOutput-script.part.bpmn", "camunda:InputOutput"
    )

    assert json_equal(
        root_element,
        {
            "$type": "camunda:InputOutput",
            "outputParameters": [
                {
                    "$type": "camunda:OutputParameter",
                    "name": "var1",
                    "definition": {
                        "$type": "camunda:Script",
                        "scriptFormat": "Groovy",
                        "source": "return 1 + 1;",
                    },
                }
            ],
        },
    )


# camunda extension > write > should export camunda types


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/write.js", "ServiceTaskLike")
def test_006_write_service_task_like() -> None:
    moddle = _moddle()
    service_task = moddle.create("bpmn:ServiceTask", {"javaDelegate": "FOO"})

    assert service_task.instance_of("camunda:ServiceTaskLike") is True

    expected_xml = (
        '<bpmn:serviceTask xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:camunda="http://activiti.org/bpmn" '
        'camunda:javaDelegate="FOO" />'
    )

    assert moddle.to_xml(service_task, {"preamble": False}).xml == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/write.js", "InputOutput - list")
def test_007_write_list() -> None:
    moddle = _moddle()
    output_parameter = moddle.create(
        "camunda:OutputParameter",
        {
            "name": "var1",
            "definition": moddle.create(
                "camunda:List",
                {
                    "items": [
                        moddle.create("camunda:Value", {"value": "${1+1}"}),
                        moddle.create("camunda:Value", {"value": "${1+2}"}),
                        moddle.create("camunda:Value", {"value": "${1+3}"}),
                    ]
                },
            ),
        },
    )
    input_output = moddle.create("camunda:InputOutput", {"outputParameters": [output_parameter]})

    expected_xml = (
        '<camunda:inputOutput xmlns:camunda="http://activiti.org/bpmn">'
        '<camunda:outputParameter name="var1">'
        "<camunda:list>"
        "<camunda:value>${1+1}</camunda:value>"
        "<camunda:value>${1+2}</camunda:value>"
        "<camunda:value>${1+3}</camunda:value>"
        "</camunda:list>"
        "</camunda:outputParameter>"
        "</camunda:inputOutput>"
    )

    assert moddle.to_xml(input_output, {"preamble": False}).xml == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/write.js", "InputOutput - map")
def test_008_write_map() -> None:
    moddle = _moddle()
    input_parameter = moddle.create(
        "camunda:InputParameter",
        {
            "name": "var1",
            "definition": moddle.create(
                "camunda:Map",
                {
                    "entries": [
                        moddle.create(
                            "camunda:Entry",
                            {
                                "key": "a",
                                "value": moddle.create(
                                    "camunda:List",
                                    {
                                        "items": [
                                            moddle.create(
                                                "camunda:Value",
                                                {"value": "stringInListNestedInMap"},
                                            ),
                                            moddle.create(
                                                "camunda:Value",
                                                {"value": "${ 'b' }"},
                                            ),
                                        ]
                                    },
                                ),
                            },
                        )
                    ]
                },
            ),
        },
    )
    input_output = moddle.create("camunda:InputOutput", {"inputParameters": [input_parameter]})

    expected_xml = (
        '<camunda:inputOutput xmlns:camunda="http://activiti.org/bpmn">'
        '<camunda:inputParameter name="var1">'
        "<camunda:map>"
        '<camunda:entry key="a">'
        "<camunda:list>"
        "<camunda:value>stringInListNestedInMap</camunda:value>"
        "<camunda:value>${ 'b' }</camunda:value>"
        "</camunda:list>"
        "</camunda:entry>"
        "</camunda:map>"
        "</camunda:inputParameter>"
        "</camunda:inputOutput>"
    )

    assert moddle.to_xml(input_output, {"preamble": False}).xml == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/write.js", "InputOutput - mixed")
def test_009_write_mixed() -> None:
    moddle = _moddle()
    input_parameter = moddle.create(
        "camunda:InputParameter",
        {
            "name": "var1",
            "definition": moddle.create(
                "camunda:List",
                {
                    "items": [
                        moddle.create("camunda:Value", {"value": "constantStringValue"}),
                        moddle.create("camunda:Value", {"value": "${ 'elValue' }"}),
                        moddle.create("camunda:Script", {"source": 'return "scriptValue";'}),
                    ]
                },
            ),
        },
    )
    input_output = moddle.create("camunda:InputOutput", {"inputParameters": [input_parameter]})

    expected_xml = (
        '<camunda:inputOutput xmlns:camunda="http://activiti.org/bpmn">'
        '<camunda:inputParameter name="var1">'
        "<camunda:list>"
        "<camunda:value>constantStringValue</camunda:value>"
        "<camunda:value>${ 'elValue' }</camunda:value>"
        '<camunda:script>return "scriptValue";</camunda:script>'
        "</camunda:list>"
        "</camunda:inputParameter>"
        "</camunda:inputOutput>"
    )

    assert moddle.to_xml(input_output, {"preamble": False}).xml == expected_xml


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/write.js", "InputOutput - plain")
def test_010_write_plain() -> None:
    moddle = _moddle()
    input_parameter = moddle.create(
        "camunda:InputParameter",
        {"name": "var2", "value": "stringConstantValue"},
    )
    input_output = moddle.create("camunda:InputOutput", {"inputParameters": [input_parameter]})

    expected_xml = (
        '<camunda:inputOutput xmlns:camunda="http://activiti.org/bpmn">'
        "<camunda:inputParameter "
        'name="var2">stringConstantValue</camunda:inputParameter>'
        "</camunda:inputOutput>"
    )

    assert moddle.to_xml(input_output, {"preamble": False}).xml == expected_xml


# camunda extension > should serialize valid BPMN 2.0 after read


@pytest.mark.upstream("bpmn-moddle/test/integration/camunda/roundtrip.js", "inputOutput")
def test_011_roundtrip_input_output() -> None:
    xml = (FIXTURES / "bpmn" / "extension" / "camunda" / "inputOutput.bpmn").read_text(
        encoding="utf-8"
    )
    root_element = _moddle().from_xml(xml).root_element

    serialized = _moddle().to_xml(root_element, {"format": True}).xml

    _validate(serialized)
