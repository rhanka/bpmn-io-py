"""Sealed native case runner (binding spec sections 8.2 and 8.3).

Every native harness file with ``input.steps`` runs its setup and steps
through the public API and compares each result byte-for-byte after
``$unsealed`` substitution, plus the ``equal``/``differ`` relations and
the ``signal`` contract.
"""

from __future__ import annotations

import pytest

from tests.profile_commands import harness


def _step_stems() -> list[str]:
    """Return every native harness stem carrying ``input.steps``."""
    stems = []
    for stem in harness.native_stems():
        case = harness.read_case(stem)
        if isinstance(case.get("input"), dict) and "steps" in case["input"]:
            stems.append(stem)
    return sorted(stems)


STEP_STEMS = _step_stems()
assert STEP_STEMS, "no native step cases found"

STEP_PARAMS = list(STEP_STEMS)


def _check_setup(_stem: str, setup: harness.Setup, case: dict[str, object]) -> None:
    """Compare the sealed setup load and activation outcomes."""
    expected_setup = case["expected"]["setup"]  # type: ignore[index]
    load_actual = setup.setup_load.to_json()  # type: ignore[attr-defined]
    harness.compare_result(load_actual, expected_setup["load"])
    activate_actual = setup.setup_activate.to_json()  # type: ignore[attr-defined]
    harness.compare_result(activate_actual, expected_setup["activate"])


@pytest.mark.parametrize("stem", STEP_PARAMS)
def test_native_case(stem: str) -> None:
    """One sealed native case reproduces through the public API."""
    case = harness.read_case(stem)
    setup = harness.make_setup(case)
    assert setup.compiled is not None, getattr(setup, "compile_refusal", None)
    assert setup.bridge is not None
    if "setup" in case["expected"]:
        _check_setup(stem, setup, case)
    expected_steps = case["expected"]["steps"]  # type: ignore[index]
    input_steps = case["input"]["steps"]  # type: ignore[index]
    assert len(input_steps) == len(expected_steps), stem
    for _index, (step, want) in enumerate(zip(input_steps, expected_steps, strict=True)):
        actual = harness.run_step(setup, step)
        signal_spec = want.get("signal")
        if signal_spec is not None:
            harness.check_signal(actual, signal_spec)
            actual = {k: v for k, v in actual.items() if k != "__signal__"}
        harness.compare_result(actual, want["result"])
        harness.check_relational(setup, actual, want)


def test_every_native_step_file_is_consumed() -> None:
    """Every native step file runs in the case runner above."""
    collected = {
        _param.values[0] if hasattr(_param, "values") else _param for _param in STEP_PARAMS
    }
    assert sorted(collected) == STEP_STEMS
