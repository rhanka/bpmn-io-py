from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_upstream_fixture_corpus_is_vendored(fixtures_dir: Path) -> None:
    bpmn_files = sorted(fixtures_dir.glob("bpmn/*.bpmn"))
    assert len(bpmn_files) >= 60, "upstream fixture corpus missing; run scripts/sync_upstream.py"
    assert (fixtures_dir / "bpmn" / "complex.bpmn").exists()
