"""Ported saxen stream cases (Lot 3).

Claims every ``saxen/test/stream.js`` title. The ledger lists
``should be independent of chunk boundaries`` twice (namespaced attributes and
proxy mode); it is claimed once, covering both chunkings. ``collect`` mirrors
the upstream helper (text decoded, attrs raw, ``end()`` error preferred).

N-A: ``test/perf/`` (``decode.cjs``, ``parse.cjs`` and friends) is a benchmark
harness with no mocha ``it`` cases, so port coverage expects no claim for it.
"""

from __future__ import annotations

import re

import pytest

from bpmn_io.saxen import ParseError, Parser


def collect(
    chunks: list[str], options: dict[str, object] | None = None
) -> tuple[list[list[object]], object]:
    """Write ``chunks`` through a streaming parser; return (events, error)."""
    parser = Parser()
    if options is not None and options.get("ns") is not None:
        ns_map = options["ns"]
        assert isinstance(ns_map, dict)
        parser.ns(ns_map)
    events: list[list[object]] = []
    errors: list[object] = []
    parser.on(
        "openTag",
        lambda name, get_attrs, _decode: events.append(["openTag", name, get_attrs()]),
    )
    parser.on("closeTag", lambda name: events.append(["closeTag", name]))
    parser.on("text", lambda value, decode: events.append(["text", decode(value)]))
    parser.on("cdata", lambda value: events.append(["cdata", value]))
    parser.on("comment", lambda value: events.append(["comment", value]))
    parser.on("question", lambda value: events.append(["question", value]))
    parser.on("attention", lambda value: events.append(["attention", value]))
    parser.on("error", lambda err, _ctx: errors.append(err))
    for chunk in chunks:
        parser.write(chunk)
    end_error = parser.end()
    return events, end_error if end_error is not None else (errors[0] if errors else None)


def collect_proxy(
    chunks: list[str], options: dict[str, object] | None = None
) -> tuple[list[list[object]], object]:
    """Write ``chunks`` through a proxy-mode parser; the live view is cloned."""
    parser = Parser({"proxy": True})
    if options is not None and options.get("ns") is not None:
        ns_map = options["ns"]
        assert isinstance(ns_map, dict)
        parser.ns(ns_map)
    events: list[list[object]] = []
    errors: list[object] = []

    def _on_open(el: object, _decode: object, self_closing: object) -> None:
        events.append(
            [
                "openTag",
                el.name,  # type: ignore[union-attr]
                el.originalName,  # type: ignore[union-attr]
                dict(el.attrs),  # type: ignore[union-attr]
                dict(el.ns),  # type: ignore[union-attr]
                self_closing,
            ]
        )

    parser.on("openTag", _on_open)
    parser.on("closeTag", lambda el: events.append(["closeTag", el.name]))  # type: ignore[union-attr]
    parser.on(
        "text",
        lambda value, decode: events.append(
            ["text", decode(value)]  # type: ignore[operator]
        ),
    )
    parser.on("error", lambda err, _ctx: errors.append(err))
    for chunk in chunks:
        parser.write(chunk)
    end_error = parser.end()
    return events, end_error if end_error is not None else (errors[0] if errors else None)


@pytest.mark.upstream("saxen/test/stream.js", "should return the parser from #write")
def test_write_returns_parser() -> None:
    parser = Parser()
    assert parser.write("<root") is parser
    assert parser.write("/>") is parser


@pytest.mark.upstream("saxen/test/stream.js", "should throw on invalid arg")
def test_write_invalid_arg() -> None:
    parser = Parser()
    with pytest.raises(TypeError, match=re.escape("required args <xml=string>")):
        parser.write({})  # type: ignore[arg-type]


@pytest.mark.upstream("saxen/test/stream.js", "should parse XML written as a single chunk")
def test_single_chunk() -> None:
    events, error = collect(["<root>text</root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["text", "text"],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should parse XML written character by character")
def test_char_by_char() -> None:
    xml = '<root a="1">hi <child/> there</root>'
    events, error = collect(list(xml))
    assert error is None
    assert events == [
        ["openTag", "root", {"a": "1"}],
        ["text", "hi "],
        ["openTag", "child", {}],
        ["closeTag", "child"],
        ["text", " there"],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split an open tag")
def test_split_open_tag() -> None:
    events, error = collect(["<ro", "ot", " a", '="1"', ">", "</root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {"a": "1"}],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split an attribute value")
def test_split_attribute_value() -> None:
    events, error = collect(['<root a="va', 'lue"/>'])
    assert error is None
    assert events == [
        ["openTag", "root", {"a": "value"}],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split a self-closing tag")
def test_split_self_closing_tag() -> None:
    events, error = collect(["<root", "/", ">"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split a closing tag")
def test_split_closing_tag() -> None:
    events, error = collect(["<root><", "/", "root", ">"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should buffer text until the next tag")
def test_buffer_text_until_next_tag() -> None:
    events, error = collect(["<root>hel", "lo wor", "ld</root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["text", "hello world"],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream(
    "saxen/test/stream.js", "should not emit text twice on a following incomplete tag"
)
def test_no_double_text_on_incomplete_tag() -> None:
    events, error = collect(["<root>text<chi", "ld/></root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["text", "text"],
        ["openTag", "child", {}],
        ["closeTag", "child"],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split an entity in text")
def test_split_entity_in_text() -> None:
    events, error = collect(["<root>a &am", "p; b</root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["text", "a & b"],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split a CDATA section")
def test_split_cdata_section() -> None:
    events, error = collect(["<root><![CD", "ATA[a <b> c]", "]></root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["cdata", "a <b> c"],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", 'should split a CDATA section right after "<"')
def test_split_cdata_right_after_open_bracket() -> None:
    events, error = collect(["<root>", "<", "!", "[CDATA[a > b]]>", "</root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["cdata", "a > b"],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split a comment")
def test_split_comment() -> None:
    events, error = collect(["<root><!-- a ", "-- b -->x</root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["comment", " a -- b "],
        ["text", "x"],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", 'should split a comment right after "<"')
def test_split_comment_right_after_open_bracket() -> None:
    events, error = collect(["<root>", "<", "!", "-- some comment -->", "</root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["comment", " some comment "],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream(
    "saxen/test/stream.js", 'should split a comment containing ">" right after "<"'
)
def test_split_comment_with_bracket_right_after_open_bracket() -> None:
    events, error = collect(["<root>", "<", "!-- a > b -->", "</root>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["comment", " a > b "],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split a processing instruction")
def test_split_processing_instruction() -> None:
    events, error = collect(["<?xml vers", 'ion="1.0"?><root/>'])
    assert error is None
    assert events == [
        ["question", '<?xml version="1.0"?>'],
        ["openTag", "root", {}],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream(
    "saxen/test/stream.js", 'should split a processing instruction right after "<"'
)
def test_split_processing_instruction_right_after_open_bracket() -> None:
    events, error = collect(["<", "?", 'xml version="1.0"?>', "<root/>"])
    assert error is None
    assert events == [
        ["question", '<?xml version="1.0"?>'],
        ["openTag", "root", {}],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split an attention tag")
def test_split_attention_tag() -> None:
    events, error = collect(["<!DOCT", "YPE root><root/>"])
    assert error is None
    assert events == [
        ["attention", "<!DOCTYPE root>"],
        ["openTag", "root", {}],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", 'should split an attention tag right after "<"')
def test_split_attention_tag_right_after_open_bracket() -> None:
    events, error = collect(["<", "!", "DOCTYPE root>", "<root/>"])
    assert error is None
    assert events == [
        ["attention", "<!DOCTYPE root>"],
        ["openTag", "root", {}],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split leading whitespace before the root")
def test_split_leading_whitespace() -> None:
    events, error = collect(["  ", "\n  ", "<root/>"])
    assert error is None
    assert events == [
        ["openTag", "root", {}],
        ["closeTag", "root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should split namespace declarations")
def test_split_namespace_declarations() -> None:
    events, error = collect(
        ['<foo:root xmlns:foo="http://', 'foo" foo:a="A"/>'],
        {"ns": {"http://foo": "foo"}},
    )
    assert error is None
    assert events == [
        ["openTag", "foo:root", {"xmlns:foo": "http://foo", "foo:a": "A"}],
        ["closeTag", "foo:root"],
    ]


@pytest.mark.upstream(
    "saxen/test/stream.js", "should produce the same result regardless of chunking"
)
def test_same_result_regardless_of_chunking() -> None:
    xml = (
        '<root xmlns:x="urn:x">'
        '<x:child a="1">hi &amp; bye</x:child>'
        "<![CDATA[ raw <data> ]]>"
        "<!-- comment -->"
        "</root>"
    )
    options: dict[str, object] = {"ns": {"urn:x": "x"}}
    whole_events, whole_error = collect([xml], options)
    char_events, char_error = collect(list(xml), options)
    assert whole_error is None
    assert char_error is None
    assert char_events == whole_events


@pytest.mark.upstream("saxen/test/stream.js", "should report unclosed tag on #end")
def test_unclosed_tag_on_end() -> None:
    parser = Parser()
    errors: list[object] = []
    parser.on("error", lambda err, _ctx: errors.append(err))
    parser.write("<root")
    assert errors == []
    returned = parser.end()
    assert isinstance(returned, ParseError)
    assert str(returned) == "unclosed tag"
    assert errors == [returned]


@pytest.mark.upstream(
    "saxen/test/stream.js", "should report unexpected end of file for an open root"
)
def test_unexpected_end_of_file() -> None:
    _events, error = collect(["<root>", "<child/>"])
    assert isinstance(error, ParseError)
    assert str(error) == "unexpected end of file"


@pytest.mark.upstream("saxen/test/stream.js", "should report missing start tag for empty input")
def test_missing_start_tag_for_empty_input() -> None:
    _events, error = collect(["   "])
    assert isinstance(error, ParseError)
    assert str(error) == "missing start tag"


@pytest.mark.upstream("saxen/test/stream.js", "should reset state between streams")
def test_reset_state_between_streams() -> None:
    parser = Parser()
    open_tags: list[object] = []
    parser.on("openTag", open_tags.append)
    parser.write("<a/>").end()
    parser.write("<b/>").end()
    assert open_tags == ["a", "b"]


@pytest.mark.upstream("saxen/test/stream.js", "should throw on #parse while streaming")
def test_parse_while_streaming() -> None:
    parser = Parser()
    parser.write("<root>")
    with pytest.raises(RuntimeError, match=re.escape("parse during stream")):
        parser.parse("<other/>")


@pytest.mark.upstream(
    "saxen/test/stream.js", "should parse namespaced attributes split across chunks"
)
def test_namespaced_attributes_split_across_chunks() -> None:
    chunks = [
        '<root xmlns="http://foo" xmlns:b',
        'ar="http://bar" bar:aa="A"',
        ' id="1">hi</root>',
    ]
    options: dict[str, object] = {
        "ns": {"http://foo": "foo", "http://bar": "bar"},
    }
    events, error = collect(chunks, options)
    assert error is None
    assert events == [
        [
            "openTag",
            "foo:root",
            {
                "xmlns": "http://foo",
                "xmlns:bar": "http://bar",
                "bar:aa": "A",
                "id": "1",
            },
        ],
        ["text", "hi"],
        ["closeTag", "foo:root"],
    ]


@pytest.mark.upstream("saxen/test/stream.js", "should be independent of chunk boundaries")
def test_independent_of_chunk_boundaries() -> None:
    # first occurrence (namespaces + attributes): whole vs per-char streaming
    xml = '<root xmlns="http://foo" xmlns:bar="http://bar" bar:aa="A" id="1">hi</root>'
    options: dict[str, object] = {
        "ns": {"http://foo": "foo", "http://bar": "bar"},
    }
    whole_events, whole_error = collect([xml], options)
    char_events, char_error = collect(list(xml), options)
    assert whole_error is None
    assert char_error is None
    assert char_events == whole_events

    # second occurrence (proxy mode): whole vs per-char streaming
    proxy_xml = '<root xmlns="http://foo" foo="&quot;" id="1">hi</root>'
    proxy_options: dict[str, object] = {"ns": {"http://foo": "foo"}}
    proxy_whole_events, proxy_whole_error = collect_proxy([proxy_xml], proxy_options)
    proxy_char_events, proxy_char_error = collect_proxy(list(proxy_xml), proxy_options)
    assert proxy_whole_error is None
    assert proxy_char_error is None
    assert proxy_char_events == proxy_whole_events


@pytest.mark.upstream("saxen/test/stream.js", "should expose element view for streamed chunks")
def test_proxy_element_view_for_streamed_chunks() -> None:
    chunks = [
        '<root xmlns="http://foo" fo',
        'o="&quot;" id="1" ',
        "/>",
    ]
    events, error = collect_proxy(chunks, {"ns": {"http://foo": "foo"}})
    assert error is None
    assert events == [
        [
            "openTag",
            "foo:root",
            "root",
            {"xmlns": "http://foo", "foo": "&quot;", "id": "1"},
            {
                "foo": "foo",
                "foo$uri": "http://foo",
                "xmlns": "foo",
                "xmlns$uri": "http://foo",
            },
            True,
        ],
        ["closeTag", "foo:root"],
    ]
