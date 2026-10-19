"""Seal integrity of the lot-4 render expectations (layout, R, themes, seams).

The expectation files under ``expected/`` were authored from DESIGN R3.3
§9 and the vendored contracts (see ``spec/SPEC_PROFILE_RENDER_EXPORT_PY.md``)
and are never regenerated from library output. These tests only check the
seal: the manifest pins every byte, the derivation helper imports nothing
from ``bpmn_io``, every case is closed and authored, cross-case reuse is
verbatim, every sealed digest is internally consistent, coverage follows the
native pre-order and every case tree is admitted by the descriptor packages
its profile pins. The vendored JS lot-4 cases (block-B parity sync) are the
pinned JS seal bytes, re-expressed with only the section-1 decisions applied.
"""

from __future__ import annotations

from pathlib import Path

from tests.profile_render._seal import (
    HELPER,
    PARITY_PREFIXES,
    case_profiles,
    check_case_shapes,
    check_helper_imports,
    check_input_from,
    check_manifest,
    check_parity_corpus,
    check_parity_vendored,
    check_vendored,
    check_vendored_digests,
    check_vendored_files,
    load_cases,
    load_helper,
    load_vendored,
)

EXPECTED = Path(__file__).resolve().parent / "expected"
EXPORT_EXPECTED = Path(__file__).resolve().parent.parent / "profile_export" / "expected"
DH = load_helper()
VENDORED_OPERATIONS = {
    "layoutTicks",
    "layoutRegions",
    "layout",
    "compileProfile",
    "resolveTheme",
    "evaluateValue",
    "renderDigests",
    "theme-sequence",
    "checkThemeSwitch",
    "resolveLegacyTheme",
}


def test_manifest_pins_every_sealed_file() -> None:
    check_manifest(EXPECTED)


def test_manifest_detects_a_one_byte_change(tmp_path: Path) -> None:
    copy_dir = tmp_path / "expected"
    copy_dir.mkdir()
    for path in EXPECTED.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            target = copy_dir / path.relative_to(EXPECTED)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    for victim in (
        min(copy_dir.glob("*.json")),
        copy_dir / "artifacts" / "render-base.json",
        copy_dir / "vendor" / "js" / "seal.json",
    ):
        original = victim.read_bytes()
        data = bytearray(original)
        data[-2] = ord(" ") if data[-2] != ord(" ") else ord("\t")
        victim.write_bytes(bytes(data))
        try:
            check_manifest(copy_dir)
        except AssertionError:
            victim.write_bytes(original)
            continue
        msg = f"a one-byte change in {victim.name} was not detected"
        raise AssertionError(msg)


def test_helper_imports_nothing_from_bpmn_io() -> None:
    assert HELPER.is_file()
    check_helper_imports()


def test_cases_are_closed_and_authored() -> None:
    check_case_shapes(EXPECTED, "render.")


def test_input_from_reuse_is_verbatim() -> None:
    assert check_input_from(EXPECTED, EXPORT_EXPECTED) > 0


def test_extension_package_pins_match_their_bytes() -> None:
    seen = set()
    for directory in (EXPECTED, EXPORT_EXPECTED):
        for path, case in load_cases(directory):
            for profile_ref, _ in case_profiles(case):
                profile = DH.profile_from_ref(profile_ref)
                for pin in [profile["base"], *profile["descriptors"]]:
                    assert pin == DH.package_pin(pin["id"]), path.name
                    seen.add(pin["id"])
    assert {"neutral-render-base/1", "neutral-render-descriptors/1"} <= seen


def test_case_trees_are_admitted_by_the_pinned_descriptors() -> None:
    checked = 0
    for directory in (EXPECTED, EXPORT_EXPECTED):
        for path, case in load_cases(directory):
            for profile_ref, trees in case_profiles(case):
                admitted = DH.admitted_types(DH.profile_from_ref(profile_ref))
                for tree in trees:
                    missing = DH.tree_types(tree) - admitted
                    assert not missing, f"{path.name}: {sorted(missing)}"
                    checked += 1
    assert checked > 100


def test_render_bindings_are_consistent() -> None:
    checked = 0
    for path, case in load_cases(EXPECTED):
        expected = case["expected"]
        if case["operation"] != "resolveTheme" or expected["status"] != "ok":
            continue
        render = expected["payload"]
        inputs = {**case["input"], "resolvedThemeId": render["binding"]["themeId"]}
        assert DH.render_binding(inputs, render) == render["binding"], path.name
        assert render["pages"] == case["input"]["layout"]["pages"], path.name
        assert expected["report"]["entries"] == render["diagnostics"], path.name
        coverage = [entry["semanticId"] for entry in render["coverage"]]
        assert coverage == DH.native_preorder_ids(case["input"]["tree"]), path.name
        checked += 1
    assert checked > 10


def test_freshness_cases_are_fresh_or_stale_as_sealed() -> None:
    checked = 0
    for path, case in load_cases(EXPECTED):
        if case["operation"] != "verifyRenderData":
            continue
        inputs = case["input"]
        render = inputs["r"]
        recomputed = DH.render_binding(inputs, render)
        if case["expected"]["status"] == "ok":
            assert recomputed == render["binding"], path.name
            want = {"viewRevision": DH.view_revision(render["binding"])}
            assert case["expected"]["payload"] == want, path.name
        else:
            assert case["expected"]["code"] == "render-stale", path.name
            assert recomputed != render["binding"], f"{path.name}: input is not stale"
        checked += 1
    assert checked > 5


def test_digest_records_are_consistent() -> None:
    checked = 0
    for path, case in load_cases(EXPECTED):
        if case["operation"] != "renderDigests" or case["expected"]["status"] != "ok":
            continue
        record = case["input"]["record"]
        metrics = [
            {"id": m["id"], "sha256": DH.b(m["utf8"].encode("utf-8"))} for m in record["metrics"]
        ]
        got = {
            "semanticRevision": DH.semantic_revision(
                record["semanticTree"], record["profileIdentity"], record["bindings"]
            ),
            "descriptorDigest": DH.descriptor_digest(record["descriptorPins"]),
            "layoutDigest": DH.h(record["layout"]),
            "themeDigest": DH.theme_digest(record["themes"], record["themeId"]),
            "overridesDigest": DH.h(DH.normalize_overrides(record["overrides"])),
            "diStylesDigest": DH.h(DH.normalize_di_styles(record["diStyles"])),
            "metricsDigest": DH.metrics_digest(metrics),
        }
        got["viewRevision"] = DH.view_revision({**got, "themeId": record["themeId"]})
        if "payload" in record:
            got["payloadDigest"] = DH.payload_digest(record["payload"])
        assert got == case["expected"]["payload"], path.name
        checked += 1
    assert checked > 5


def test_parity_corpus_repeats_the_sealed_values() -> None:
    assert check_parity_corpus(DH, EXPECTED / "parity", EXPECTED, EXPORT_EXPECTED) == 224


def test_parity_manifest_lists_vendored_cases_and_twins() -> None:
    assert check_parity_vendored(DH, EXPECTED / "parity", EXPECTED, EXPORT_EXPECTED) == 153


def test_vendored_files_are_the_js_sealed_bytes() -> None:
    assert check_vendored_files(DH, EXPECTED, "render") == 228
    for path, want in DH.VENDORED_CONTRACTS.items():
        assert DH.b((DH.ROOT / path).read_bytes()) == want, path


def test_vendored_js_cases_match_their_sources() -> None:
    assert check_vendored(DH, EXPECTED, "render") == 107
    operations = {case["operation"] for _, case in load_vendored(EXPECTED)}
    assert operations == VENDORED_OPERATIONS


def test_vendored_digests_follow_the_helper_formulas() -> None:
    checked = sum(check_vendored_digests(DH, case) for _, case in load_vendored(EXPECTED))
    assert checked >= 20


def test_twins_are_aliases_without_files() -> None:
    own = {case["case"] for _, case in load_cases(EXPECTED)}
    vendored = {case["case"] for _, case in load_vendored(EXPECTED)}
    for case_id, alias in DH.ALIASES.items():
        assert alias["aliasOf"] in own, case_id
        assert alias["aliasOf"].startswith(PARITY_PREFIXES), case_id
        assert case_id not in vendored, case_id
        assert f"cases/{case_id}.json" not in DH.VENDORED["render"], case_id


def test_result_envelope_members_follow_the_input_envelope() -> None:
    checked = 0
    for directory in (EXPECTED, EXPORT_EXPECTED):
        for path, case in load_cases(directory):
            if case["operation"] not in ("computeLayout", "layout", "resolveTheme"):
                continue
            inputs = case["input"]
            identity = DH.profile_identity(DH.profile_from_ref(inputs["profile"]))
            revision = DH.semantic_revision(inputs["tree"], identity, inputs["bindings"])
            expected = case["expected"]
            assert expected["profileIdentity"] == identity, path.name
            assert expected["baseRevision"] == revision, path.name
            assert expected["report"]["sourceIdentity"] == identity, path.name
            assert expected["report"]["inputRevision"] == revision, path.name
            checked += 1
    assert checked > 50
