"""Block-B mirror J5: preparation refusals merge buckets into canonical entries."""

from __future__ import annotations

import copy
import json
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent / "expected"


def _repairable_input() -> dict:
    case = json.loads((EXPORT_DIR / "export.prepare.repairable-pre-normalize.json").read_text())
    return copy.deepcopy(case["input"])


def test_j5_layout_refusal_keeps_earlier_stage_entries() -> None:
    """A layout refusal keeps the complete/normalize/lint entries in order."""
    from bpmn_io.profile._prepare import prepare_export
    from bpmn_io.profile._results import sort_report_entries
    from tests.profile_export.test_prepare import _compiled_envelope, _options

    case_input = _repairable_input()
    compiled, envelope = _compiled_envelope(case_input)
    # No importedDi reaches the layout stage: it refuses after C/N and lint ran.
    options = _options(case_input)
    options.pop("importedDi", None)
    result = prepare_export(compiled, envelope, options)
    assert result.status == "refused"
    assert result.code == "operation-error"  # type: ignore[union-attr]
    entries = list(result.report.entries)  # type: ignore[union-attr]
    assert entries == sort_report_entries(entries)
    assert len({json.dumps(e.to_json(), sort_keys=True) for e in entries}) == len(entries)
    stages = [(e.stage, e.rule_id) for e in entries]
    assert ("normalize", "assoc-direction-fix") in stages
    assert any(stage == "pre-normalize" for stage, _ in stages)
