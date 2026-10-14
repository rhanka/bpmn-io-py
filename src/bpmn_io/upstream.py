"""Upstream bpmn.io versions this release transposes (kept in sync with ``UPSTREAM.toml``)."""

from __future__ import annotations

from typing import Final

#: npm package name -> exact upstream version whose algorithms and tests this package ports.
UPSTREAM_VERSIONS: Final[dict[str, str]] = {
    "saxen": "11.2.0",
    "min-dash": "5.1.0",
    "moddle": "8.2.1",
    "moddle-xml": "12.3.1",
    "bpmn-moddle": "10.3.1",
    "bpmn-in-color-moddle": "0.2.0",
    "bpmn-auto-layout": "1.3.0",
    "bpmnlint": "11.15.0",
    "bpmnlint-utils": "1.1.1",
    "@bpmn-io/moddle-utils": "0.3.0",
}
