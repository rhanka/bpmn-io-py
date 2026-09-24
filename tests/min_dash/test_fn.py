"""Ported min-dash fn cases (Lot 2).

Claims every ``min-dash/test/fn.spec.js`` title. Only ``bind`` is transposed;
``debounce``/``throttle`` are claimed N-A with a reason (see ``docs/naming.md``
§ min-dash): no ported library uses them, and timer-driven re-entrancy has no
equivalent in the synchronous port.
"""

from __future__ import annotations

import pytest

import bpmn_io._min_dash as min_dash


@pytest.mark.upstream("min-dash/test/fn.spec.js", "should bind fn")
def test_bind_fn() -> None:
    def get_foo(self: dict[str, str]) -> str:
        return self["foo"]

    bound = min_dash.bind(get_foo, {"foo": "FOO"})
    assert bound() == "FOO"


def test_bind_method_used_by_moddle() -> None:
    # The moddle call shape: forEach(attrs, bind(fn(self, val, key), this)).
    seen: dict[str, int] = {}

    class Registry:
        def register_package(self, package: str, index: int) -> None:
            seen[package] = index

    registry = Registry()
    min_dash.for_each(["a", "b"], min_dash.bind(registry.register_package, registry))
    assert seen == {"a": 0, "b": 1}


@pytest.mark.upstream("min-dash/test/fn.spec.js", "should debounce fn")
def test_debounce_not_transposed() -> None:
    # N-A: `debounce` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "debounce")
    assert "debounce" not in min_dash.__all__


@pytest.mark.upstream("min-dash/test/fn.spec.js", "should pass last args")
def test_debounce_args_not_transposed() -> None:
    # N-A: `debounce` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "debounce")


@pytest.mark.upstream("min-dash/test/fn.spec.js", "should use last this")
def test_debounce_this_not_transposed() -> None:
    # N-A: `debounce` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "debounce")


@pytest.mark.upstream("min-dash/test/fn.spec.js", "should not repetitively call #clearTimeout")
def test_debounce_timers_not_transposed() -> None:
    # N-A: `debounce` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "debounce")


@pytest.mark.upstream("min-dash/test/fn.spec.js", "should #cancel")
def test_debounce_cancel_not_transposed() -> None:
    # N-A: `debounce` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "debounce")


@pytest.mark.upstream("min-dash/test/fn.spec.js", "should #flush")
def test_debounce_flush_not_transposed() -> None:
    # N-A: `debounce` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "debounce")


@pytest.mark.upstream("min-dash/test/fn.spec.js", "should throttle fn")
def test_throttle_not_transposed() -> None:
    # N-A: `throttle` is unused by the ported libraries (see docs/naming.md § min-dash).
    assert not hasattr(min_dash, "throttle")
    assert "throttle" not in min_dash.__all__
