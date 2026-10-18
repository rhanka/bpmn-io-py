"""Canonical JSON and digests (profile-c14n/2) for the lint bridge."""

from __future__ import annotations

import pytest

from bpmn_io.profile._lint.c14n import digest, dumps_jcs, render_number, utf16_key


def test_number_vectors() -> None:
    """ECMAScript rendering vectors (DESIGN R3.3 section 14.3 plus boundaries)."""
    assert render_number(1.0) == "1"
    assert render_number(1e20) == "100000000000000000000"
    assert render_number(123456789012345680000) == "123456789012345680000"
    assert render_number(1e21) == "1e+21"
    assert render_number(1e-6) == "0.000001"
    assert render_number(1e-7) == "1e-7"
    assert render_number(5e-324) == "5e-324"
    assert render_number(-0.0) == "0"
    assert render_number(100.0) == "100"
    assert render_number(0.5) == "0.5"


def test_non_finite_numbers_refuse() -> None:
    """NaN and infinities have no canonical form."""
    with pytest.raises(ValueError, match="non-finite"):
        render_number(float("nan"))
    with pytest.raises(ValueError, match="non-finite"):
        render_number(float("inf"))


def test_booleans_are_not_numbers() -> None:
    """Booleans refuse despite subclassing ``int``."""
    with pytest.raises(TypeError, match="booleans are not numbers"):
        render_number(value=True)


def test_utf16_key_order() -> None:
    """U+10000 sorts before U+E000 in UTF-16 code-unit order."""
    assert utf16_key("\U00010000") < utf16_key("\ue000")
    assert dumps_jcs({"\ue000": 1, "\U00010000": 2}).index("2") < dumps_jcs(
        {"\ue000": 1, "\U00010000": 2}
    ).index("1")


def test_jcs_shape() -> None:
    """Canonical JSON sorts keys, drops whitespace and normalizes numbers."""
    assert dumps_jcs({"b": 1.0, "a": [True, None, "x"]}) == '{"a":[true,null,"x"],"b":1}'
    assert digest({"b": 1, "a": 2}) == digest({"a": 2, "b": 1})
    assert len(digest({})) == 64
