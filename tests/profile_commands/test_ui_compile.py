"""Focused CR-10 compile tests (binding spec section 6, first item).

Each case composes its profile delta over the fixture composition and runs
the public ``load_profile``/``compile_profile`` path. These fail until the
CR-10 UI/field rules land in ``compile_profile``.
"""

from __future__ import annotations

import pytest

from tests.profile_commands import harness
from tests.profile_commands.harness import EXPECTED

COMPILE_STEMS = sorted(
    path.stem
    for path in EXPECTED.glob("compile-*.json")
    if "expected" in path.read_text(encoding="utf-8")
)

COMPILE_PARAMS = list(COMPILE_STEMS)


def _compile_outcome(stem: str) -> dict[str, object]:
    case = harness.read_case(stem)
    setup = harness.make_setup(case)
    load_refusal = getattr(setup, "load_refusal", None)
    if load_refusal is not None:
        return load_refusal.to_json()  # type: ignore[union-attr]
    compile_refusal = getattr(setup, "compile_refusal", None)
    if compile_refusal is not None:
        return compile_refusal.to_json()  # type: ignore[union-attr]
    return {"status": "ok"}


@pytest.mark.parametrize("stem", COMPILE_PARAMS)
def test_compile_outcome_matches_seal(stem: str) -> None:
    """The sealed compile outcome reproduces through the public API."""
    case = harness.read_case(stem)
    expected = case["expected"]["compile"]
    actual = _compile_outcome(stem)
    if expected["status"] == "ok":
        assert actual["status"] == "ok", actual
        from bpmn_io.profile._ui import compiled_identity

        setup = harness.make_setup(case)
        assert setup.compiled is not None
        assert compiled_identity(setup.compiled) == case["expected"]["compiledIdentity"]
        return
    assert actual["status"] == "refused", actual
    assert actual["code"] == expected["code"], actual
    assert actual["diagnostics"] == []
