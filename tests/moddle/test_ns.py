"""Ported moddle ns cases (Lot 4).

Transcribes every ``moddle/test/spec/ns.js`` ``it()`` title: one test per unique
ledger title (4 claims). Verification mirrors the upstream assertions:
``jsonEqual`` becomes field-wise ``==`` on the parsed namespace, ``throw()``
becomes ``pytest.raises``.
"""

from __future__ import annotations

import pytest

from bpmn_io.moddle import parse_name_ns


@pytest.mark.upstream("moddle/test/spec/ns.js", "should parse namespaced name")
def test_001_parse_namespaced_name() -> None:
    parsed = parse_name_ns("asdf:bar")

    assert parsed.name == "asdf:bar"
    assert parsed.prefix == "asdf"
    assert parsed.local_name == "bar"


@pytest.mark.upstream("moddle/test/spec/ns.js", "should parse localName (with default ns)")
def test_002_parse_local_name_with_default_ns() -> None:
    parsed = parse_name_ns("bar", "asdf")

    assert parsed.name == "asdf:bar"
    assert parsed.prefix == "asdf"
    assert parsed.local_name == "bar"


@pytest.mark.upstream("moddle/test/spec/ns.js", "should parse non-ns name")
def test_003_parse_non_ns_name() -> None:
    parsed = parse_name_ns("bar")

    assert parsed.name == "bar"
    assert parsed.prefix is None
    assert parsed.local_name == "bar"


@pytest.mark.upstream("moddle/test/spec/ns.js", "should handle invalid input")
def test_004_handle_invalid_input() -> None:
    with pytest.raises(ValueError, match="prefix:localName"):
        parse_name_ns("asdf:foo:bar")
