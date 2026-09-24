"""Access to the vendored moddle descriptors (JSON meta-model packages).

The descriptor files are copied verbatim from upstream ``bpmn-moddle`` at the version pinned in
``UPSTREAM.toml``; ``UPSTREAM.lock`` holds their sha256 digests. They are data, never edited here.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, Final

#: Descriptor package prefix -> resource path relative to ``bpmn_io/resources``.
DESCRIPTOR_NAMES: Final[dict[str, str]] = {
    "bpmn": "bpmn/bpmn.json",
    "bpmndi": "bpmn/bpmndi.json",
    "dc": "bpmn/dc.json",
    "di": "bpmn/di.json",
    "bioc": "bpmn-io/bioc.json",
    "color": "color/bpmn-in-color.json",
}


def load_descriptor(name: str) -> dict[str, Any]:
    """Return the parsed JSON descriptor for ``name`` (one of :data:`DESCRIPTOR_NAMES`)."""
    try:
        relative = DESCRIPTOR_NAMES[name]
    except KeyError:
        msg = f"unknown descriptor {name!r}; expected one of {sorted(DESCRIPTOR_NAMES)}"
        raise KeyError(msg) from None
    text = files("bpmn_io.resources").joinpath(relative).read_text(encoding="utf-8")
    descriptor: dict[str, Any] = json.loads(text)
    return descriptor
