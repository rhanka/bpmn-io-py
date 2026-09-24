"""Saxen security posture (Lot 3): no DTD processing, no external entities.

saxen is a non-validating parser: ``<!DOCTYPE>`` and ``<!ENTITY>`` markup
surface as ``attention`` events, references other than the five reserved names
(plus decimal/hex codes) pass through literally, and nesting is iterative.
These expectations were verified against the pinned upstream package (node)
at authoring time; they pin the posture, not upstream spec titles.
"""

from __future__ import annotations

from bpmn_io.saxen import Parser


def _record(xml: str) -> tuple[list[tuple[str, str]], object]:
    """Parse ``xml``, returning ``[(event, value)]`` and the returned error."""
    parser = Parser()
    events: list[tuple[str, str]] = []
    for name in ("openTag", "closeTag", "text", "cdata", "comment", "question", "attention"):
        parser.on(name, lambda value, *_, _name=name: events.append((_name, value)))
    parser.on("error", lambda err, _ctx: events.append(("error", str(err))))
    parser.on("warn", lambda err, _ctx: events.append(("warn", str(err))))
    return events, parser.parse(xml)


def test_xxe_external_entity_not_resolved() -> None:
    """An XXE payload is inert: doctype/entity markup is attention, ``&xxe;`` literal."""
    events, error = _record(
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><r>&xxe;</r>'
    )
    assert error is None
    assert events == [
        ("question", '<?xml version="1.0"?>'),
        ("attention", '<!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">'),
        ("warn", "non-whitespace outside of root node"),
        ("openTag", "r"),
        ("text", "&xxe;"),
        ("closeTag", "r"),
    ]


def test_entity_amplification_not_expanded() -> None:
    """Nested entity declarations never expand (no billion-laughs amplification)."""
    events, error = _record(
        '<!DOCTYPE l [<!ENTITY a "xxxxxxxxxx"><!ENTITY b "&a;&a;&a;&a;">]><l>&b;</l>'
    )
    assert error is None
    assert events == [
        ("attention", '<!DOCTYPE l [<!ENTITY a "xxxxxxxxxx">'),
        ("attention", '<!ENTITY b "&a;&a;&a;&a;">'),
        ("warn", "non-whitespace outside of root node"),
        ("openTag", "l"),
        ("text", "&b;"),
        ("closeTag", "l"),
    ]


def test_deep_nesting_iterative() -> None:
    """2000-deep nesting parses without recursion errors, both tags balanced."""
    depth = 2000
    events, error = _record("<a>" * depth + "</a>" * depth)
    assert error is None
    assert events == [("openTag", "a")] * depth + [("closeTag", "a")] * depth
