# Transposed from bpmn-io/bpmnlint-utils@83543fa lib/index.js (MIT).
"""Rule-authoring utilities transposed from ``bpmnlint-utils`` ``lib/index.js``.

``is`` maps to ``is_`` (Python keyword, same convention as the auto-layout
``DiUtil.is`` port); moddle elements answer through ``instance_of`` and plain
test doubles through a callable ``instance_of`` attribute or ``type_``.
"""

from __future__ import annotations

__all__ = ["is_", "is_any"]


def is_(node: object, type: str) -> bool:  # noqa: A002 - upstream name is `type`
    """Check whether ``node`` is of the specific bpmn ``type``."""
    type_name = type if ":" in type else "bpmn:" + type

    instance_of = getattr(node, "instance_of", None)
    if callable(instance_of):
        return bool(instance_of(type_name))
    return getattr(node, "type_", None) == type_name


def is_any(node: object, types: list[str]) -> bool:
    """Check whether ``node`` has any of the specified ``types``."""
    return any(is_(node, type_name) for type_name in types)
