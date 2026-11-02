"""Lot-3 gate table (DESIGN R3.3 §13 with §16; harmonization H H1, H2, H3).

Every owner part below was ratified on 2026-10-14; every technical part
(conductor plus both libraries) is open. A gated effective change refuses
``profile-open`` in ``edit`` activation and proceeds for neutral
qualification, except membership removal whose responsibility
representation is unresolved (``responsibility-preservation-required``).
"""

from __future__ import annotations

from types import MappingProxyType

__all__ = ["GATES"]

#: Read-only lot-3 gate table (§7 of the lot-3 binding).
GATES = MappingProxyType(
    {
        "OPEN-EXTERNAL": MappingProxyType(
            {
                "owner": "ratified",
                "ownerRecord": "DESIGN R3.3 §16 item 2",
                "technical": "open",
                "guards": "normalize: an effective bpmn:Lane flowNodeRef membership change",
                "edit": "profile-open",
                "qualification": "proceeds",
            }
        ),
        "OPEN-ID": MappingProxyType(
            {
                "owner": "ratified",
                "ownerRecord": "DESIGN R3.3 §16 item 1",
                "technical": "open",
                "guards": "remap_ids",
                "edit": "profile-open",
                "qualification": "proceeds",
            }
        ),
        "OPEN-IO": MappingProxyType(
            {
                "owner": "ratified",
                "ownerRecord": "DESIGN R3.3 §16 item 8",
                "technical": "open",
                "guards": "complete: filling an absent bpmn:DataOutputAssociation sourceRef",
                "edit": "profile-open",
                "qualification": "proceeds",
            }
        ),
        "OPEN-MACHINE": MappingProxyType(
            {
                "owner": "ratified",
                "ownerRecord": "DESIGN R3.3 §16 item 6",
                "technical": "open",
                "guards": "bind_supports",
                "edit": "profile-open",
                "qualification": "proceeds",
            }
        ),
        "OPEN-RESERVED-N": MappingProxyType(
            {
                "owner": "ratified",
                "ownerRecord": "DESIGN R3.3 §16 item 11",
                "technical": "open",
                "guards": "normalize: an ensure that would create a support object",
                "edit": "profile-open",
                "qualification": "proceeds",
            }
        ),
        "OPEN-SHARING": MappingProxyType(
            {
                "owner": "ratified",
                "ownerRecord": "DESIGN R3.3 §16 item 4",
                "technical": "open",
                "guards": "normalize: removal of an existing bpmn:Lane flowNodeRef membership",
                "edit": "profile-open",
                "qualification": "responsibility-preservation-required",
            }
        ),
    }
)
