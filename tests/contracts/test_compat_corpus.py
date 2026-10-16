"""Lot 21c: compatibility-matrix expectations checked against pinned artifacts.

Every ``compat-`` case carries the conductor vector input verbatim plus the
verbatim ``expectedR33`` verdict/outcome (copied, never computed, from the
vendored ``r33-matrix-vectors.public.json``). This test checks each expected verdict
against Ajv 2020 (strict, design validator options) over the pinned
``compatibility-verdict.schema.json``, checks every refusal code against the
pinned ``compatibility-codes.json`` registry, and checks ``expectedStatus``
consistency (``ok`` / ``refused:<code>`` / bare ``refused`` for exact-but-
invalid envelopes, which DESIGN assigns no code). Agreement of the verdicts
themselves with DESIGN section 3.3 R3.3 (P1, P2, row order) was reviewed by
hand against every vector and is recorded in the plan Feedback Loop; any
disagreement would be an ``open`` entry there, never a corrected expectation.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tests.contracts.test_corpus_references import (
    _ajv,
    _artifact_path,
    _by_role,
    _cases,
)

ROOT = Path(__file__).resolve().parent.parent.parent
Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None
VECTORS = {
    "path": "profile-mechanism/1/r33-matrix-vectors.public.json",
    "sha256": json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))["files"][
        "contracts/profile-mechanism/1/r33-matrix-vectors.public.json"
    ],
}
VERDICT_SCHEMA = {
    "path": "profile-mechanism/1/compatibility-verdict.schema.json",
    "sha256": json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))["files"][
        "contracts/profile-mechanism/1/compatibility-verdict.schema.json"
    ],
}
CODES = {
    "path": "profile-mechanism/1/compatibility-codes.json",
    "sha256": json.loads((ROOT / "CONTRACTS.lock").read_text(encoding="utf-8"))["files"][
        "contracts/profile-mechanism/1/compatibility-codes.json"
    ],
}


def _registry_codes() -> list[str]:
    codes = json.loads(_artifact_path(CODES).read_text(encoding="utf-8"))
    return [entry["code"] for entry in codes["codes"]]


def _vectors_by_case_id() -> dict[str, Json]:
    vectors = json.loads(_artifact_path(VECTORS).read_text(encoding="utf-8"))
    by_id: dict[str, Json] = {}
    for entry in [*vectors["existing"], *vectors["added"]]:
        assert isinstance(entry, dict)
        by_id[str(entry["caseId"])] = entry
    return by_id


@pytest.mark.oracle
def test_compat_group_matches_pinned_verdict_artifacts() -> None:
    """Ajv validates every compat verdict; every code is registered."""
    schema = json.loads(_artifact_path(VERDICT_SCHEMA).read_text(encoding="utf-8"))
    registered = _registry_codes()
    assert len(registered) == 20
    seen = 0
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        for rel, case in _cases():
            assert isinstance(case, dict)
            if not Path(rel).name.startswith("compat-"):
                continue
            seen += 1
            assert case["operation"] == "check_compatibility", rel
            verdict = _by_role(case["expectedArtifacts"], "verdict")
            assert isinstance(verdict, dict)
            expected = verdict["json"]
            assert isinstance(expected, dict)
            result = _ajv(tmp, schema, expected, [])
            assert isinstance(result, dict)
            assert result.get("ok") is True, f"{rel}: verdict fails pinned schema"
            status = case["expectedStatus"]
            if expected.get("status") == "ok":
                assert status == "ok", rel
            else:
                code = expected.get("code")
                if code is None:
                    assert status == "refused", rel
                else:
                    assert code in registered, f"{rel}: unregistered code"
                    assert status == "refused:" + code, rel
            outcome = _by_role(case["expectedArtifacts"], "outcome")
            assert isinstance(outcome, dict)
    assert seen == 151, f"expected 151 compat cases, saw {seen}"


def test_compat_cases_match_vendored_vectors() -> None:
    """Every case carries its vector's input and outcome verbatim by caseId."""
    by_id = _vectors_by_case_id()
    assert len(by_id) == 151
    seen = 0
    for rel, case in _cases():
        assert isinstance(case, dict)
        if not Path(rel).name.startswith("compat-"):
            continue
        seen += 1
        case_id = str(case["caseId"])
        assert case_id in by_id, f"{rel}: no vendored vector"
        vector = by_id[case_id]
        assert isinstance(vector, dict)
        inputs = case["inputArtifacts"]
        assert isinstance(inputs, list)
        assert _by_role(inputs, "matrixInput")["json"] == vector["input"], rel
        expected = vector.get("expectedR33", vector.get("expected"))
        assert isinstance(expected, dict)
        assert _by_role(case["expectedArtifacts"], "outcome")["json"] == expected["output"], rel
    assert seen == 151, f"expected 151 compat cases, saw {seen}"
