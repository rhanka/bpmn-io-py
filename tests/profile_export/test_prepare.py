"""Unit tests for the export preparation pipeline (spec §12).

The full pipeline needs lot-3 complete/normalize (marked); the options and
compatibility stages run on block-A modules and pass now.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.profile_render._lot4_harness import (
    build_case_envelope,
    compile_profile_doc,
    profile_from_ref,
)

EXPORT_DIR = Path(__file__).resolve().parent / "expected"


def _success_input() -> dict:
    """Load the sealed prepare success input."""
    case = json.loads((EXPORT_DIR / "export.prepare.success.json").read_text(encoding="utf-8"))
    return copy.deepcopy(case["input"])


def _compiled_envelope(case_input: dict) -> tuple[object, object]:
    """Compile the case profile and build its envelope."""
    profile = profile_from_ref(case_input["profile"])
    compiled_result, _, _ = compile_profile_doc(copy.deepcopy(profile), None)
    assert compiled_result.status == "ok", compiled_result.to_json()
    compiled = compiled_result.payload
    envelope = build_case_envelope(
        compiled,
        profile,
        copy.deepcopy(case_input["tree"]),
        copy.deepcopy(case_input.get("bindings", [])),
        case_input.get("envelopeIdentity"),
    )
    return compiled, envelope


def _options(case_input: dict, **overrides: object) -> dict:
    """Build pipeline options from a case (diagrams stay unmapped here)."""
    options = copy.deepcopy(case_input["options"])
    options.pop("diagrams", None)
    options.update(overrides)
    return options


def test_describe_prepare_stages_lists_twelve_names() -> None:
    from bpmn_io.profile._prepare import PREPARE_STAGES, describe_prepare_stages

    assert describe_prepare_stages() == PREPARE_STAGES
    assert list(PREPARE_STAGES) == [
        "options",
        "compatibility",
        "graph",
        "complete",
        "pre-normalize",
        "normalize",
        "post-normalize",
        "layout",
        "post-layout",
        "release",
        "render",
        "map",
    ]


def test_options_unknown_member_refuses_operation_error() -> None:
    from bpmn_io.profile._prepare import run_pipeline

    case_input = _success_input()
    compiled, envelope = _compiled_envelope(case_input)
    options = _options(case_input, extraMember=True)
    trace: list[str] = []
    result = run_pipeline(compiled, envelope, options, observer=trace.append)
    assert result.status == "refused"
    assert result.code == "operation-error"  # type: ignore[union-attr]
    assert trace == ["options"]


def test_options_missing_format_refuses_operation_error() -> None:
    from bpmn_io.profile._prepare import run_pipeline

    case_input = _success_input()
    compiled, envelope = _compiled_envelope(case_input)
    options = _options(case_input)
    del options["format"]
    result = run_pipeline(compiled, envelope, options)
    assert result.status == "refused"
    assert result.code == "operation-error"  # type: ignore[union-attr]


def test_options_undeclared_format_refuses_unsupported() -> None:
    from bpmn_io.profile._prepare import run_pipeline

    case_input = _success_input()
    compiled, envelope = _compiled_envelope(case_input)
    result = run_pipeline(compiled, envelope, _options(case_input, format="sparx"))
    assert result.status == "refused"
    assert result.code == "export-format-unsupported"  # type: ignore[union-attr]


def test_options_unknown_theme_refuses_stale() -> None:
    from bpmn_io.profile._prepare import run_pipeline

    case_input = _success_input()
    compiled, envelope = _compiled_envelope(case_input)
    result = run_pipeline(compiled, envelope, _options(case_input, themeId="standard"))
    assert result.status == "refused"
    assert result.code == "render-stale"  # type: ignore[union-attr]


def test_prepare_export_without_observer_refuses_options_code() -> None:
    from bpmn_io.profile._prepare import prepare_export

    case_input = _success_input()
    compiled, envelope = _compiled_envelope(case_input)
    result = prepare_export(compiled, envelope, _options(case_input, themeId="standard"))
    assert result.status == "refused"
    assert result.code == "render-stale"  # type: ignore[union-attr]


@pytest.mark.xfail(strict=True, reason="needs lot 3 C/N: graph stage has no context")
def test_full_pipeline_runs_twelve_stages() -> None:
    from bpmn_io.profile._prepare import run_pipeline

    case_input = _success_input()
    compiled, envelope = _compiled_envelope(case_input)
    options = _options(case_input)
    options["importedDi"] = {"descriptorDigest": "x", "diagrams": [], "sha256": "y"}
    trace: list[str] = []
    result = run_pipeline(compiled, envelope, options, observer=trace.append)
    assert result.status == "ok", result.to_json()  # type: ignore[union-attr]
