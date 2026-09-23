"""Differential saxen tests: Python port vs the pinned Node package (Lot 3).

``op=saxen`` (``tests/oracle/run.mjs``) records the full event stream — all eight
events with handler-shaped arguments, contexts and the returned error — for a
batch of inputs; the port mirrors the recording and every stream must match
exactly. The corpus is the vendored upstream fixtures (89 ``bpmn-moddle``
``.bpmn`` files including ``error/`` and ``.part.`` cases, ``moddle-xml``
``UML.xmi``, garbage-in ``no-xml.txt``/``binary.png``), each parsed raw and with
a BPMN namespace map, plus chunked parses of a few inputs. ``decode_entities``
is covered by a direct ``call`` table on the ``decode`` export.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from bpmn_io.saxen import Parser, decode_entities

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.oracle

UPSTREAM = Path(__file__).parent.parent / "upstream"

NS_MAP = {
    "http://www.omg.org/spec/BPMN/20100524/MODEL": "bpmn",
    "http://www.omg.org/spec/BPMN/20100524/DI": "bpmndi",
    "http://www.omg.org/spec/DD/20100524/DI": "di",
    "http://www.omg.org/spec/DD/20100524/DC": "dc",
    "http://www.w3.org/2001/XMLSchema-instance": "xsi",
}


def _collect_py(
    xml: str | None, chunks: list[str] | None = None, ns: dict[str, str] | None = None
) -> dict[str, Any]:
    """Record the port event stream with the same shapes as the oracle driver."""
    parser = Parser()
    if ns is not None:
        parser.ns(dict(ns))
    events: list[list[Any]] = []
    parser.on(
        "openTag",
        lambda name, get_attrs, _decode, tag_end, ctx: events.append(
            ["openTag", name, get_attrs(), tag_end, ctx()]
        ),
    )
    parser.on(
        "closeTag",
        lambda name, _decode, tag_start, ctx: events.append(["closeTag", name, tag_start, ctx()]),
    )
    parser.on(
        "text",
        lambda chars, _decode, ctx: events.append(["text", chars, ctx()]),
    )
    parser.on(
        "comment",
        lambda value, _decode, ctx: events.append(["comment", value, ctx()]),
    )
    parser.on(
        "attention",
        lambda value, _decode, ctx: events.append(["attention", value, ctx()]),
    )
    parser.on("cdata", lambda data, ctx: events.append(["cdata", data, ctx()]))
    parser.on("question", lambda value, ctx: events.append(["question", value, ctx()]))
    parser.on("error", lambda err, ctx: events.append(["error", str(err), ctx()]))
    parser.on("warn", lambda err, ctx: events.append(["warn", str(err), ctx()]))
    if chunks is None:
        assert xml is not None
        returned = parser.parse(xml)
    else:
        returned = None
        for chunk in chunks:
            returned = parser.write(chunk)
        returned = parser.end()
    return {"events": events, "error": None if returned is None else str(returned)}


def _fixture_inputs() -> tuple[list[str], list[dict[str, Any]]]:
    """Build (ids, oracle inputs) for the whole fixture corpus."""
    ids: list[str] = []
    inputs: list[dict[str, Any]] = []
    paths = sorted((UPSTREAM / "bpmn-moddle" / "test" / "fixtures").rglob("*.bpmn"))
    paths.append(UPSTREAM / "moddle-xml" / "test" / "fixtures" / "xml" / "UML.xmi")
    paths.append(UPSTREAM / "moddle-xml" / "test" / "fixtures" / "error" / "no-xml.txt")
    paths.append(UPSTREAM / "moddle-xml" / "test" / "fixtures" / "error" / "binary.png")
    for path in paths:
        xml = path.read_text(encoding="utf-8", errors="replace")
        for mode, ns in (("raw", None), ("ns", NS_MAP)):
            ids.append(f"{path.parent.name}/{path.name}#{mode}")
            payload: dict[str, Any] = {"xml": xml}
            if ns is not None:
                payload["options"] = {"ns": ns}
            inputs.append(payload)
    edge = "<r><!--c--><![CDATA[x]]><?q?><!D a='1' b=\"2\">t</r>"
    for label, xml in (("edge", edge), ("head", paths[0].read_text(encoding="utf-8"))):
        cuts = sorted({len(xml) // 3, len(xml) // 2, 2 * len(xml) // 3})
        chunks = []
        prev = 0
        for cut in cuts:
            chunks.append(xml[prev:cut])
            prev = cut
        chunks.append(xml[prev:])
        ids.append(f"chunked:{label}")
        inputs.append({"xml": None, "chunks": chunks})
    return ids, inputs


def test_decode_table(oracle_call: Callable[[dict[str, object]], object]) -> None:
    rows = [
        "&amp;&lt;&gt;&quot;&apos;",
        "&AMP;&LT;&GT;&QUOT;&APOS;",
        "&#65;&#x41;&#X41;&#x4a;",
        "&Quot;&unknown;&nbsp;",
        "&#١٢٣;&#x;",
        "a&b",
        "&",
        "&#;",
        "plain",
    ]
    for row in rows:
        expected = oracle_call({"op": "call", "package": "saxen", "path": "decode", "args": [row]})
        assert decode_entities(row) == expected, row


def test_event_stream_corpus(oracle_call: Callable[[dict[str, object]], object]) -> None:
    ids, inputs = _fixture_inputs()
    # One argv per batch: the full corpus exceeds the OS argument size limit.
    for start in range(0, len(inputs), 10):
        batch_ids = ids[start : start + 10]
        batch = inputs[start : start + 10]
        results = oracle_call({"op": "saxen", "inputs": batch})
        assert isinstance(results, list)
        assert len(results) == len(batch)
        for fid, payload, expected in zip(batch_ids, batch, results, strict=True):
            ns = (payload.get("options") or {}).get("ns")
            got = _collect_py(payload.get("xml"), payload.get("chunks"), ns)
            assert got == expected, fid
