"""N-A claims for JS-packaging and performance suites (Lot 13).

The upstream CLI, bundling and compilation integration suites exercise the
Node ``bpmnlint`` executable and JS bundlers; they are adapted to the
``bpmn-io lint`` CLI tests in Lot 14 and have no Python equivalent here.
The performance suites assert timing ratios of a benchmark harness.
"""

from __future__ import annotations

import pytest


@pytest.mark.upstream("bpmnlint/test/integration/compile-spec.mjs", "should compile configuration")
def test_compile_configuration_na() -> None:
    pytest.skip(
        "JS bundle compilation integration test; compile_config itself is ported "
        "and covered by tests/lint/test_compile_config.py",
    )


@pytest.mark.upstream(
    "bpmnlint/test/performance/no-bpmndi.mjs",
    "should scale linearly with number of elements",
)
def test_performance_no_bpmndi_na() -> None:
    pytest.skip("performance scaling harness (timing ratio), no portable assertion")


@pytest.mark.upstream(
    "bpmnlint/test/performance/no-overlapping-elements.mjs",
    "should scale linearly with number of elements",
)
def test_performance_no_overlapping_na() -> None:
    pytest.skip("performance scaling harness (timing ratio), no portable assertion")
