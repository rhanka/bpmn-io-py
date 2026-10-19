"""Lot-3 normalization (DESIGN §7 ``normalize`` with §4.6 placements).

``sort_placements`` orders one placement list in §4.6 order. ``normalize``
lands in this module; it reuses the plan/apply machinery through
function-local imports so this module never creates an import cycle with
:mod:`bpmn_io.profile._cn_apply`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io.profile._cn_context import _utf16

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["sort_placements"]


def sort_placements(placements: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Sort one placement list in §4.6 order (deep copies).

    Owner process, region, element, anchor (absent first), then the
    related association array lexicographically.
    """
    owned: list[tuple[str, str, str, str | None, list[str]]] = []
    for placement in placements:
        element_id = placement.get("elementId")
        owner_id = placement.get("ownerProcessId")
        region = placement.get("regionKey")
        related = placement.get("relatedAssociationIds")
        anchor = placement.get("anchorAssociationId")
        if not isinstance(related, list):
            msg = "placement record is malformed"
            raise TypeError(msg)
        related_ids: list[str] = []
        for item in related:
            if not isinstance(item, str):
                msg = "placement record is malformed"
                raise TypeError(msg)
            related_ids.append(item)
        if (
            not isinstance(element_id, str)
            or not isinstance(owner_id, str)
            or not isinstance(region, str)
            or (anchor is not None and not isinstance(anchor, str))
            or set(placement.keys())
            - {
                "elementId",
                "ownerProcessId",
                "regionKey",
                "relatedAssociationIds",
                "anchorAssociationId",
            }
        ):
            msg = "placement record is malformed"
            raise TypeError(msg)
        owned.append((element_id, owner_id, region, anchor, related_ids))

    def _key(
        parts: tuple[str, str, str, str | None, list[str]],
    ) -> tuple[Any, ...]:
        element_id, owner_id, region, anchor, related = parts
        return (
            _utf16(owner_id),
            _utf16(region),
            _utf16(element_id),
            (0,) if anchor is None else (1, _utf16(anchor)),
            tuple(_utf16(item) for item in related),
        )

    ordered = sorted(owned, key=_key)
    result: list[dict[str, object]] = []
    for element_id, owner_id, region, anchor, related in ordered:
        record: dict[str, object] = {
            "elementId": element_id,
            "ownerProcessId": owner_id,
            "regionKey": region,
            "relatedAssociationIds": related,
        }
        if anchor is not None:
            record["anchorAssociationId"] = anchor
        result.append(record)
    return result
