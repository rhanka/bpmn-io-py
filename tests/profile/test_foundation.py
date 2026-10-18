"""Parity tests for lexical pre-parse, JCS bytes and stable identities.

Each case is driven by the vendored parity corpus; expectations come from
the corpus bytes (DESIGN text first, independent Node references second),
never from the implementation under test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "contracts" / "profile-parity-corpus" / "1"
MANIFEST = CORPUS / "manifest.json"

Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None


def _cases() -> list[tuple[str, Json]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        (rel, json.loads((ROOT / "contracts" / rel).read_text(encoding="utf-8")))
        for rel in sorted(manifest["files"])
    ]


def _by_role(entries: list[Json], role: str) -> Json:
    matches = [e for e in entries if isinstance(e, dict) and e.get("role") == role]
    assert len(matches) == 1, f"expected exactly one {role!r} artifact"
    return matches[0]


def test_lexical_group_matches_corpus() -> None:
    """Every lexical case yields its authored status through this package."""
    from bpmn_io.profile import check_lexical

    seen = 0
    for rel, case in _cases():
        assert isinstance(case, dict)
        if not str(case["caseId"]).startswith("lexical-"):
            continue
        seen += 1
        inputs = case["inputArtifacts"]
        assert isinstance(inputs, list)
        document = _by_role(inputs, "document")
        assert isinstance(document, dict)
        result = check_lexical(bytes.fromhex(str(document["hex"])))
        verdict = _by_role(case["expectedArtifacts"], "verdict")
        assert isinstance(verdict, dict)
        wanted = verdict["json"]
        assert isinstance(wanted, dict)
        if result.status == "ok":
            assert wanted == {"status": "ok"}, rel
        else:
            assert wanted == {"status": "refused", "code": result.code}, rel
        expected_status = str(case["expectedStatus"])
        if result.status == "ok":
            assert expected_status == "ok", rel
        else:
            assert expected_status == "refused:" + result.code, rel
    assert seen == 7, f"expected 7 lexical cases, saw {seen}"


def test_jcs_group_matches_corpus() -> None:
    """Every JCS case renders its authored canonical bytes through this package."""
    from bpmn_io.profile import jcs

    seen = 0
    for rel, case in _cases():
        assert isinstance(case, dict)
        if not str(case["caseId"]).startswith("jcs-"):
            continue
        inputs = case["inputArtifacts"]
        assert isinstance(inputs, list)
        expected = case["expectedArtifacts"]
        assert isinstance(expected, list)
        assert len(inputs) == len(expected), rel
        for input_entry, expected_entry in zip(inputs, expected, strict=True):
            seen += 1
            assert isinstance(input_entry, dict)
            assert isinstance(expected_entry, dict)
            assert jcs(input_entry["json"]) == expected_entry["text"], rel
        assert case["expectedStatus"] == "ok", rel
    assert seen == 4, f"expected 4 jcs value checks, saw {seen}"


def test_identity_group_matches_corpus() -> None:
    """Every stable-id case allocates its authored identifier."""
    from bpmn_io.profile import allocate_stable_id
    from bpmn_io.profile import jcs as _jcs

    seen = 0
    for rel, case in _cases():
        assert isinstance(case, dict)
        if not str(case["caseId"]).startswith("identity-"):
            continue
        allocations = _by_role(case["inputArtifacts"], "allocations")
        assert isinstance(allocations, dict)
        expected_ids = _by_role(case["expectedArtifacts"], "ids")
        assert isinstance(expected_ids, dict)
        wanted = expected_ids["json"]
        assert isinstance(wanted, list)
        entries = allocations["json"]
        assert isinstance(entries, list)
        assert len(entries) == len(wanted)
        for entry, want in zip(entries, wanted, strict=True):
            seen += 1
            assert isinstance(entry, dict)
            got = allocate_stable_id(str(entry["owner"]), str(entry["slot"]), str(entry["key"]))
            assert got == want, rel
            preimage = ["profile-mechanism/1", entry["owner"], entry["slot"], entry["key"]]
            assert got == "g_" + hashlib.sha256(_jcs(preimage).encode("utf-8")).hexdigest(), rel
        assert case["expectedStatus"] == "ok", rel
    assert seen == 4, f"expected 4 identity checks, saw {seen}"
