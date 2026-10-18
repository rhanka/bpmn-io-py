"""Load → compile → lint wiring over the neutral profile and fixture.

The compiled path (``CompiledProfile`` from ``compile_profile``) must agree
exactly with the transport-dict path the corpus pins (``lot-1-lint``
comparator, ``validate`` operation, ``post-normalize`` stage).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.profile_lint.helpers import NAMED_TASK_DOC, make_compiled, parse

ROOT = Path(__file__).resolve().parent.parent.parent
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"


def _load_neutral() -> tuple[dict[str, Any], Any]:
    """Load the neutral profile with its pins; return (profile, loaded)."""
    from bpmn_io.profile import load_profile

    profile_bytes = (MECHANISM / "neutral-profile.json").read_bytes()
    profile = json.loads(profile_bytes.decode("utf-8"))
    assert isinstance(profile, dict)
    loaded = load_profile(
        profile_bytes,
        schema_bytes=(MECHANISM / "profile-mechanism-1.schema.json").read_bytes(),
        descriptor_pins=profile["descriptors"],  # type: ignore[arg-type]
        base_bytes=(MECHANISM / "neutral-base.json").read_bytes(),
        asset_bag={
            "neutral-metrics.json": (MECHANISM / "neutral-metrics.json").read_bytes(),
        },
        capabilities=[str(c) for c in profile["capabilities"]],
    )
    assert loaded.status == "ok", loaded
    return profile, loaded


def _compile_neutral() -> tuple[dict[str, Any], Any]:
    """Compile the neutral profile; return (profile, compiled)."""
    from bpmn_io.profile import compile_profile

    profile, loaded = _load_neutral()
    compiled = compile_profile(loaded.payload)  # type: ignore[arg-type]
    assert compiled.status == "ok", compiled
    assert compiled.payload is not None
    return profile, compiled.payload


def test_lint_is_the_wired_bridge() -> None:
    """``bpmn_io.profile.lint`` resolves to the lint bridge directly."""
    from bpmn_io.profile import lint
    from bpmn_io.profile._lint import lint as bridge

    assert lint is bridge


def test_compiled_profile_lints_like_transport_dicts() -> None:
    """Load → compile → lint matches the dict path and the pinned counts."""
    from bpmn_io.profile import lint

    profile, compiled = _compile_neutral()
    root = parse(NAMED_TASK_DOC)
    via_compiled = lint(root, compiled, phase="post-normalize", readiness_policy="accept")
    via_dicts = lint(
        root,
        make_compiled(
            profile,
            phase="post-normalize",
            readiness_policy="accept",
            profile_digest=compiled.profile_digest,
        ),
        phase="post-normalize",
        readiness_policy="accept",
    )
    assert via_compiled == via_dicts
    assert via_compiled["status"] == "ok"
    assert via_compiled["operation"] == "validate"
    assert via_compiled["payload"] == {"ok": False, "counts": {"info": 0, "warn": 0, "error": 10}}


def test_compiled_profile_accepts_registry() -> None:
    """An explicit registry works with the compiled form (extends configs)."""
    from bpmn_io.profile import lint

    _, compiled = _compile_neutral()
    root = parse(NAMED_TASK_DOC)
    plain = lint(root, compiled, phase="post-normalize", readiness_policy="accept")
    with_registry = lint(
        root, compiled, phase="post-normalize", readiness_policy="accept", registry={}
    )
    assert with_registry == plain


def test_registry_contradicts_transport_dicts() -> None:
    """A registry argument contradicts a transport dict carrying its own."""
    import pytest

    from bpmn_io.profile import lint

    profile, _ = _load_neutral()
    root = parse(NAMED_TASK_DOC)
    compiled_dicts = make_compiled(profile, phase="post-normalize", readiness_policy="accept")
    with pytest.raises(ValueError, match="contradicts"):
        lint(root, compiled_dicts, phase="post-normalize", readiness_policy="accept", registry={})
