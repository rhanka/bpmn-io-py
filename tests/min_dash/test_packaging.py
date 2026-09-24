"""Packaging-surface claims for min-dash (Lot 2).

The bundle specs assert which helpers the built JS package exposes; the TypeScript
spec asserts typings. Neither has a Python equivalent, so every title is claimed N-A:
titles probing transposed helpers assert the helper IS exposed by
``bpmn_io._min_dash``; titles probing unused helpers assert it is NOT, with a reason
(see ``docs/naming.md`` § min-dash).
"""

from __future__ import annotations

import pytest

import bpmn_io._min_dash as min_dash


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.js", "should expose array utils")
def test_bundle_esm_array_not_transposed() -> None:
    # N-A: the array group is `flatten`, unused by the ported libraries.
    assert not hasattr(min_dash, "flatten")


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.js", "should expose collection utils")
def test_bundle_esm_collection_exposed() -> None:
    assert min_dash.find([1], 1) == 1


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.js", "should expose fn utils")
def test_bundle_esm_fn_exposed() -> None:
    assert callable(min_dash.bind(lambda self: self, {}))


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.js", "should expose lang utils")
def test_bundle_esm_lang_not_transposed() -> None:
    # N-A: the lang probe is `isArray`, unused by the ported libraries.
    assert not hasattr(min_dash, "is_array")
    assert min_dash.is_string("a") is True


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.js", "should expose object utils")
def test_bundle_esm_object_exposed() -> None:
    assert min_dash.pick({"a": 1}, ["a"]) == {"a": 1}


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.cjs", "should expose array utils")
def test_bundle_cjs_array_not_transposed() -> None:
    # N-A: the array group is `flatten`, unused by the ported libraries.
    assert not hasattr(min_dash, "flatten")


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.cjs", "should expose collection utils")
def test_bundle_cjs_collection_exposed() -> None:
    assert min_dash.find([1], 1) == 1


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.cjs", "should expose fn utils")
def test_bundle_cjs_fn_exposed() -> None:
    assert callable(min_dash.bind(lambda self: self, {}))


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.cjs", "should expose lang utils")
def test_bundle_cjs_lang_not_transposed() -> None:
    # N-A: the lang probe is `isArray`, unused by the ported libraries.
    assert not hasattr(min_dash, "is_array")


@pytest.mark.upstream("min-dash/test/integration/bundle.spec.cjs", "should expose object utils")
def test_bundle_cjs_object_exposed() -> None:
    assert min_dash.pick({"a": 1}, ["a"]) == {"a": 1}


@pytest.mark.upstream("min-dash/test/index.spec.ts", "flatten")
def test_typing_flatten_not_transposed() -> None:
    # N-A: TypeScript typing test for `flatten`, unused by the ported libraries.
    assert not hasattr(min_dash, "flatten")


@pytest.mark.upstream("min-dash/test/index.spec.ts", "debounce + throttle")
def test_typing_debounce_throttle_not_transposed() -> None:
    # N-A: TypeScript typing test for `debounce`/`throttle`, unused downstream.
    assert not hasattr(min_dash, "debounce")
    assert not hasattr(min_dash, "throttle")
