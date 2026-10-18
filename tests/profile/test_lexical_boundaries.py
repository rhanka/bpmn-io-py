"""Lexical boundary regressions from the independent review (findings #7/#8).

Expectations come from DESIGN R3.3 §2.1.1 (pre-scan skips ECMAScript
whitespace; U+0085 is not ECMAScript whitespace) and §2.5 (host resource
limits refuse with ``resource-limit``), never from the implementation.
"""

from __future__ import annotations


def test_deep_nesting_refuses_typed_never_recursion_error() -> None:
    """600 nested arrays refuse with a typed code, never RecursionError."""
    from bpmn_io.profile import check_lexical

    data = ("[" * 600 + "]" * 600).encode("utf-8")
    try:
        result = check_lexical(data)
    except RecursionError as exc:
        msg = "lexical traversal must not recurse"
        raise AssertionError(msg) from exc
    assert result.status == "refused"
    assert result.code == "resource-limit"  # type: ignore[union-attr]


def test_deep_nesting_objects_refuse_typed() -> None:
    """600 nested objects refuse with the same typed code."""
    from bpmn_io.profile import check_lexical

    data = ('{"a":' * 600 + "0" + "}" * 600).encode("utf-8")
    try:
        result = check_lexical(data)
    except RecursionError as exc:
        msg = "lexical traversal must not recurse"
        raise AssertionError(msg) from exc
    assert result.status == "refused"
    assert result.code == "resource-limit"  # type: ignore[union-attr]


def test_nel_is_not_whitespace_before_overflowing_number() -> None:
    """U+0085 is not ECMAScript whitespace: leading NEL is ``profile-json``.

    The pre-scan (DESIGN R3.3 §2.1.1 step 1) skips ECMAScript whitespace
    only. U+0085 is outside that set, so it is an invalid token and the
    traversal fails before the overflowing number is examined.
    """
    from bpmn_io.profile import check_lexical

    data = '\u0085{"x":1e400}'.encode("utf-8")
    result = check_lexical(data)
    assert result.status == "refused"
    assert result.code == "profile-json"  # type: ignore[union-attr]


def test_overflowing_number_still_reports_number() -> None:
    """Without the NEL prefix the same document reports ``profile-number``."""
    from bpmn_io.profile import check_lexical

    result = check_lexical(b'{"x":1e400}')
    assert result.status == "refused"
    assert result.code == "profile-number"  # type: ignore[union-attr]


def test_ecma_whitespace_around_value_stays_lexically_ok() -> None:
    """JSON whitespace around a value still lexes cleanly."""
    from bpmn_io.profile import check_lexical

    result = check_lexical(b' \t\r\n{"a":1} ')
    assert result.status == "ok"


def test_nbsp_only_prefix_is_trailing_grammar_failure() -> None:
    """A leading NBSP is skipped by the pre-scan, then fails whole-text parse."""
    from bpmn_io.profile import check_lexical

    result = check_lexical('\u00a0{"a":1}'.encode("utf-8"))
    assert result.status == "refused"
    assert result.code == "profile-json"  # type: ignore[union-attr]
