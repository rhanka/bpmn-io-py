# Transposed from bpmn-io/bpmn-auto-layout@1.3.0 lib/di/DiUtil.js (MIT).
"""Default DI sizes and the type predicate transposed from ``lib/di/DiUtil.js``."""

from __future__ import annotations

from typing import Any, TypeAlias

__all__ = ["DEFAULT_TASK_HEIGHT", "DEFAULT_TASK_WIDTH", "get_default_size", "is_"]

#: A dynamic moddle element; the attribute shape varies by type.
Element: TypeAlias = Any

#: Default height of a task-like shape.
DEFAULT_TASK_HEIGHT = 80
#: Default width of a task-like shape.
DEFAULT_TASK_WIDTH = 100


def get_default_size(  # noqa: PLR0911 - nine-branch upstream cascade, kept literal
    element: Element,
) -> dict[str, Any]:
    """Return the default ``{width, height}`` for ``element`` (same 9-branch cascade)."""
    if is_(element, "bpmn:SubProcess"):
        return {"width": DEFAULT_TASK_WIDTH, "height": DEFAULT_TASK_HEIGHT}

    if is_(element, "bpmn:Task"):
        return {"width": DEFAULT_TASK_WIDTH, "height": DEFAULT_TASK_HEIGHT}

    if is_(element, "bpmn:Gateway"):
        return {"width": 50, "height": 50}

    if is_(element, "bpmn:Event"):
        return {"width": 36, "height": 36}

    if is_(element, "bpmn:Participant"):
        return {"width": 400, "height": 100}

    if is_(element, "bpmn:Lane"):
        return {"width": 400, "height": 100}

    if is_(element, "bpmn:DataObjectReference"):
        return {"width": 36, "height": 50}

    if is_(element, "bpmn:DataStoreReference"):
        return {"width": 50, "height": 50}

    if is_(element, "bpmn:TextAnnotation"):
        return {"width": DEFAULT_TASK_WIDTH, "height": 30}

    return {"width": DEFAULT_TASK_WIDTH, "height": DEFAULT_TASK_HEIGHT}


def is_(element: Element, type_name: str) -> bool:
    """Return whether ``element`` is of ``type_name`` (``is`` is a keyword)."""
    return bool(element.instance_of(type_name))
