"""Ported config tests (upstream ``test/spec/config-spec.mjs``)."""

from __future__ import annotations

import pytest

from bpmn_io.lint.config.all import CONFIG as ALL_CONFIG
from bpmn_io.lint.config.correctness import CONFIG as CORRECTNESS_CONFIG
from bpmn_io.lint.rules import RULES


@pytest.mark.upstream(
    "bpmnlint/test/spec/config-spec.mjs",
    "config > all > should contain all lint rules",
)
def test_all_contains_all_rules() -> None:
    assert list(ALL_CONFIG["rules"]) == list(RULES)


@pytest.mark.upstream(
    "bpmnlint/test/spec/config-spec.mjs",
    "config > correctness > should contain relevant lint rules",
)
def test_correctness_contains_relevant_rules() -> None:
    assert list(CORRECTNESS_CONFIG["rules"]) == [
        "ad-hoc-sub-process",
        "conditional-event",
        "event-based-gateway",
        "event-sub-process-typed-start-event",
        "link-event",
        "no-duplicate-sequence-flows",
        "sub-process-blank-start-event",
        "single-blank-start-event",
    ]
