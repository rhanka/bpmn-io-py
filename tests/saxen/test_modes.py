"""Ported saxen mode cases (Lot 3).

Claims every ``saxen/test/modes.js`` title. The only parser option upstream and
in the port is ``proxy`` (no ``attrMode``/``cdataMode`` exists on either side,
so there is nothing to parametrize beyond proxy on/off); the proxy element view
exposes lazy ``attrs``/``ns`` semantics cloned via ``dict(element)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bpmn_io.saxen import Parser

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.upstream("saxen/test/modes.js", "exposing additional details")
def test_proxy_additional_details() -> None:
    parser = Parser({"proxy": True})
    parser.ns({"http://ns": "ns"})
    counter = 0

    def _on_open(el: object, decode: Callable[[str], str], _tag_end: object, _ctx: object) -> None:
        nonlocal counter
        counter += 1
        assert el.name == "ns:root"  # type: ignore[union-attr]
        assert el.originalName == "root"  # type: ignore[union-attr]
        assert el.attrs == {"xmlns": "http://ns", "foo": "&quot;"}  # type: ignore[union-attr]
        assert el.ns == {  # type: ignore[union-attr]
            "ns": "ns",
            "ns$uri": "http://ns",
            "xmlns": "ns",
            "xmlns$uri": "http://ns",
        }
        assert decode(el.attrs["foo"]) == '"'  # type: ignore[union-attr]

    parser.on("openTag", _on_open)
    parser.parse('<root xmlns="http://ns" foo="&quot;" />')
    assert counter == 1


@pytest.mark.upstream("saxen/test/modes.js", "providing clonable properties")
def test_proxy_clonable_properties() -> None:
    parser = Parser({"proxy": True})
    parser.ns({"http://ns": "ns"})
    counter = 0

    def _on_open(el: object, _decode: object, _tag_end: object, _ctx: object) -> None:
        nonlocal counter
        counter += 1
        clone = dict(el)  # type: ignore[arg-type]
        assert clone["name"] == "ns:root"
        assert clone["originalName"] == "root"
        assert clone["attrs"] == {"xmlns": "http://ns", "foo": "&quot;"}
        assert clone["ns"] == {
            "ns": "ns",
            "ns$uri": "http://ns",
            "xmlns": "ns",
            "xmlns$uri": "http://ns",
        }

    parser.on("openTag", _on_open)
    parser.parse('<root xmlns="http://ns" foo="&quot;" />')
    assert counter == 1


@pytest.mark.upstream("saxen/test/modes.js", "exposing stable ns snapshots")
def test_proxy_stable_ns_snapshots() -> None:
    parser = Parser({"proxy": True})
    parser.ns({"urn:1": "one", "urn:2": "two"})
    captured: list[object] = []
    captured_again: list[object] = []

    def _on_open(el: object) -> None:
        if el.originalName == "a:x":  # type: ignore[union-attr]
            captured.append(el.ns)  # type: ignore[union-attr]
            captured_again.append(el.ns)  # type: ignore[union-attr]

    parser.on("openTag", _on_open)
    parser.parse('<root xmlns:a="urn:1"><a:x xmlns:b="urn:2"><b:y /></a:x></root>')
    assert len(captured) == 1
    assert captured[0] is captured_again[0]
    assert captured[0] == {
        "one": "one",
        "one$uri": "urn:1",
        "two": "two",
        "two$uri": "urn:2",
        "a": "one",
        "a$uri": "urn:1",
        "b": "two",
        "b$uri": "urn:2",
    }


@pytest.mark.upstream("saxen/test/modes.js", "should instantiate functional")
def test_instantiate_functional() -> None:
    # Python has no `new`: plain construction is the functional form upstream
    # tests via `Parser()` (which the `if (!this)` guard redirects).
    parser = Parser()
    assert isinstance(parser, Parser)
    assert isinstance(Parser({"proxy": True}), Parser)
