"""Runtime narrowing helper over the BPMN model.

The generated stub ``types.pyi`` refines this module with per-type
``TypeGuard`` overloads; the runtime stays a single boolean function.
"""

from __future__ import annotations

from typing import TypeGuard

from bpmn_io.moddle.base import AnyModdleElement, ModdleElement

__all__ = ["is_a"]


def is_a(element: object, type_name: str) -> TypeGuard[ModdleElement]:
    """Return whether ``element`` is of the type called ``type_name``."""
    if isinstance(element, (ModdleElement, AnyModdleElement)):
        return element.instance_of(type_name)
    return False
