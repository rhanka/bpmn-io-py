"""Results ordering regressions (finding #16).

Expectations come from DESIGN R3.3 \u00a710.1: stage order is the fixed
pipeline order (load, import, complete, pre-normalize, normalize,
post-normalize, layout, post-layout, release, render, export), never
alphabetical; within a stage entries sort by ruleId, source
domain/pointer, targetId, code, pageId, occurrenceKey and canonical
before/after in UTF-16 code-unit order with absent before present; exact
duplicate tuples coalesce.
"""

from __future__ import annotations


def _entry(stage: str, **overrides: object) -> object:
    from bpmn_io.profile._results import Coordinate, ReportEntry

    source = Coordinate(
        domain="tree",
        pointer=overrides.pop("pointer", "/a"),
        target_id=overrides.pop("target", None),
        provenance="exact",
    )
    result = Coordinate(
        domain="tree",
        pointer=None,
        target_id=overrides.pop("result_target", None),
        provenance="exact",
    )
    fields: dict[str, object] = {
        "code": "c",
        "severity": "error",
        "classification": "integrity",
        "stage": stage,
        "rule_id": "b-rule",
        "message_key": "m",
        "disposition": "observed",
        "source": source,
        "result": result,
        "before_present": False,
        "after_present": False,
        "before": None,
        "after": None,
        "page_id": None,
        "occurrence_key": None,
    }
    renamed = {"page": "page_id", "key": "occurrence_key"}
    for name, value in overrides.items():
        fields[renamed.get(name, name)] = value
    return ReportEntry(**fields)  # type: ignore[arg-type]


def _stages(entries: list[object]) -> list[str]:
    from bpmn_io.profile import sort_report_entries

    return [entry.stage for entry in sort_report_entries(entries)]  # type: ignore[union-attr]


def test_stage_order_follows_pipeline_not_alphabet() -> None:
    """Stages sort in \u00a710.1 pipeline order even when alphabetical differs."""
    scrambled = ["release", "export", "import", "load", "normalize", "complete", "render"]
    assert _stages([_entry(stage) for stage in scrambled]) == [
        "load",
        "import",
        "complete",
        "normalize",
        "release",
        "render",
        "export",
    ]


def test_full_stage_order() -> None:
    """All eleven pipeline stages land in their \u00a710.1 slots."""
    scrambled = [
        "export",
        "render",
        "release",
        "post-layout",
        "layout",
        "post-normalize",
        "normalize",
        "pre-normalize",
        "complete",
        "import",
        "load",
    ]
    assert _stages([_entry(stage) for stage in scrambled]) == [
        "load",
        "import",
        "complete",
        "pre-normalize",
        "normalize",
        "post-normalize",
        "layout",
        "post-layout",
        "release",
        "render",
        "export",
    ]


def test_utf16_orders_astral_before_bmp_private_use() -> None:
    """UTF-16 code-unit order (U+10000 before U+E000), not code points."""
    from bpmn_io.profile import sort_report_entries

    astral = _entry("complete", rule_id="\U00010000")
    private = _entry("complete", rule_id="\ue000")
    ranked = sort_report_entries([private, astral])
    assert [entry.rule_id for entry in ranked] == ["\U00010000", "\ue000"]  # type: ignore[union-attr]


def test_absent_sorts_before_present() -> None:
    """Absent page, key, target and values precede present ones."""
    from bpmn_io.profile import sort_report_entries

    present_page = _entry("complete", page="p")
    absent_page = _entry("complete", page=None)
    ranked = sort_report_entries([present_page, absent_page])
    assert ranked[0] is absent_page
    present_target = _entry("complete", target="t")
    absent_target = _entry("complete", target=None)
    ranked = sort_report_entries([present_target, absent_target])
    assert ranked[0] is absent_target
    present_before = _entry("complete", before={"a": 1}, before_present=True)
    absent_before = _entry("complete", before_present=False)
    ranked = sort_report_entries([present_before, absent_before])
    assert ranked[0] is absent_before


def test_exact_duplicates_coalesce() -> None:
    """Two wire-identical entries collapse to one."""
    from bpmn_io.profile import make_report

    first = _entry("complete")
    second = _entry("complete")
    report = make_report("complete", [first, second])  # type: ignore[arg-type]
    assert len(report.to_json()["entries"]) == 1


def test_near_duplicates_survive_on_result_target() -> None:
    """Entries differing only by result target both survive, ordered."""
    from bpmn_io.profile import sort_report_entries

    second = _entry("complete", result_target="b")
    first = _entry("complete", result_target="a")
    ranked = sort_report_entries([second, first])
    assert len(ranked) == 2
    assert ranked[0] is first
