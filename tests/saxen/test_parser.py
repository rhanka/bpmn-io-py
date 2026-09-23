"""Ported saxen parser cases (Lot 3).

Claims the single ``saxen/test/parser.js`` title: parser state resets between
``parse`` runs.
"""

from __future__ import annotations

import pytest

from bpmn_io.saxen import Parser


@pytest.mark.upstream("saxen/test/parser.js", "should reset state between parses")
def test_reset_state_between_parses() -> None:
    parser = Parser()
    open_tags: list[object] = []
    parser.on("openTag", open_tags.append)
    parser.parse("<a/>")
    parser.parse("<b/>")
    assert open_tags == ["a", "b"]
