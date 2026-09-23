"""Ported saxen decode cases (Lot 3).

Claims the single ``saxen/test/decode.js`` title. Upstream drives the full entity
table through one namespaced ``openTag`` attribute; this port keeps that drive
(``decode`` arrives as the handler argument and must be ``decode_entities``) and
pins each table row — reserved names plus UPPERCASE variants, decimal and hex
references, unknown/mixed-case/malformed literals — through ``decode_entities``
directly, under the same claim.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bpmn_io import saxen
from bpmn_io.saxen import ParseError, Parser, decode_entities

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.upstream("saxen/test/decode.js", "should decode entities")
def test_decode_entities() -> None:
    assert {"Parser", "ParseError", "decode_entities"} <= set(saxen.__all__)
    assert saxen.Parser is Parser
    assert saxen.ParseError is ParseError
    assert saxen.decode_entities is decode_entities

    parser = Parser()
    parser.ns({})

    counter = 0

    def _on_open(
        _el: object,
        get_attrs: Callable[[], dict[str, str]],
        decode: Callable[[str], str],
        _tag_end: object,
        _ctx: object,
    ) -> None:
        nonlocal counter
        counter += 1
        assert decode is decode_entities
        assert decode(get_attrs()["encoded"]) == "&'><\"&Quot;\"'&{İ&raquo;&constructor;&#NaN;"

    parser.on("openTag", _on_open)

    special_chars = [
        "&amp;",
        "&apos;",
        "&gt;",
        "&lt;",
        "&quot;",
        "&Quot;",
        "&QUOT;",
        "&#39;",
        "&#38;",
        "&#0123;",
        "&#x0130;",
        "&raquo;",
        "&constructor;",
        "&#NaN;",
    ]
    parser.parse('<root xmlns="http://ns" encoded="' + "".join(special_chars) + '" />')
    assert counter == 1

    # same table, one row at a time
    assert decode_entities("&amp;") == "&"
    assert decode_entities("&apos;") == "'"
    assert decode_entities("&gt;") == ">"
    assert decode_entities("&lt;") == "<"
    assert decode_entities("&quot;") == '"'
    assert decode_entities("&AMP;&APOS;&GT;&LT;&QUOT;") == "&'><\""
    assert decode_entities("&#39;&#38;&#0123;") == "'&{"
    assert decode_entities("&#x0130;&#x22;") == 'İ"'
    # mixed-case reserved names stay literal, as upstream
    assert decode_entities("&Quot;") == "&Quot;"
    # unknown named references pass through unchanged
    assert decode_entities("&raquo;&constructor;&nbsp;") == "&raquo;&constructor;&nbsp;"
    # malformed references stay literal
    assert decode_entities("&#NaN;&#x;&;") == "&#NaN;&#x;&;"
    # numeric codes go through the fromCharCode modulo
    assert decode_entities("&#65;&#x41;") == "AA"
    assert decode_entities("&#0;") == "\x00"
    # short strings without an ampersand return unchanged
    assert decode_entities("") == ""
    assert decode_entities("ab") == "ab"
    assert decode_entities("a&b") == "a&b"
