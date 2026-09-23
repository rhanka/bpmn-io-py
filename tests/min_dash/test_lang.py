"""Ported min-dash lang cases (Lot 2).

Claims every ``min-dash/test/lang.spec.js`` title for the transposed helpers (``has``,
``is_function``); the shared ``should work`` title also covers the N-A predicates
(``isDefined``/``isUndefined``/``isNil``) with a reason.
"""

from __future__ import annotations

import pytest

import bpmn_io._min_dash as min_dash


@pytest.mark.upstream("min-dash/test/lang.spec.js", "should work for {}")
def test_has_on_dict() -> None:
    obj = {"a": 1, "e": None}
    assert min_dash.has(obj, "a") is True
    assert min_dash.has(obj, "e") is True
    assert min_dash.has(obj, "c") is False


@pytest.mark.upstream("min-dash/test/lang.spec.js", "should work for []")
def test_has_on_list() -> None:
    assert min_dash.has([1, 2, 3], "1") is True
    assert min_dash.has([1, 2, 3], "5") is False


@pytest.mark.upstream("min-dash/test/lang.spec.js", "should handle invalid input")
def test_has_invalid_input() -> None:
    assert min_dash.has(None, "1") is False
    assert min_dash.has(0, "1") is False
    assert min_dash.has("", "length") is True


@pytest.mark.upstream("min-dash/test/lang.spec.js", "should work")
def test_predicates() -> None:
    assert min_dash.is_function(lambda: None) is True
    assert min_dash.is_function({}) is False
    assert min_dash.is_function(None) is False
    # N-A in this title: isDefined/isUndefined/isNil are unused by the ported
    # libraries (see docs/naming.md § min-dash); None/UNDEFINED semantics live in
    # bpmn_io._js and are covered by tests/test_js.py.
    assert not hasattr(min_dash, "is_defined")
    assert not hasattr(min_dash, "is_undefined")
    assert not hasattr(min_dash, "is_nil")
    assert not hasattr(min_dash, "is_array")
    assert not hasattr(min_dash, "is_number")
    assert not hasattr(min_dash, "ensure_array")
