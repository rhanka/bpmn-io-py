"""Seal integrity of the lot-4 export expectations (map, serialize, prepare, legacy).

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


def test_manifest_detects_a_one_byte_change(tmp_path: Path) -> None:
    copy_dir = tmp_path / "expected"
    copy_dir.mkdir()
    for path in EXPECTED.iterdir():
        if path.is_file():
            (copy_dir / path.name).write_bytes(path.read_bytes())
    victim = max(copy_dir.glob("*.json"))
    data = bytearray(victim.read_bytes())
    data[-2] = ord(" ") if data[-2] != ord(" ") else ord("\t")
    victim.write_bytes(bytes(data))
    try:
        check_manifest(copy_dir)
    except AssertionError:
        return
    msg = "a one-byte change was not detected"
    raise AssertionError(msg)


def test_shared_helper_imports_nothing_from_bpmn_io() -> None:
    check_helper_imports()


def test_cases_are_closed_and_authored() -> None:
    check_case_shapes(EXPECTED, "export.")


def test_cross_tree_reuse_is_verbatim() -> None:
    check_input_from(RENDER_EXPECTED, EXPECTED)


def _map_steps(case: dict) -> list[tuple[dict, dict]]:
    if case["operation"] == "mapExport":
        return [(case["input"], case["expected"])]
    if case["operation"] == "mapExportSequence":
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
                coverage = [entry["semanticId"] for entry in render["coverage"]]
                assert coverage == DH.native_preorder_ids(inputs["tree"]), path.name
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


def test_prepare_results_are_consistent() -> None:
    checked = 0
    for path, case in load_cases(EXPECTED):
        if case["operation"] != "prepareExport":
            continue
        expected = case["expected"]
        assert expected["inputsUnchanged"] is True, path.name
        if expected["status"] == "ok":
            prepared = expected["payload"]
            assert prepared["report"] == expected["report"], path.name
            assert prepared["viewRevision"] == DH.view_revision(prepared["renderBinding"]), (
                path.name
            )
            assert prepared["semanticRevision"] == prepared["renderBinding"]["semanticRevision"], (
                path.name
            )
            assert prepared["report"]["artifacts"][0]["digest"] == DH.h(prepared["ir"]), path.name
            indexes = prepared["report"]["artifacts"][0]["entryIndexes"]
            assert indexes == list(range(len(prepared["report"]["entries"]))), path.name
        checked += 1
    assert checked >= 9


def test_serialize_expectations_follow_the_drawio_projection() -> None:
    checked = 0
    for path, case in load_cases(EXPECTED):
        if case["operation"] != "serializePrepared" or case["expected"]["status"] != "ok":
            continue
        prepared = case["input"]["prepared"]
        structural = case["expected"]["structural"]
        pages = [record for record in prepared["ir"] if record["kind"] == "page"]
        assert [d["id"] for d in structural["diagrams"]] == [p["id"] for p in pages], path.name
        assert [d["name"] for d in structural["diagrams"]] == [p["name"] for p in pages], path.name
        cells = [c["id"] for d in structural["diagrams"] for c in d["cells"]]
        drawn = [r["id"] for r in prepared["ir"] if r["kind"] in ("node", "edge", "label")]
        assert sorted(cells) == sorted(drawn), path.name
        assert case["expected"]["payload"]["idMap"] == prepared["idMap"], path.name
        checked += 1
    assert checked >= 3


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
