"""Ported saxen element cases (Lot 3).

Transcribes every ``saxen/test/elements.js`` ``test()`` title: one test per unique
ledger title (139 claims in this file counting the deeply-nested namespace case
below; the 7 titles the ledger lists twice are claimed once, on first
occurrence — a differing second body is asserted in the same test, never with a
second marker). Verification mirrors ``test/helper.js``: events are recorded via
``on()``, open-tag attrs compare as a SUBSET, ``error``/``warn`` compare by
message, context dicts compare fully where the upstream row carries one, and
record counts must match. The ``ns`` rows use the helper default map.
"""

from __future__ import annotations

import pytest

from bpmn_io.saxen import Parser

NS_MAP = {
    "http://search.yahoo.com/mrss/": "media",
    "http://www.w3.org/1999/xhtml": "xhtml",
    "http://www.w3.org/2005/Atom": "atom",
    "http://purl.org/rss/1.0/": "rss",
}


def _verify(xml: str, expect: list[list[object]], *, ns: bool = False) -> None:
    """Parse ``xml`` and check the recorded events against ``expect``."""
    parser = Parser()
    if ns:
        parser.ns(dict(NS_MAP))
    recorded: list[tuple[object, ...]] = []
    parser.on("error", lambda err, ctx: recorded.append(("error", err, ctx())))
    parser.on("warn", lambda err, ctx: recorded.append(("warn", err, ctx())))
    parser.on(
        "openTag",
        lambda name, get_attrs, _decode, tag_end, ctx: recorded.append(
            ("openTag", name, get_attrs(), tag_end, ctx())
        ),
    )
    parser.on(
        "closeTag",
        lambda name, _decode, tag_start, ctx: recorded.append(("closeTag", name, tag_start, ctx())),
    )
    parser.on("text", lambda value, _decode, ctx: recorded.append(("text", value, ctx())))
    parser.on("cdata", lambda data, ctx: recorded.append(("cdata", data, ctx())))
    parser.on(
        "comment",
        lambda value, _decode, ctx: recorded.append(("comment", value, ctx())),
    )
    parser.on(
        "attention",
        lambda value, _decode, ctx: recorded.append(("attention", value, ctx())),
    )
    parser.on("question", lambda value, ctx: recorded.append(("question", value, ctx())))
    parser.parse(xml)
    assert len(recorded) == len(expect)
    for index, (actual, wanted) in enumerate(zip(recorded, expect, strict=True)):
        _verify_record(actual, index, wanted)


def _verify_record(actual: tuple[object, ...], index: int, wanted: list[object]) -> None:
    """Check one recorded event against one upstream row (helper.js semantics)."""
    name = actual[0]
    assert name == wanted[0], f"record {index}: event mismatch"
    for column, (seen, expected) in enumerate(zip(actual[1:], wanted[1:], strict=False), start=1):
        if name == "openTag" and column == 2:
            if expected is False:
                assert seen is False, f"record {index}: attrs mismatch"
            else:
                assert isinstance(seen, dict), f"record {index}: attrs mismatch"
                assert isinstance(expected, dict), f"record {index}: attrs mismatch"
                assert {key: seen[key] for key in expected} == expected, (
                    f"record {index}: attrs mismatch"
                )
            continue
        if name in ("error", "warn") and column == 1:
            assert isinstance(seen, Exception), f"record {index}: error mismatch"
            assert str(seen) == expected, f"record {index}: error mismatch"
            continue
        assert seen == expected, f"record {index} column {column}: mismatch"


@pytest.mark.upstream("saxen/test/elements.js", "<div/>")
def test_001_div() -> None:
    _verify(
        "<div/>",
        [["openTag", "div", {}, True], ["closeTag", "div", True]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<div />")
def test_002_div() -> None:
    _verify(
        "<div />",
        [["openTag", "div", {}, True], ["closeTag", "div", True]],
    )
    # same ledger title, second occurrence transcribes ' \ufeff<div />'
    _verify(
        " \ufeff<div />",
        [["openTag", "div"], ["closeTag", "div"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<div></div>")
def test_003_div_div() -> None:
    _verify(
        "<div></div>",
        [["openTag", "div", {}, False], ["closeTag", "div", False]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<DIV/>")
def test_004_div() -> None:
    _verify(
        "<DIV/>",
        [["openTag", "DIV", {}, True], ["closeTag", "DIV", True]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<dateTime.iso8601 />")
def test_005_datetime_iso8601() -> None:
    _verify(
        "<dateTime.iso8601 />",
        [["openTag", "dateTime.iso8601", {}, True], ["closeTag", "dateTime.iso8601", True]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<DIV />")
def test_006_div() -> None:
    _verify(
        "<DIV />",
        [["openTag", "DIV", {}, True], ["closeTag", "DIV", True]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<DIV></DIV>")
def test_007_div_div() -> None:
    _verify(
        "<DIV></DIV>",
        [["openTag", "DIV", {}, False], ["closeTag", "DIV", False]],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<DIV a="B"></DIV>')
def test_008_div_a_b_div() -> None:
    _verify(
        '<DIV\x0ca="B"></DIV>',
        [["openTag", "DIV"], ["closeTag", "DIV"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<div></div \x0f>")
def test_009_div_div() -> None:
    _verify(
        "<div></div \x0f>",
        [["openTag", "div"], ["error", "close tag"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "\x01asdasd")
def test_010_asdasd() -> None:
    _verify(
        "\n\x01asdasd",
        [["error", "missing start tag"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<!XXXXX zzzz="eeee">')
def test_011_xxxxx_zzzz_eeee() -> None:
    _verify(
        '<!XXXXX zzzz="eeee">',
        [
            [
                "attention",
                '<!XXXXX zzzz="eeee">',
                {"data": '<!XXXXX zzzz="eeee">', "line": 0, "column": 0},
            ]
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<!-- HELLO -->")
def test_012_hello() -> None:
    _verify(
        "<!-- HELLO -->",
        [["comment", " HELLO ", {"data": "<!-- HELLO -", "line": 0, "column": 0}]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<!-- HELLO")
def test_013_hello() -> None:
    _verify(
        "<!-- HELLO",
        [["error", "unclosed comment", {"data": "<!-- HELLO", "line": 0, "column": 0}]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "</a>")
def test_014_a() -> None:
    _verify(
        "</a>",
        [["error", "missing open tag"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<!- HELLO")
def test_015_hello() -> None:
    _verify(
        "<!- HELLO",
        [["error", "unclosed tag", {"line": 0, "column": 0, "data": "<!- HELLO"}]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<? QUESTION ?>")
def test_016_question() -> None:
    _verify(
        "<? QUESTION ?>",
        [["question", "<? QUESTION ?>", {"data": "<? QUESTION ?", "line": 0, "column": 0}]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<? QUESTION")
def test_017_question() -> None:
    _verify(
        "<? QUESTION",
        [["error", "unclosed question", {"data": "<? QUESTION", "line": 0, "column": 0}]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<a><b/></a>")
def test_018_a_b_a() -> None:
    _verify(
        "<a><b/></a>",
        [
            ["openTag", "a", {}, False],
            ["openTag", "b", {}, True],
            ["closeTag", "b", True],
            ["closeTag", "a", False],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<open")
def test_019_open() -> None:
    _verify(
        "<open",
        [["error", "unclosed tag"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<open /")
def test_020_open() -> None:
    _verify(
        "<open /",
        [["error", "unclosed tag"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<=div></=div>")
def test_021_div_div() -> None:
    _verify(
        "<=div></=div>",
        [["error", "illegal first char nodeName", {"data": "<=div>", "line": 0, "column": 0}]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<div=></div=>")
def test_022_div_div() -> None:
    _verify(
        "<div=></div=>",
        [["error", "invalid nodeName"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<a><b></c></b></a>")
def test_023_a_b_c_b_a() -> None:
    _verify(
        "<a><b></c></b></a>",
        [
            ["openTag", "a", {}, False],
            ["openTag", "b", {}, False],
            ["error", "closing tag mismatch", {"data": "</c>", "line": 0, "column": 6}],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<_a><:b></:b></_a>")
def test_024_a_b_b_a() -> None:
    _verify(
        "<_a><:b></:b></_a>",
        [
            ["openTag", "_a", {}, False],
            ["openTag", ":b", {}, False],
            ["closeTag", ":b", False],
            ["closeTag", "_a", False],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root a:::="A" :b="B" ::c="C"/>')
def test_025_root_a_a_b_b_c_c() -> None:
    _verify(
        '<root a:::="A" :b="B" ::c="C"/>',
        [
            ["openTag", "root", {"a:::": "A", ":b": "B", "::c": "C"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<a><!--comment text--></a>")
def test_026_a_comment_text_a() -> None:
    _verify(
        "<a><!--comment text--></a>",
        [["openTag", "a", {}, False], ["comment", "comment text"], ["closeTag", "a", False]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root><foo>")
def test_027_root_foo() -> None:
    _verify(
        "<root><foo>",
        [
            ["openTag", "root"],
            ["openTag", "foo"],
            ["error", "unexpected end of file", {"data": "", "line": 0, "column": 11}],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root/><f")
def test_028_root_f() -> None:
    _verify(
        "<root/><f",
        [
            ["openTag", "root", {}, True],
            ["closeTag", "root", True],
            ["error", "unclosed tag", {"data": "<f", "line": 0, "column": 7}],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root></rof")
def test_029_root_rof() -> None:
    _verify(
        "<root></rof",
        [
            ["openTag", "root", {}, False],
            ["error", "unclosed tag", {"data": "</rof", "line": 0, "column": 6}],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root></rof</root>")
def test_030_root_rof_root() -> None:
    _verify(
        "<root></rof</root>",
        [
            ["openTag", "root", {}, False],
            ["error", "closing tag mismatch", {"data": "</rof</root>", "line": 0, "column": 6}],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root>text</root>")
def test_031_root_text_root() -> None:
    _verify(
        "<root>text</root>",
        [
            ["openTag", "root"],
            ["text", "text", {"data": "ext", "line": 0, "column": 10}],
            ["closeTag", "root"],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "a<root />")
def test_032_a_root() -> None:
    _verify(
        "a<root />",
        [
            ["warn", "non-whitespace outside of root node", {"data": "a", "line": 0, "column": 0}],
            ["openTag", "root"],
            ["closeTag", "root"],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root />a")
def test_033_root_a() -> None:
    _verify(
        "<root />a",
        [
            ["openTag", "root"],
            ["closeTag", "root"],
            ["warn", "non-whitespace outside of root node", {"data": "a", "line": 0, "column": 8}],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root>a<child />b</root>")
def test_034_root_a_child_b_root() -> None:
    _verify(
        "<root>a<child />b</root>",
        [
            ["openTag", "root"],
            ["text", "a"],
            ["openTag", "child"],
            ["closeTag", "child"],
            ["text", "b"],
            ["closeTag", "root"],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<?xml version="1.0" encoding="UTF-8"?> <root/>')
def test_035_xml_version_1_0_encoding_utf_8_root() -> None:
    _verify(
        '<?xml version="1.0" encoding="UTF-8"?>\n\t <root/>',
        [
            ["question", '<?xml version="1.0" encoding="UTF-8"?>'],
            ["openTag", "root"],
            ["closeTag", "root"],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<?xml version="1.0" encoding="UTF-8"?> a <root/>')
def test_036_xml_version_1_0_encoding_utf_8_a_roo() -> None:
    _verify(
        '<?xml version="1.0" encoding="UTF-8"?>\na\n<root/>\n',
        [
            ["question", '<?xml version="1.0" encoding="UTF-8"?>'],
            ["warn", "non-whitespace outside of root node"],
            ["openTag", "root"],
            ["closeTag", "root"],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root /><otherRoot />")
def test_037_root_otherroot() -> None:
    _verify(
        "<root /><otherRoot />\n",
        [
            ["openTag", "root"],
            ["closeTag", "root"],
            ["openTag", "otherRoot"],
            ["closeTag", "otherRoot"],
        ],
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<root xmlns="http://www.w3.org/2005/Atom" /><atom:otherRoot xmlns:atom="http://not-atom" />',
)
def test_038_root_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<root xmlns="http://www.w3.org/2005/Atom" /><atom:otherRoot xmlns:atom="http://not-atom" />',  # noqa: E501
        [
            ["openTag", "atom:root"],
            ["closeTag", "atom:root"],
            ["openTag", "ns0:otherRoot"],
            ["closeTag", "ns0:otherRoot"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root LENGTH="abc=ABC"></root>')
def test_039_root_length_abc_abc_root() -> None:
    _verify(
        '<root LENGTH="abc=ABC"></root>',
        [["openTag", "root", {"LENGTH": "abc=ABC"}, False], ["closeTag", "root", False]],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root xmlns:xmlns="http://foo" a="B"></root>')
def test_040_root_xmlns_xmlns_http_foo_a_b_root() -> None:
    _verify(
        '<root xmlns:xmlns="http://foo" a="B"></root>',
        [
            ["warn", "illegal declaration of xmlns"],
            ["openTag", "root", {"a": "B"}],
            ["closeTag", "root"],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root xmlns:xml="http://foo" a="B"></root>')
def test_041_root_xmlns_xml_http_foo_a_b_root() -> None:
    _verify(
        '<root xmlns:xml="http://foo" a="B"></root>',
        [
            ["error", "illegal value of xmlns:xml"],
            ["openTag", "root", {"a": "B"}],
            ["closeTag", "root"],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root length='abc=abc'></root>")
def test_042_root_length_abc_abc_root() -> None:
    _verify(
        "<root length='abc=abc'></root>",
        [["openTag", "root", {"length": "abc=abc"}, False], ["closeTag", "root", False]],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root _abc="abc=abc" :abc="abc"></root>')
def test_043_root_abc_abc_abc_abc_abc_root() -> None:
    _verify(
        '<root _abc="abc=abc" :abc="abc"></root>',
        [
            ["openTag", "root", {"_abc": "abc=abc", ":abc": "abc"}, False],
            ["closeTag", "root", False],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root attr1="first" attr2="second"/>')
def test_044_root_attr1_first_attr2_second() -> None:
    _verify(
        '<root attr1="first"\t attr2="second"/>',
        [
            ["openTag", "root", {"attr1": "first", "attr2": "second"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<root attr1="first"attr2="second" attr1="a"b a="B" />'
)
def test_045_root_attr1_first_attr2_second_attr1() -> None:
    _verify(
        '<root attr1="first"attr2="second" attr1="a"b a="B" />',
        [
            ["warn", "illegal character after attribute end"],
            ["warn", "illegal character after attribute end"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root =attr1="first" a="B" />')
def test_046_root_attr1_first_a_b() -> None:
    _verify(
        '<root =attr1="first" a="B" />',
        [
            ["warn", "illegal first char attribute name"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root .attr1="first" a="B" />')
def test_047_root_attr1_first_a_b() -> None:
    _verify(
        '<root .attr1="first" a="B" />',
        [
            ["warn", "illegal first char attribute name"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root a="B" attr1="first\' />')
def test_048_root_a_b_attr1_first() -> None:
    _verify(
        '<root a="B" attr1="first\' />',
        [
            ["warn", "attribute value quote missmatch"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root a="B" attr1="first />')
def test_049_root_a_b_attr1_first() -> None:
    _verify(
        '<root a="B" attr1="first />',
        [
            ["warn", "missing closing quotes"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root attr1=\'first" a="B" />')
def test_050_root_attr1_first_a_b() -> None:
    _verify(
        '<root attr1=\'first" a="B" />',
        [
            ["warn", "attribute value quote missmatch"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<root $attr1="first" ☂attr1="first" attr2="second"/>'
)
def test_051_root_attr1_first_attr1_first_attr2_s() -> None:
    _verify(
        '<root $attr1="first" ☂attr1="first" attr2="second"/>',
        [
            ["warn", "illegal first char attribute name"],
            ["warn", "illegal first char attribute name"],
            ["openTag", "root", {"attr2": "second"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root rain="☂"/>')
def test_052_root_rain() -> None:
    _verify(
        '<root rain="☂"/>',
        [["openTag", "root", {"rain": "☂"}, True], ["closeTag", "root", True]],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root <attr1="first" attr2="second"/>')
def test_053_root_attr1_first_attr2_second() -> None:
    _verify(
        '<root <attr1="first" attr2="second"/>',
        [
            ["warn", "illegal first char attribute name"],
            ["openTag", "root", {"attr2": "second"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root attr1☂="first" attr2="second"/>')
def test_054_root_attr1_first_attr2_second() -> None:
    _verify(
        '<root attr1☂="first" attr2="second"/>',
        [
            ["warn", "illegal attribute name char"],
            ["openTag", "root", {"attr2": "second"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root xmlns:color_1-.0="http://color" />')
def test_055_root_xmlns_color_1_0_http_color() -> None:
    _verify(
        '<root xmlns:color_1-.0="http://color" />',
        [
            ["openTag", "root", {"xmlns:color_1-.0": "http://color"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root a:b:c="B" xmlns:b:c="http://color" />')
def test_056_root_a_b_c_b_xmlns_b_c_http_color() -> None:
    _verify(
        '<root a:b:c="B" xmlns:b:c="http://color" />',
        [["openTag", "root", {"xmlns:b:c": "http://color"}, True], ["closeTag", "root", True]],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root color_1-.0="green" />')
def test_057_root_color_1_0_green() -> None:
    _verify(
        '<root color_1-.0="green" />',
        [["openTag", "root", {"color_1-.0": "green"}, True], ["closeTag", "root", True]],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root attr1 a="B"/>')
def test_058_root_attr1_a_b() -> None:
    _verify(
        '<root attr1 a="B"/>',
        [
            ["warn", "missing attribute value"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )
    # same ledger title, second occurrence transcribes '<root attr1\na="B"/>'
    _verify(
        '<root attr1\na="B"/>',
        [
            ["warn", "missing attribute value"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root attr1=value a="B" />')
def test_059_root_attr1_value_a_b() -> None:
    _verify(
        '<root attr1=value a="B" />',
        [
            ["warn", "missing attribute value quotes"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )
    # same ledger title, second occurrence transcribes '<root attr1=value\na="B" />'
    _verify(
        '<root attr1=value\na="B" />',
        [
            ["warn", "missing attribute value quotes"],
            ["openTag", "root", {"a": "B"}, True],
            ["closeTag", "root", True],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<root length='12345'><item/></root>")
def test_060_root_length_12345_item_root() -> None:
    _verify(
        "<root length='12345'><item/></root>",
        [
            ["openTag", "root", {"length": "12345"}, False],
            ["openTag", "item", {}, True],
            ["closeTag", "item", True],
            ["closeTag", "root", False],
        ],
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", "<r><![CDATA[ this is ]]><![CDATA[ this is [] ]]></r>"
)
def test_061_r_cdata_this_is_cdata_this_is_r() -> None:
    _verify(
        "<r><![CDATA[ this is ]]><![CDATA[ this is [] ]]></r>",
        [["openTag", "r"], ["cdata", " this is "], ["cdata", " this is [] "], ["closeTag", "r"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<r><![CDATA[[[[[[[[[]]]]]]]]]]></r>")
def test_062_r_cdata_r() -> None:
    _verify(
        "<r><![CDATA[[[[[[[[[]]]]]]]]]]></r>",
        [["openTag", "r"], ["cdata", "[[[[[[[[]]]]]]]]"], ["closeTag", "r"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<r><![CDATA[</r>")
def test_063_r_cdata_r() -> None:
    _verify(
        "<r><![CDATA[</r>",
        [["openTag", "r"], ["error", "unclosed cdata"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<r>&lt;![CDATA[ this is ]]&gt;</r>")
def test_064_r_lt_cdata_this_is_gt_r() -> None:
    _verify(
        "<r>&lt;![CDATA[ this is ]]&gt;</r>",
        [["openTag", "r"], ["text", "&lt;![CDATA[ this is ]]&gt;"], ["closeTag", "r"]],
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", "<html><head><script>'<div>foo</div></'</script></head></html>"
)
def test_065_html_head_script_div_foo_div_script() -> None:
    _verify(
        "<html><head><script>'<div>foo</div></'</script></head></html>",
        [
            ["openTag", "html"],
            ["openTag", "head"],
            ["openTag", "script"],
            ["text", "'"],
            ["openTag", "div"],
            ["text", "foo"],
            ["closeTag", "div"],
            ["error", "closing tag mismatch"],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<xmlns/>")
def test_066_xmlns() -> None:
    _verify(
        "<xmlns/>",
        [["openTag", "xmlns"], ["closeTag", "xmlns"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel></channel></rss>',
)
def test_067_rss_version_2_0_xmlns_atom_http_www() -> None:
    _verify(
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel></channel></rss>',
        [
            ["openTag", "rss", {"xmlns:atom": "http://www.w3.org/2005/Atom", "version": "2.0"}],
            ["openTag", "channel"],
            ["closeTag", "channel"],
            ["closeTag", "rss"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" id="aa" media:title="bb"/>',  # noqa: E501
)
def test_068_feed_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" id="aa" media:title="bb"/>',  # noqa: E501
        [["openTag", "atom:feed", {"id": "aa", "media:title": "bb"}], ["closeTag", "atom:feed"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" id="aa" media:title="bb"></feed>',  # noqa: E501
)
def test_069_feed_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" id="aa" media:title="bb"></feed>',  # noqa: E501
        [["openTag", "atom:feed", {"id": "aa", "media:title": "bb"}], ["closeTag", "atom:feed"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:m="http://search.yahoo.com/mrss/" id="aa" m:title="bb"/>',  # noqa: E501
)
def test_070_feed_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:m="http://search.yahoo.com/mrss/" id="aa" m:title="bb"/>',  # noqa: E501
        [["openTag", "atom:feed", {"id": "aa", "media:title": "bb"}], ["closeTag", "atom:feed"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:a="http://www.w3.org/2005/Atom" id="aa" a:title="bb"/>',  # noqa: E501
)
def test_071_feed_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:a="http://www.w3.org/2005/Atom" id="aa" a:title="bb"/>',  # noqa: E501
        [["openTag", "atom:feed", {"id": "aa", "title": "bb"}], ["closeTag", "atom:feed"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/"><media:title>text</media:title></feed>',
)
def test_072_feed_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/"><media:title>text</media:title></feed>',
        [
            ["openTag", "atom:feed"],
            ["openTag", "media:title"],
            ["text", "text"],
            ["closeTag", "media:title"],
            ["closeTag", "atom:feed"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:m="http://search.yahoo.com/mrss/"><m:title>text</m:title></feed>',
)
def test_073_feed_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:m="http://search.yahoo.com/mrss/"><m:title>text</m:title></feed>',
        [
            ["openTag", "atom:feed"],
            ["openTag", "media:title"],
            ["text", "text"],
            ["closeTag", "media:title"],
            ["closeTag", "atom:feed"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:a="http://www.w3.org/2005/Atom"><a:title>text</a:title></feed>',
)
def test_074_feed_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:a="http://www.w3.org/2005/Atom"><a:title>text</a:title></feed>',
        [
            ["openTag", "atom:feed"],
            ["openTag", "atom:title"],
            ["text", "text"],
            ["closeTag", "atom:title"],
            ["closeTag", "atom:feed"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:="http://search.yahoo.com/mrss/" id="aa" :title="bb"><:text/></feed>',  # noqa: E501
)
def test_075_feed_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:="http://search.yahoo.com/mrss/" id="aa" :title="bb"><:text/></feed>',  # noqa: E501
        [
            ["openTag", "atom:feed", {"id": "aa", "media:title": "bb"}],
            ["openTag", "media:text"],
            ["closeTag", "media:text"],
            ["closeTag", "atom:feed"],
        ],
        ns=True,
    )
    # same ledger title, second occurrence transcribes '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:="http://search.yahoo.com/mrss/" id="aa" :title="bb"><:text/></feed>'  # noqa: E501
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:="http://search.yahoo.com/mrss/" id="aa" :title="bb"><:text/></feed>',  # noqa: E501
        [
            [
                "openTag",
                "atom:feed",
                {"id": "aa", "media:title": "bb"},
                False,
                {
                    "line": 0,
                    "column": 0,
                    "data": '<feed xmlns="http://www.w3.org/2005/Atom" '
                    'xmlns:="http://search.yahoo.com/mrss/" id="aa" :title="bb">',
                },
            ],
            ["openTag", "media:text", {}, True, {"line": 0, "column": 101, "data": "<:text/>"}],
            ["closeTag", "media:text", True, {"line": 0, "column": 101, "data": "<:text/>"}],
            ["closeTag", "atom:feed", False, {"line": 0, "column": 109, "data": "</feed>"}],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<root xmlns="http://foo" xmlns:bar="http://bar" id="aa" bar:title="bb"><bar:child /></root>',
)
def test_076_root_xmlns_http_foo_xmlns_bar_http_b() -> None:
    _verify(
        '<root xmlns="http://foo" xmlns:bar="http://bar" id="aa" bar:title="bb"><bar:child /></root>',  # noqa: E501
        [
            ["openTag", "ns0:root", {"id": "aa", "bar:title": "bb"}],
            ["openTag", "bar:child"],
            ["closeTag", "bar:child"],
            ["closeTag", "ns0:root"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:="http://search.yahoo.com/mrss/" id="aa" :title="bb"> <:text/> </feed>',  # noqa: E501
)
def test_077_feed_xmlns_http_www_w3_org_2005_atom() -> None:
    _verify(
        '<feed xmlns="http://www.w3.org/2005/Atom" \r\n      xmlns:="http://search.yahoo.com/mrss/" id="aa" :title="bb">\r  <:text/>\n</feed>',  # noqa: E501
        [
            [
                "openTag",
                "atom:feed",
                {"id": "aa", "media:title": "bb"},
                False,
                {
                    "line": 0,
                    "column": 0,
                    "data": '<feed xmlns="http://www.w3.org/2005/Atom" \r\n'
                    '      xmlns:="http://search.yahoo.com/mrss/" id="aa" :title="bb">',
                },
            ],
            ["text", "\r  "],
            ["openTag", "media:text", {}, True, {"line": 2, "column": 2, "data": "<:text/>"}],
            ["closeTag", "media:text", True, {"line": 2, "column": 2, "data": "<:text/>"}],
            ["text", "\n"],
            ["closeTag", "atom:feed", False, {"line": 3, "column": 0, "data": "</feed>"}],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://this" xmlns:that="http://that" id="aa" that:title="bb" />',
)
def test_078_foo_xmlns_http_this_xmlns_that_http() -> None:
    _verify(
        '<foo xmlns="http://this" xmlns:that="http://that" id="aa" that:title="bb" />',
        [
            [
                "openTag",
                "ns0:foo",
                {"id": "aa", "that:title": "bb"},
                True,
                {
                    "line": 0,
                    "column": 0,
                    "data": '<foo xmlns="http://this" xmlns:that="http://that" id="aa" that:title="bb" '  # noqa: E501
                    "/>",
                },
            ],
            [
                "closeTag",
                "ns0:foo",
                True,
                {
                    "line": 0,
                    "column": 0,
                    "data": '<foo xmlns="http://this" xmlns:that="http://that" id="aa" that:title="bb" '  # noqa: E501
                    "/>",
                },
            ],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://this" xmlns:bar="http://bar"><t xmlns="http://that" id="aa" bar:title="bb" /></foo>',  # noqa: E501
)
def test_079_foo_xmlns_http_this_xmlns_bar_http_b() -> None:
    _verify(
        '<foo xmlns="http://this" xmlns:bar="http://bar"><t xmlns="http://that" id="aa" bar:title="bb" /></foo>',  # noqa: E501
        [
            ["openTag", "ns0:foo", {}, False],
            ["openTag", "ns1:t", {"id": "aa", "bar:title": "bb"}, True],
            ["closeTag", "ns1:t", True],
            ["closeTag", "ns0:foo", False],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://this" xmlns:bar="http://bar"><t xmlns="http://that"><n/><n/></t></foo>',
)
def test_080_foo_xmlns_http_this_xmlns_bar_http_b() -> None:
    _verify(
        '<foo xmlns="http://this" xmlns:bar="http://bar"><t xmlns="http://that"><n/><n/></t></foo>',
        [
            ["openTag", "ns0:foo"],
            ["openTag", "ns1:t"],
            ["openTag", "ns1:n"],
            ["closeTag", "ns1:n"],
            ["openTag", "ns1:n"],
            ["closeTag", "ns1:n"],
            ["closeTag", "ns1:t"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://this" xmlns:bar="http://bar"><t xmlns="http://that"><n id="b" bar:title="BAR"></n></t></foo>',  # noqa: E501
)
def test_081_foo_xmlns_http_this_xmlns_bar_http_b() -> None:
    _verify(
        '<foo xmlns="http://this" xmlns:bar="http://bar"><t xmlns="http://that"><n id="b" bar:title="BAR"></n></t></foo>',  # noqa: E501
        [
            ["openTag", "ns0:foo"],
            ["openTag", "ns1:t"],
            ["openTag", "ns1:n", {"id": "b", "bar:title": "BAR"}],
            ["closeTag", "ns1:n"],
            ["closeTag", "ns1:t"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo:root xmlns:foo="http://foo" xmlns:bar="http://bar"><bar:outer><nested/></bar:outer></foo:root>',
)
def test_082_foo_root_xmlns_foo_http_foo_xmlns_ba() -> None:
    _verify(
        '<foo:root xmlns:foo="http://foo" xmlns:bar="http://bar"><bar:outer><nested/></bar:outer></foo:root>',
        [
            ["openTag", "foo:root"],
            ["openTag", "bar:outer"],
            ["openTag", "nested"],
            ["closeTag", "nested"],
            ["closeTag", "bar:outer"],
            ["closeTag", "foo:root"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://this" xmlns:bar="http://bar"><t xmlns="http://that" xmlns:b="http://bar"><b:other bar:attr="BAR" /></t></foo>',  # noqa: E501
)
def test_083_foo_xmlns_http_this_xmlns_bar_http_b() -> None:
    _verify(
        '<foo xmlns="http://this" xmlns:bar="http://bar"><t xmlns="http://that" xmlns:b="http://bar"><b:other bar:attr="BAR" /></t></foo>',  # noqa: E501
        [
            ["openTag", "ns0:foo"],
            ["openTag", "ns1:t"],
            ["openTag", "bar:other", {"bar:attr": "BAR"}],
            ["closeTag", "bar:other"],
            ["closeTag", "ns1:t"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<foo xmlns="http://xxx"></foo>')
def test_084_foo_xmlns_http_xxx_foo() -> None:
    _verify(
        '<foo xmlns="http://xxx"></foo>',
        [["openTag", "ns0:foo", {"xmlns": "http://xxx"}], ["closeTag", "ns0:foo", False]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://xxx" xmlns:a="http://www.w3.org/2005/Atom" a:xx="foo"></foo>',
)
def test_085_foo_xmlns_http_xxx_xmlns_a_http_www() -> None:
    _verify(
        '<foo xmlns="http://xxx" xmlns:a="http://www.w3.org/2005/Atom" a:xx="foo"></foo>',
        [
            [
                "openTag",
                "ns0:foo",
                {"xmlns:a": "http://www.w3.org/2005/Atom", "xmlns": "http://xxx", "atom:xx": "foo"},
            ],
            ["closeTag", "ns0:foo", False],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<foo xmlns="http://xxx"><bar:unknown /></foo>')
def test_086_foo_xmlns_http_xxx_bar_unknown_foo() -> None:
    _verify(
        '<foo xmlns="http://xxx"><bar:unknown /></foo>',
        [
            ["openTag", "ns0:foo"],
            [
                "error",
                "missing namespace on <bar:unknown>",
                {"data": "<bar:unknown />", "line": 0, "column": 24},
            ],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<foo xmlns="http://xxx"><__proto__:unknown /></foo>'
)
def test_087_foo_xmlns_http_xxx_proto_unknown_foo() -> None:
    _verify(
        '<foo xmlns="http://xxx"><__proto__:unknown /></foo>',
        [["openTag", "ns0:foo"], ["error", "missing namespace on <__proto__:unknown>"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<foo xmlns="http://xxx"><constructor:unknown /></foo>'
)
def test_088_foo_xmlns_http_xxx_constructor_unkno() -> None:
    _verify(
        '<foo xmlns="http://xxx"><constructor:unknown /></foo>',
        [["openTag", "ns0:foo"], ["error", "missing namespace on <constructor:unknown>"]],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<foo xmlns="http://xxx" __proto__:bar="BAR" />')
def test_089_foo_xmlns_http_xxx_proto_bar_bar() -> None:
    _verify(
        '<foo xmlns="http://xxx" __proto__:bar="BAR" />',
        [
            ["warn", "missing namespace for prefix <__proto__>"],
            ["openTag", "ns0:foo"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<foo xmlns="http://xxx" hasOwnProperty:bar="BAR" />'
)
def test_090_foo_xmlns_http_xxx_hasownproperty_ba() -> None:
    _verify(
        '<foo xmlns="http://xxx" hasOwnProperty:bar="BAR" />',
        [
            ["warn", "missing namespace for prefix <hasOwnProperty>"],
            ["openTag", "ns0:foo"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<a$uri:foo xmlns:a$uri="http://not-atom" />')
def test_091_a_uri_foo_xmlns_a_uri_http_not_atom() -> None:
    _verify(
        '<a$uri:foo xmlns:a$uri="http://not-atom" />',
        [["error", "invalid nodeName"]],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<atom:foo xmlns:atom="http://not-atom" />')
def test_092_atom_foo_xmlns_atom_http_not_atom() -> None:
    _verify(
        '<atom:foo xmlns:atom="http://not-atom" />',
        [["openTag", "ns0:foo"], ["closeTag", "ns0:foo"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<foo xmlns="http://not-ns0" xmlns:ns0="http://ns0" ns0:bar="BAR" />'
)
def test_093_foo_xmlns_http_not_ns0_xmlns_ns0_htt() -> None:
    _verify(
        '<foo xmlns="http://not-ns0" xmlns:ns0="http://ns0" ns0:bar="BAR" />',
        [["openTag", "ns0:foo", {"ns1:bar": "BAR"}], ["closeTag", "ns0:foo"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://foo" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="Foo" />',  # noqa: E501
)
def test_094_foo_xmlns_http_foo_xmlns_xsi_http_ww() -> None:
    _verify(
        '<foo xmlns="http://foo" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="Foo" />',  # noqa: E501
        [["openTag", "ns0:foo", {"xsi:type": "Foo"}], ["closeTag", "ns0:foo"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://foo" xmlns:o="http://www.w3.org/2001/XMLSchema-instance" o:type="Foo" />',
)
def test_095_foo_xmlns_http_foo_xmlns_o_http_www() -> None:
    _verify(
        '<foo xmlns="http://foo" xmlns:o="http://www.w3.org/2001/XMLSchema-instance" o:type="Foo" />',  # noqa: E501
        [["openTag", "ns0:foo", {"o:type": "Foo"}], ["closeTag", "ns0:foo"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://foo" xmlns:bar="http://bar" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="bar:Bar" />',  # noqa: E501
)
def test_096_foo_xmlns_http_foo_xmlns_bar_http_ba() -> None:
    _verify(
        '<foo xmlns="http://foo" xmlns:bar="http://bar" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="bar:Bar" />',  # noqa: E501
        [["openTag", "ns0:foo", {"xsi:type": "bar:Bar"}], ["closeTag", "ns0:foo"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://foo" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="xs:string" />',  # noqa: E501
)
def test_097_foo_xmlns_http_foo_xmlns_xsi_http_ww() -> None:
    _verify(
        '<foo xmlns="http://foo" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="xs:string" />',  # noqa: E501
        [["openTag", "ns0:foo", {"xsi:type": "xs:string"}], ["closeTag", "ns0:foo"]],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://foo" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><bar xsi:type="Bar" /></foo>',  # noqa: E501
)
def test_098_foo_xmlns_http_foo_xmlns_xsi_http_ww() -> None:
    _verify(
        '<foo xmlns="http://foo" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><bar xsi:type="Bar" /></foo>',  # noqa: E501
        [
            ["openTag", "ns0:foo"],
            ["openTag", "ns0:bar", {"xsi:type": "Bar"}],
            ["closeTag", "ns0:bar"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://foo" xmlns:bar="http://bar" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><bar xsi:type="bar:Bar" /></foo>',  # noqa: E501
)
def test_099_foo_xmlns_http_foo_xmlns_bar_http_ba() -> None:
    _verify(
        '<foo xmlns="http://foo" xmlns:bar="http://bar" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><bar xsi:type="bar:Bar" /></foo>',  # noqa: E501
        [
            ["openTag", "ns0:foo"],
            ["openTag", "ns0:bar", {"xsi:type": "bar:Bar"}],
            ["closeTag", "ns0:bar"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<foo xmlns="http://foo" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><bar xsi:type="xs:string" /></foo>',  # noqa: E501
)
def test_100_foo_xmlns_http_foo_xmlns_xsi_http_ww() -> None:
    _verify(
        '<foo xmlns="http://foo" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><bar xsi:type="xs:string" /></foo>',  # noqa: E501
        [
            ["openTag", "ns0:foo"],
            ["openTag", "ns0:bar", {"xsi:type": "xs:string"}],
            ["closeTag", "ns0:bar"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<foo:foo xmlns:foo="http://foo" bar:no-ns="BAR" />'
)
def test_101_foo_foo_xmlns_foo_http_foo_bar_no_ns() -> None:
    _verify(
        '<foo:foo xmlns:foo="http://foo" bar:no-ns="BAR" />',
        [
            [
                "warn",
                "missing namespace for prefix <bar>",
                {
                    "column": 0,
                    "line": 0,
                    "data": '<foo:foo xmlns:foo="http://foo" bar:no-ns="BAR" />',
                },
            ],
            ["openTag", "foo:foo"],
            ["closeTag", "foo:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<foo xmlns="http://foo"><bar xx:bar="BAR" /></foo>'
)
def test_102_foo_xmlns_http_foo_bar_xx_bar_bar_fo() -> None:
    _verify(
        '<foo xmlns="http://foo"><bar xx:bar="BAR" /></foo>',
        [
            ["openTag", "ns0:foo"],
            ["warn", "missing namespace for prefix <xx>"],
            ["openTag", "ns0:bar"],
            ["closeTag", "ns0:bar"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<foo xmlns="http://xxx" bar:no-ns="BAR" />')
def test_103_foo_xmlns_http_xxx_bar_no_ns_bar() -> None:
    _verify(
        '<foo xmlns="http://xxx" bar:no-ns="BAR" />',
        [
            ["warn", "missing namespace for prefix <bar>"],
            ["openTag", "ns0:foo"],
            ["closeTag", "ns0:foo"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", "<div> </div>")
def test_104_div_div() -> None:
    _verify(
        "\ufeff<div>\ufeff</div>",
        [["openTag", "div"], ["text", "\ufeff"], ["closeTag", "div"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", "<P>тест</P>")
def test_105_p_p() -> None:
    _verify(
        "<P>тест</P>",
        [["openTag", "P"], ["text", "тест"], ["closeTag", "P"]],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<P foo="误" />')
def test_106_p_foo() -> None:
    _verify(
        '<P foo="误" />',
        [["openTag", "P", {"foo": "误"}, True], ["closeTag", "P"]],
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<e:root xmlns:e="http://extensions"><bar:bar xmlns:bar="http://bar"><other:child b="B" xmlns:other="http://other" /></bar:bar><foo xmlns="http://foo"><child a="A" /></foo></e:root>',  # noqa: E501
)
def test_107_e_root_xmlns_e_http_extensions_bar_b() -> None:
    _verify(
        '<e:root xmlns:e="http://extensions"><bar:bar xmlns:bar="http://bar"><other:child b="B" xmlns:other="http://other" /></bar:bar><foo xmlns="http://foo"><child a="A" /></foo></e:root>',  # noqa: E501
        [
            ["openTag", "e:root", {"xmlns:e": "http://extensions"}],
            ["openTag", "bar:bar", {"xmlns:bar": "http://bar"}],
            ["openTag", "other:child", {"b": "B", "xmlns:other": "http://other"}],
            ["closeTag", "other:child"],
            ["closeTag", "bar:bar"],
            ["openTag", "ns0:foo", {"xmlns": "http://foo"}],
            ["openTag", "ns0:child", {"a": "A"}],
            ["closeTag", "ns0:child"],
            ["closeTag", "ns0:foo"],
            ["closeTag", "e:root"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<e:root xmlns:e="http://extensions" xmlns:e="http://other" />'
)
def test_108_e_root_xmlns_e_http_extensions_xmlns() -> None:
    _verify(
        '<e:root xmlns:e="http://extensions" xmlns:e="http://other" />',
        [
            ["warn", "attribute <xmlns:e> already defined"],
            ["openTag", "e:root", {"xmlns:e": "http://extensions"}],
            ["closeTag", "e:root"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<root xmlns="http://extensions" xmlns="http://other" />'
)
def test_109_root_xmlns_http_extensions_xmlns_htt() -> None:
    _verify(
        '<root xmlns="http://extensions" xmlns="http://other" />',
        [
            ["warn", "attribute <xmlns> already defined"],
            ["openTag", "ns0:root", {"xmlns": "http://extensions"}],
            ["closeTag", "ns0:root"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root a="A" a="B" />')
def test_110_root_a_a_a_b() -> None:
    _verify(
        '<root a="A" a="B" />',
        [
            ["warn", "attribute <a> already defined"],
            ["openTag", "root", {"a": "A"}],
            ["closeTag", "root"],
        ],
    )


@pytest.mark.upstream("saxen/test/elements.js", '<root xmlns="http://extensions" a="A" a="B" />')
def test_111_root_xmlns_http_extensions_a_a_a_b() -> None:
    _verify(
        '<root xmlns="http://extensions" a="A" a="B" />',
        [
            ["warn", "attribute <a> already defined"],
            ["openTag", "ns0:root", {"xmlns": "http://extensions", "a": "A"}],
            ["closeTag", "ns0:root"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<root xmlns="http://extensions" xmlns:bar="http://bar" bar:a="A" bar:a="B" />',
)
def test_112_root_xmlns_http_extensions_xmlns_bar() -> None:
    _verify(
        '<root xmlns="http://extensions" xmlns:bar="http://bar" bar:a="A" bar:a="B" />',
        [
            ["warn", "attribute <bar:a> already defined"],
            [
                "openTag",
                "ns0:root",
                {"xmlns": "http://extensions", "xmlns:bar": "http://bar", "bar:a": "A"},
            ],
            ["closeTag", "ns0:root"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><element id="sample>error"></element></doc>')
def test_113_doc_element_id_sample_error_element() -> None:
    _verify(
        '<doc><element id="sample>error"></element></doc>',
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {"id": "sample>error"}, False],
            ["closeTag", "element", False],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<doc> <element id="sample>error" > </element></doc>'
)
def test_114_doc_element_id_sample_error_element() -> None:
    _verify(
        '<doc> \n<element id="sample>error" > \n </element></doc>',
        [
            ["openTag", "doc", {}, False],
            ["text", " \n"],
            ["openTag", "element", {"id": "sample>error"}, False],
            ["text", " \n "],
            ["closeTag", "element", False],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><element fo>o="FOO" bar="BAR" /></doc>')
def test_115_doc_element_fo_o_foo_bar_bar_doc() -> None:
    _verify(
        '<doc><element fo>o="FOO" bar="BAR" /></doc>',
        [
            ["openTag", "doc", {}, False],
            ["warn", "missing attribute value quotes"],
            ["openTag", "element", {}, False],
            ["text", 'o="FOO" bar="BAR" />'],
            ["error", "closing tag mismatch"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><element foo="FOO" >> bar="BAR" /></doc>')
def test_116_doc_element_foo_foo_bar_bar_doc() -> None:
    _verify(
        '<doc><element foo="FOO" >> bar="BAR" /></doc>',
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {"foo": "FOO"}, False],
            ["text", '> bar="BAR" />'],
            ["error", "closing tag mismatch"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><element foo="FOO"> bar="BAR" /></doc>')
def test_117_doc_element_foo_foo_bar_bar_doc() -> None:
    _verify(
        '<doc><element foo="FOO"> bar="BAR" /></doc>',
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {"foo": "FOO"}, False],
            ["text", ' bar="BAR" />'],
            ["error", "closing tag mismatch"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", "<doc><element />></doc>")
def test_118_doc_element_doc() -> None:
    _verify(
        "<doc><element />></doc>",
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {}, True],
            ["closeTag", "element", True],
            ["text", ">"],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", "<doc><element>/></doc>")
def test_119_doc_element_doc() -> None:
    _verify(
        "<doc><element>/></doc>",
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {}, False],
            ["text", "/>"],
            ["error", "closing tag mismatch"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><element id="sample>error" /></doc>')
def test_120_doc_element_id_sample_error_doc() -> None:
    _verify(
        '<doc><element id="sample>error" /></doc>',
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {"id": "sample>error"}, True],
            ["closeTag", "element", True],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc> <element id="sample>error" /> </doc>')
def test_121_doc_element_id_sample_error_doc() -> None:
    _verify(
        '<doc> \n<element id="sample>error"\n /> </doc>',
        [
            ["openTag", "doc", {}, False],
            ["text", " \n"],
            ["openTag", "element", {"id": "sample>error"}, True],
            ["closeTag", "element", True],
            ["text", " "],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc></doc><element id="sample>error" />')
def test_122_doc_doc_element_id_sample_error() -> None:
    _verify(
        '<doc></doc><element id="sample>error" />',
        [
            ["openTag", "doc", {}, False],
            ["closeTag", "doc", False],
            ["openTag", "element", {"id": "sample>error"}, True],
            ["closeTag", "element", True],
        ],
        ns=True,
    )
    # same ledger title, second occurrence transcribes '<doc></doc><element id="sample>error" />\n '
    _verify(
        '<doc></doc><element id="sample>error" />\n ',
        [
            ["openTag", "doc", {}, False],
            ["closeTag", "doc", False],
            ["openTag", "element", {"id": "sample>error"}, True],
            ["closeTag", "element", True],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<doc></doc><!-- !>>> --><element id="sample>error" />'
)
def test_123_doc_doc_element_id_sample_error() -> None:
    _verify(
        '<doc></doc><!-- !>>> --><element id="sample>error" />',
        [
            ["openTag", "doc", {}, False],
            ["closeTag", "doc", False],
            ["comment", " !>>> "],
            ["openTag", "element", {"id": "sample>error"}, True],
            ["closeTag", "element", True],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<doc></doc><!-- !>>> --> <element id="sample>error" />'
)
def test_124_doc_doc_element_id_sample_error() -> None:
    _verify(
        '<doc></doc><!-- !>>> --> <element id="sample>error" />',
        [
            ["openTag", "doc", {}, False],
            ["closeTag", "doc", False],
            ["comment", " !>>> "],
            ["openTag", "element", {"id": "sample>error"}, True],
            ["closeTag", "element", True],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<doc><element foo="FO\'O"> bar="BAR" /></element></doc>'
)
def test_125_doc_element_foo_fo_o_bar_bar_element() -> None:
    _verify(
        '<doc><element foo="FO\'O"> bar="BAR" /></element></doc>',
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {"foo": "FO'O"}, False],
            ["text", ' bar="BAR" />'],
            ["closeTag", "element", False],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", '<doc><element foo=\'FO"O\'> bar="BAR" /></element></doc>'
)
def test_126_doc_element_foo_fo_o_bar_bar_element() -> None:
    _verify(
        '<doc><element foo=\'FO"O\'> bar="BAR" /></element></doc>',
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {"foo": 'FO"O'}, False],
            ["text", ' bar="BAR" />'],
            ["closeTag", "element", False],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><element foo="FO\'O"> bar="BAR" /></doc>')
def test_127_doc_element_foo_fo_o_bar_bar_doc() -> None:
    _verify(
        '<doc><element foo="FO\'O"> bar="BAR" /></doc>',
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {"foo": "FO'O"}, False],
            ["text", ' bar="BAR" />'],
            ["error", "closing tag mismatch"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><element foo=\'FO"O\'> bar="BAR" /></doc>')
def test_128_doc_element_foo_fo_o_bar_bar_doc() -> None:
    _verify(
        '<doc><element foo=\'FO"O\'> bar="BAR" /></doc>',
        [
            ["openTag", "doc", {}, False],
            ["openTag", "element", {"foo": 'FO"O'}, False],
            ["text", ' bar="BAR" />'],
            ["error", "closing tag mismatch"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><!-- foo=\'FO"O\' --> bar="BAR" ></doc>')
def test_129_doc_foo_fo_o_bar_bar_doc() -> None:
    _verify(
        '<doc><!-- foo=\'FO"O\' --> bar="BAR" ></doc>',
        [
            ["openTag", "doc", {}, False],
            ["comment", " foo='FO\"O' "],
            ["text", ' bar="BAR" >'],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><! foo="FO\'O" > bar="BAR" ></doc>')
def test_130_doc_foo_fo_o_bar_bar_doc() -> None:
    _verify(
        '<doc><! foo="FO\'O" > bar="BAR" ></doc>',
        [
            ["openTag", "doc", {}, False],
            ["attention", '<! foo="FO\'O" >'],
            ["text", ' bar="BAR" >'],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><! foo=\'FO"O\' > bar="BAR" ></doc>')
def test_131_doc_foo_fo_o_bar_bar_doc() -> None:
    _verify(
        '<doc><! foo=\'FO"O\' > bar="BAR" ></doc>',
        [
            ["openTag", "doc", {}, False],
            ["attention", "<! foo='FO\"O' >"],
            ["text", ' bar="BAR" >'],
            ["closeTag", "doc", False],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><element foo="FOO>')
def test_132_doc_element_foo_foo() -> None:
    _verify(
        '<doc><element foo="FOO>',
        [
            ["openTag", "doc", {}, False],
            ["warn", "missing closing quotes"],
            ["openTag", "element", {}, False],
            ["error", "unexpected end of file"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", "<doc><element foo='FOO>")
def test_133_doc_element_foo_foo() -> None:
    _verify(
        "<doc><element foo='FOO>",
        [
            ["openTag", "doc", {}, False],
            ["warn", "missing closing quotes"],
            ["openTag", "element", {}, False],
            ["error", "unexpected end of file"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", '<doc><! element foo="FOO >')
def test_134_doc_element_foo_foo() -> None:
    _verify(
        '<doc><! element foo="FOO >',
        [
            ["openTag", "doc", {}, False],
            ["attention", '<! element foo="FOO >'],
            ["error", "unexpected end of file"],
        ],
        ns=True,
    )


@pytest.mark.upstream("saxen/test/elements.js", "<doc><! element foo='FOO >")
def test_135_doc_element_foo_foo() -> None:
    _verify(
        "<doc><! element foo='FOO >",
        [
            ["openTag", "doc", {}, False],
            ["attention", "<! element foo='FOO >"],
            ["error", "unexpected end of file"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<root xmlns:a="http://www.w3.org/2005/Atom"><a:x xmlns:a="http://purl.org/rss/1.0/"><a:y /></a:x><a:z /></root>',  # noqa: E501
)
def test_136_root_xmlns_a_http_www_w3_org_2005_at() -> None:
    _verify(
        '<root xmlns:a="http://www.w3.org/2005/Atom"><a:x xmlns:a="http://purl.org/rss/1.0/"><a:y /></a:x><a:z /></root>',  # noqa: E501
        [
            ["openTag", "root"],
            ["openTag", "rss:x"],
            ["openTag", "rss:y"],
            ["closeTag", "rss:y"],
            ["closeTag", "rss:x"],
            ["openTag", "atom:z"],
            ["closeTag", "atom:z"],
            ["closeTag", "root"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<root xmlns:a="http://www.w3.org/2005/Atom"><a:x xmlns:a="http://purl.org/rss/1.0/"><a:y /></a:x><a:y /></root>',  # noqa: E501
)
def test_137_root_xmlns_a_http_www_w3_org_2005_at() -> None:
    _verify(
        '<root xmlns:a="http://www.w3.org/2005/Atom"><a:x xmlns:a="http://purl.org/rss/1.0/"><a:y /></a:x><a:y /></root>',  # noqa: E501
        [
            ["openTag", "root"],
            ["openTag", "rss:x"],
            ["openTag", "rss:y"],
            ["closeTag", "rss:y"],
            ["closeTag", "rss:x"],
            ["openTag", "atom:y"],
            ["closeTag", "atom:y"],
            ["closeTag", "root"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js",
    '<root xmlns:a="http://www.w3.org/2005/Atom"><a:x xmlns:b="urn:unknown" /><b:y /></root>',
)
def test_138_root_xmlns_a_http_www_w3_org_2005_at() -> None:
    _verify(
        '<root xmlns:a="http://www.w3.org/2005/Atom"><a:x xmlns:b="urn:unknown" /><b:y /></root>',
        [
            ["openTag", "root"],
            ["openTag", "atom:x"],
            ["closeTag", "atom:x"],
            ["error", "missing namespace on <b:y>"],
        ],
        ns=True,
    )


@pytest.mark.upstream(
    "saxen/test/elements.js", "should handle deeply nested namespace declarations"
)
def test_139_deeply_nested_namespace_declarations() -> None:
    depth = 3000
    opening = "".join(f'<p{i}:e xmlns:p{i}="urn:{i}">' for i in range(depth))
    closing = "".join(f"</p{i}:e>" for i in reversed(range(depth)))
    xml = f'<root xmlns="urn:root">{opening}{closing}</root>'
    parser = Parser({"proxy": True})
    parser.ns({})
    count = 0
    last_name = ""

    def _record(el: object) -> None:
        nonlocal count, last_name
        count += 1
        last_name = el.name  # type: ignore[union-attr]

    parser.on("openTag", _record)
    err = parser.parse(xml)
    assert err is None
    assert count == depth + 1
    assert last_name == f"p{depth - 1}:e"
