"""Seal integrity of the lot-4 render expectations (layout, R, themes).

The expectation files under ``expected/`` were authored from DESIGN R3.3
§9 and the vendored contracts (see ``spec/SPEC_PROFILE_RENDER_EXPORT_PY.md``)
and are never regenerated from library output. These tests only check the
seal: the manifest pins every byte, the derivation helper imports nothing
from ``bpmn_io``, every case is closed and authored, cross-case reuse is
verbatim and every sealed digest is internally consistent.
"""

from __future__ import annotations

from pathlib import Path

from tests.profile_render._seal import (
    HELPER,
    check_case_shapes,
    check_helper_imports,
    check_input_from,
    check_manifest,
    load_cases,
    load_helper,
)

EXPECTED = Path(__file__).resolve().parent / "expected"
EXPORT_EXPECTED = Path(__file__).resolve().parent.parent / "profile_export" / "expected"
DH = load_helper()


def test_manifest_pins_every_sealed_file() -> None:
    check_manifest(EXPECTED)


def test_manifest_detects_a_one_byte_change(tmp_path: Path) -> None:
    copy_dir = tmp_path / "expected"
    copy_dir.mkdir()
    for path in EXPECTED.iterdir():
        if path.is_file():
            (copy_dir / path.name).write_bytes(path.read_bytes())
    victim = min(copy_dir.glob("*.json"))
    data = bytearray(victim.read_bytes())
    data[-2] = ord(" ") if data[-2] != ord(" ") else ord("\t")
    victim.write_bytes(bytes(data))
    try:
        check_manifest(copy_dir)
    except AssertionError:
        return
    msg = "a one-byte change was not detected"
    raise AssertionError(msg)


def test_helper_imports_nothing_from_bpmn_io() -> None:
    assert HELPER.is_file()
    check_helper_imports()


def test_cases_are_closed_and_authored() -> None:
    check_case_shapes(EXPECTED, "render.")


def test_input_from_reuse_is_verbatim() -> None:
    assert check_input_from(EXPECTED, EXPORT_EXPECTED) > 0


def test_render_bindings_are_consistent() -> None:
    checked = 0
    for path, case in load_cases(EXPECTED):
        expected = case["expected"]
        if case["operation"] != "resolve_theme" or expected["status"] != "ok":
            continue
        render = expected["payload"]
        inputs = {**case["input"], "resolvedThemeId": render["binding"]["themeId"]}
        assert DH.render_binding(inputs, render) == render["binding"], path.name
        assert render["pages"] == case["input"]["layout"]["pages"], path.name
        checked += 1
    assert checked > 10


def test_freshness_cases_are_fresh_or_stale_as_sealed() -> None:
    checked = 0
    for path, case in load_cases(EXPECTED):
        if case["operation"] != "verify_render_data":
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
        if case["operation"] != "render_digests" or case["expected"]["status"] != "ok":
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
