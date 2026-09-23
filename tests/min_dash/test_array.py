"""Ported min-dash array cases (Lot 2).

Claims every ``min-dash/test/array.spec.js`` title. ``flatten`` is the only helper in
``lib/array.js`` and is unused by the ported libraries, so both titles are claimed N-A
with a reason (see ``docs/naming.md`` § min-dash).
"""

from __future__ import annotations

import pytest

import bpmn_io._min_dash as min_dash


@pytest.mark.upstream("min-dash/test/array.spec.js", "should handle null values")
def test_flatten_null_not_transposed() -> None:
    # N-A: `flatten` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "flatten")
    assert "flatten" not in min_dash.__all__


@pytest.mark.upstream("min-dash/test/array.spec.js", "should flatten, one level deep")
def test_flatten_not_transposed() -> None:
    # N-A: `flatten` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "flatten")
