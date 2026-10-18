"""Stable identity ``stable-id/1`` (DESIGN R3.3 §3.2)."""

from __future__ import annotations

from typing import Any

from bpmn_io.profile._c14n import digest

__all__ = ["STABLE_ID_PREFIX", "allocate_stable_id"]

#: Allocated identifier prefix.
STABLE_ID_PREFIX = "g_"

_Json = dict[str, Any] | list[Any] | str | int | float | bool | None


def allocate_stable_id(owner_id: str, slot: str, stable_key: str) -> str:
    """Allocate one deterministic identifier for an owner/slot/key triple.

    Computes ``g_`` plus the lowercase hex SHA-256 over the UTF-8 JCS bytes
    of ``["profile-mechanism/1", owner_id, slot, stable_key]``. Full-length
    digest, no suffixing; collisions refuse upstream with ``id-collision``.
    """
    preimage: _Json = ["profile-mechanism/1", owner_id, slot, stable_key]
    return STABLE_ID_PREFIX + digest(preimage)
