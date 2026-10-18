"""Seal integrity of the lot-4 export expectations (map, serialize, prepare).

The expectation files under ``expected/`` were authored from DESIGN R3.3
§10.1/§10.2 and the vendored contracts (see
``spec/SPEC_PROFILE_RENDER_EXPORT_PY.md``) and are never regenerated from
library output. These tests only check the seal: the manifest pins every
byte, the shared derivation helper imports nothing from ``bpmn_io``, every
case is closed and authored, and every sealed digest of a prepared artifact
is internally consistent.
"""

from __future__ import annotations

from pathlib import Path

from tests.profile_render._seal import (
    check_case_shapes,
    check_helper_imports,
    check_input_from,
    check_manifest,
    load_cases,
    load_helper,
)

EXPECTED = Path(__file__).resolve().parent / "expected"
RENDER_EXPECTED = Path(__file__).resolve().parent.parent / "profile_render" / "expected"
DH = load_helper()
EMPTY_BAGS = {
    "overrides": {"semantic": [], "occurrence": []},
    "diStyles": {"native": [], "bioc": []},
}


def test_manifest_pins_every_sealed_file() -> None:
    check_manifest(EXPECTED)


def test_shared_helper_imports_nothing_from_bpmn_io() -> None:
    check_helper_imports()


def test_cases_are_closed_and_authored() -> None:
    check_case_shapes(EXPECTED, "export.")


def test_cross_tree_reuse_is_verbatim() -> None:
    check_input_from(RENDER_EXPECTED, EXPECTED)


def _map_steps(case: dict) -> list[tuple[dict, dict]]:
    if case["operation"] == "map_export":
        return [(case["input"], case["expected"])]
    if case["operation"] == "map_export_sequence":
        return list(zip(case["input"]["steps"], case["expected"]["steps"], strict=True))
    return []


def test_prepared_artifacts_are_consistent() -> None:
    checked = 0
    for path, case in load_cases(EXPECTED):
        for inputs, expected in _map_steps(case):
            render = inputs["r"]
            if expected.get("code") != "render-stale":
                fresh = DH.render_binding(
                    {**inputs, **EMPTY_BAGS, "themeId": render["binding"]["themeId"]}, render
                )
                assert fresh == render["binding"], f"{path.name}: input R is not fresh"
            if expected["status"] != "ok":
                continue
            prepared = expected["payload"]
            assert prepared["renderBinding"] == render["binding"], path.name
            assert prepared["viewRevision"] == DH.view_revision(render["binding"]), path.name
            assert prepared["report"]["artifacts"][0]["digest"] == DH.h(prepared["ir"]), path.name
            assert prepared["idMap"] == prepared["report"]["idMap"], path.name
            assert expected["report"] == prepared["report"], path.name
            checked += 1
    assert checked > 10


def test_digest_policy_ids_follow_the_formula() -> None:
    case = next(c for _, c in load_cases(EXPECTED) if c["case"] == "export.map.digest-policy")
    ids = [record["id"] for record in case["expected"]["payload"]["ir"]]
    keys = [
        ("P1", "", "page"),
        ("P1", "s-task-a", "node"),
        ("P1", "s-task-b", "node"),
        ("P1", "e-flow", "edge"),
    ]
    assert ids == [DH.digest_id(*key) for key in keys]
