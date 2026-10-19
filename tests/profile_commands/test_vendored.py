"""Vendored JS parity cases (binding spec section 9.1, first item J1).

Every harness record under ``tests/profile_commands/expected`` with a
vendored profile executes its session through the public API and compares
the twin observation exactly (markers resolved per section 9.1). All of
them need the lot-3 plan/apply/complete/normalize functions or the lot-3
compiler fixes today; the strict xfail markers below say which, and the
integration job removes them after the merge.
"""

from __future__ import annotations

import pytest

from tests.profile_commands import vendored

_QUERY_OPS = frozenset(
    {
        "listEntries",
        "listFields",
        "checkField",
        "queryReferences",
        "copy",
    }
)

#: Records blocked at compile by the lot-3 block-A fixes.
XFAIL_BFIX = frozenset(
    {
        "lot5-surfaces-013-compile-duplicate-upstream",
        "lot5-surfaces-014-compile-missing-fallback-text",
    }
)


def _is_l3_script(record: dict[str, object]) -> bool:
    """Return whether a record carries a lot-3 transaction script."""
    roles = {entry.get("role") for entry in record["input"].get("inputArtifacts", [])}
    return "script" in roles


def _is_compile(record: dict[str, object]) -> bool:
    """Return whether a record only compiles its variant profile."""
    roles = {entry.get("role") for entry in record["input"].get("inputArtifacts", [])}
    return record.get("operation") == "compileProfile" or "compile-inputs" in roles


VENDORED_STEMS = vendored.vendored_stems()
assert VENDORED_STEMS, "no vendored records found"

VENDORED_PARAMS = []
for _stem in VENDORED_STEMS:
    if _stem in XFAIL_BFIX:
        VENDORED_PARAMS.append(
            pytest.param(_stem, marks=pytest.mark.xfail(strict=True, reason="needs lot 3 B-fix"))
        )
    else:
        VENDORED_PARAMS.append(
            pytest.param(_stem, marks=pytest.mark.xfail(strict=True, reason="needs lot 3 C/N"))
        )


@pytest.mark.parametrize("stem", VENDORED_PARAMS)
def test_vendored_case(stem: str) -> None:
    """One vendored harness record reproduces through the public API."""
    record = vendored.read_record(stem)
    if _is_compile(record):
        session = vendored.make_vsession(record)
        refusal = getattr(session, "compile_refusal", None)
        assert refusal is not None, "compileProfile records seal a refusal"
        vendored.compare_twin(refusal.to_json(), record["expected"], record)
        return
    if _is_l3_script(record):
        session = vendored.make_vsession(record)
        assert session.compiled is not None, getattr(session, "compile_refusal", None)
        assert session.bridge is not None
        activated = session.bridge.activate_business_profile(session.compiled)
        assert activated.status == "ok", activated
        actual = vendored.run_l3_script(session, record)
        vendored.compare_l3_trace(
            actual["trace"],
            record["expected"]["trace"],
            record["expected"].get("unsealed", []),
            session.step_results,
        )
        return
    session = vendored.make_vsession(record)
    assert session.bridge is not None
    assert session.compiled is not None, getattr(session, "compile_refusal", None)
    operation = record.get("operation")
    if operation == "applyCommands":
        actual = vendored.run_transaction(session, record)
    elif operation == "sequence":
        actual = vendored.run_sequence(session, record)
    elif operation in _QUERY_OPS:
        actual = vendored.run_queries(session, record)
    else:
        message = f"unknown vendored operation {operation!r}"
        raise AssertionError(message)
    vendored.compare_twin(actual, record["expected"], record)


def test_every_vendored_record_is_consumed() -> None:
    """Every vendored harness record runs in the parity test above."""
    collected = {
        _param.values[0] if hasattr(_param, "values") else _param for _param in VENDORED_PARAMS
    }
    assert sorted(collected) == VENDORED_STEMS
