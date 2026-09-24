"""Ported bpmn-auto-layout snapshot cases (Lot 8).

Transcribes ``bpmn-auto-layout/test/LayoutSpec.js``: one case per
``test/fixtures/*.bpmn`` (47 fixtures, sorted by file name, as upstream
``readdirSync`` enumerates them). Each case runs ``layout_process`` on the
fixture and asserts byte-exact equality with the same-named file in
``test/snapshots/`` (upstream ``assert.strictEqual``). Fixtures and snapshots
stay in place -- no copies. The ``UPDATE_SNAPSHOTS`` regeneration mode and
the browser ``output/index.html`` report harness are not ported
(harness-only, no assertions). ``ONLY*``/``SKIP*`` file prefixes keep their
upstream ``iit`` meaning (no such files exist today).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bpmn_io.auto_layout import layout_process

FIXTURES = (
    Path(__file__).resolve().parent.parent / "upstream" / "bpmn-auto-layout" / "test" / "fixtures"
)
SNAPSHOTS = (
    Path(__file__).resolve().parent.parent / "upstream" / "bpmn-auto-layout" / "test" / "snapshots"
)

#: Sorted fixture names (mirrors the upstream enumeration).
NAMES = sorted(path.name for path in FIXTURES.glob("*.bpmn"))

#: Upstream ``iit``: when any ``ONLY*`` fixture exists, only those run.
_ONLY_ACTIVE = any(name.startswith("ONLY") for name in NAMES)


@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout ad-hoc-sub-process.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout boundary-event.back-loop.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout boundary-event.forward-modeling.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout boundary-event.multiple.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout boundary-event.self-loop.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout boundary-event.simple.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout collaboration-message-flows.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout data-object-and-store-reference.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout event-sub-process.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout example.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout expanded.01-hour.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout expanded.03-hour.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout expanded.04-hour.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout expanded.06-hour.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout expanded.09-hour.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout expanded.self-loop.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout gateway.future-incoming.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout gateway.multiple-complex.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout gateway.multiple-with-tasks.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout gateway.multiple.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout gateway.parallel.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout process.independent-flows.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout process.joining-flows.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.disconnected-loop-boundary.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.disconnected-loop.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.empty-definitions.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.empty-process.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.gateway-with-loop-back.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.happy-path.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.implicit-start.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.issue-100.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.issue-131.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.issue-32.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.issue-79-1.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.issue-79-2.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.issue-79-3.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.link-events.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.multiple-event-starts.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.multiple-start-events.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.multiple-task-gateways-columns.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.no-outgoing.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout scenario.simple.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout sub-process.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout sub-process.empty.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout sub-process.nested.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout text-annotation.bpmn",
)
@pytest.mark.upstream(
    "bpmn-auto-layout/test/LayoutSpec.js",
    "should layout transaction.bpmn",
)
@pytest.mark.parametrize("name", NAMES)
def test_layout_snapshot(name: str) -> None:
    """Lay out ``name`` and byte-compare it with its committed snapshot."""
    if name.startswith("SKIP"):
        pytest.skip(f"upstream SKIP* fixture: {name}")
    if _ONLY_ACTIVE and not name.startswith("ONLY"):
        pytest.skip(f"upstream ONLY* fixture present, skipping: {name}")
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    expected = (SNAPSHOTS / name).read_text(encoding="utf-8")
    assert layout_process(xml) == expected
