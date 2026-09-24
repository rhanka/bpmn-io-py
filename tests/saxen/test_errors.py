"""Ported saxen error cases (Lot 3).

Claims every ``saxen/test/errors.js`` title. The ledger lists
``should throw on invalid args`` twice (``#on`` and ``#ns`` describes); it is
claimed once, covering both invalid-arg paths. Programmer errors raise the
port's ``TypeError``/``ValueError`` with the upstream messages; parse-time
failures travel through ``onError`` (default: raise ``ParseError``) and are
returned by ``parse``/``end``.
"""

from __future__ import annotations

import re

import pytest

from bpmn_io.saxen import ParseError, Parser


@pytest.mark.upstream("saxen/test/errors.js", "should NOT pass to #onError")
def test_handler_exception_not_routed_to_on_error() -> None:
    parser = Parser()
    seen: list[object] = []
    parser.on("error", lambda err, _ctx: seen.append(err))

    def _boom(_el: object) -> None:
        msg = "foo"
        raise ValueError(msg)

    parser.on("openTag", _boom)
    with pytest.raises(ValueError, match=re.escape("foo")):
        parser.parse("<xml />")
    assert seen == []


@pytest.mark.upstream("saxen/test/errors.js", "should throw on invalid arg")
def test_parse_invalid_arg() -> None:
    parser = Parser()
    with pytest.raises(TypeError, match=re.escape("required args <xml=string>")):
        parser.parse({})  # type: ignore[arg-type]


@pytest.mark.upstream("saxen/test/errors.js", "should throw on XML parse error")
def test_parse_error_default_routing() -> None:
    parser = Parser()
    with pytest.raises(ParseError, match=re.escape("unclosed tag")):
        parser.parse("<not<quite<xml")

    hooked: list[object] = []
    parser.on("error", lambda err, _ctx: hooked.append(err))
    returned = parser.parse("<not<quite<xml")
    assert isinstance(returned, ParseError)
    assert str(returned) == "unclosed tag"
    assert hooked == [returned]


@pytest.mark.upstream("saxen/test/errors.js", "should not throw without hooks")
def test_no_throw_without_hooks() -> None:
    lines = [
        "<? question ?>",
        "<!ATTENTION>",
        "<!-- COMMENT -->",
        "<tag a=\"1'>",
        "hi",
        "<![CDATA[cdata]]>",
        "</tag>",
    ]
    doc = "\n".join(lines)
    assert Parser().parse(doc) is None

    # same document with hooks: warnings are routed, nothing is thrown
    # (attributes parse lazily, so an openTag hook must force them)
    parser = Parser()
    warnings: list[object] = []
    parser.on("warn", lambda err, _ctx: warnings.append(err))
    parser.on("openTag", lambda _name, get_attrs: get_attrs())
    assert parser.parse(doc) is None
    assert [str(warning) for warning in warnings] == ["attribute value quote missmatch"]


@pytest.mark.upstream("saxen/test/errors.js", "should throw on invalid args")
def test_invalid_args() -> None:
    # first occurrence (#on): missing callback
    with pytest.raises(TypeError, match=re.escape("required args <name, cb>")):
        Parser().on("openTag", None)  # type: ignore[arg-type]
    # second occurrence (#ns): non-object namespace map
    with pytest.raises(TypeError, match=re.escape("required args <nsMap={}>")):
        Parser().ns("bar")  # type: ignore[arg-type]


@pytest.mark.upstream("saxen/test/errors.js", "should throw on invalid event")
def test_invalid_event() -> None:
    with pytest.raises(ValueError, match=re.escape("unsupported event: foo")):
        Parser().on("foo", lambda: None)


@pytest.mark.upstream("saxen/test/errors.js", "should NOT throw on no args")
def test_ns_no_args() -> None:
    parser = Parser()
    assert parser.ns() is parser
