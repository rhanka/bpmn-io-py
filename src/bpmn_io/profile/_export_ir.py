"""Export-ir/1 field vocabulary and compile-time emit checks (DESIGN §10.2).

Field names, required fields and literal value types per record kind;
``counter``/``digest``/``native`` ID allocation over the planning pass.
"""

from __future__ import annotations

import math
from typing import Any

from bpmn_io.profile._c14n import digest
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

__all__ = ["check_emit", "check_export_record", "plan_ids"]

Json = Any

#: ID allocation domain order (DESIGN §10.2).
_DOMAIN_ORDER = ("page", "node", "edge", "label")

#: Optional string fields per record kind (DESIGN §10.2 field vocabulary).
_STRING_FIELDS: dict[str, frozenset[str]] = {
    "page": frozenset(),
    "node": frozenset({"name", "shape", "fill", "stroke", "textColor", "fontFamily"}),
    "edge": frozenset({"name", "stroke", "dash", "arrow"}),
    "label": frozenset(),
    "metadata": frozenset(),
}

#: Optional numeric fields per record kind.
_NUMBER_FIELDS: dict[str, frozenset[str]] = {
    "page": frozenset(),
    "node": frozenset({"fontSize", "strokeWidth"}),
    "edge": frozenset({"strokeWidth"}),
    "label": frozenset(),
    "metadata": frozenset(),
}

#: Required fields per record kind.
_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "page": frozenset({"id", "name"}),
    "node": frozenset({"id"}),
    "edge": frozenset({"id", "source", "target"}),
    "label": frozenset({"id", "text"}),
    "metadata": frozenset({"name", "value"}),
}

_ID_FIELD = "id"


def _vocabulary(kind: str) -> set[str]:
    """Return every admittable field name for one record kind."""
    names = set(_REQUIRED_FIELDS[kind])
    names.update(_STRING_FIELDS[kind])
    names.update(_NUMBER_FIELDS[kind])
    return names


def _check_literal_type(kind: str, name: str, value: dict[str, Json]) -> bool:
    """Check one literal emit value against its declared field type.

    Only the §10.2 declared optional node/edge fields carry a compile-time
    type (strings vs numbers); id, endpoints, texts and metadata values
    accept any value AST and evaluate at map time.
    """
    if not isinstance(value, dict) or value.get("op") != "literal":
        return True
    literal = value.get("value")
    if name in _NUMBER_FIELDS[kind]:
        if isinstance(literal, bool):
            return False
        if isinstance(literal, int):
            return True
        return isinstance(literal, float) and math.isfinite(literal)
    if name in _STRING_FIELDS[kind]:
        return isinstance(literal, str)
    return True


def _check_emit_field(kind: str, entry: object, vocabulary: set[str], seen: set[str]) -> str | None:
    """Check one emit field entry (name, duplicate, literal type)."""
    if not isinstance(entry, dict):
        return "profile-export-field"
    name = entry.get("name")
    if not isinstance(name, str) or name in seen or name not in vocabulary:
        return "profile-export-field"
    seen.add(name)
    value = entry.get("value")
    if name == _ID_FIELD and not isinstance(value, dict):
        return "profile-export-field"
    if isinstance(value, dict) and not _check_literal_type(kind, name, value):
        return "profile-export-field"
    return None


def check_emit(step: object) -> str | None:  # noqa: PLR0911
    """Check one emit step (field vocabulary, duplicates, literals).

    Returns ``profile-export-field`` for vocabulary violations,
    ``profile-type`` for a page parent, else ``None``.
    """
    if not isinstance(step, dict):
        return "profile-export-field"
    kind = step.get("kind")
    if kind not in _REQUIRED_FIELDS:
        return "profile-export-field"
    if kind == "page" and step.get("parent") is not None:
        return "profile-type"
    fields = step.get("fields")
    if not isinstance(fields, list):
        return "profile-export-field"
    name = str(kind)
    vocabulary = _vocabulary(name)
    seen: set[str] = set()
    for entry in fields:
        code = _check_emit_field(name, entry, vocabulary, seen)
        if code is not None:
            return code
    if not _REQUIRED_FIELDS[name] <= seen:
        return "profile-export-field"
    return None


def check_export_record(export: object) -> str | None:
    """Check one exports[] record (counter-origin policy); refusal or ``None``."""
    if not isinstance(export, dict):
        return "profile-type"
    policy = export.get("idPolicy")
    origin = export.get("counterOrigin")
    if (
        policy != "counter"
        and isinstance(origin, (int, float))
        and not isinstance(origin, bool)
        and origin != 0
    ):
        return "profile-type"
    return None


def _check_plan_request(entry: object) -> dict[str, object] | None:
    """Normalize one ID request (None when malformed)."""
    if not isinstance(entry, dict):
        return None
    page_id = entry.get("pageId")
    key = entry.get("occurrenceKey")
    domain = entry.get("domain")
    if (
        not isinstance(page_id, str)
        or not isinstance(key, str)
        or not isinstance(domain, str)
        or domain not in _DOMAIN_ORDER
    ):
        return None
    semantic_id = entry.get("semanticId")
    return {
        "pageId": page_id,
        "occurrenceKey": key,
        "domain": domain,
        "semanticId": semantic_id if isinstance(semantic_id, str) else None,
    }


def plan_ids(plan: object) -> PureResult:
    """Allocate one call-local ID plan (DESIGN §10.1 step 7).

    The explicit plan is ``{policy, counterOrigin, pages?, requests}``
    with ``requests`` as ``{pageId, occurrenceKey, domain, semanticId?}``.
    ``counter`` numbers the deduplicated keys in domain, page-order then
    UTF-16 key order from ``counterOrigin``; ``digest`` hashes each key;
    ``native`` reuses page and semantic ids, refusing
    ``export-id-ambiguous`` on synthetic, anonymous or duplicate ids.
    """
    checked, code = _check_plan(plan)
    if checked is None:
        return PureRefused(code=code or "profile-type")
    policy, origin, order_of, normalized = checked
    if policy == "counter":
        return _plan_counter(normalized, order_of, origin)
    if policy == "digest":
        return _plan_digest(normalized)
    return _plan_native(normalized)


def _check_plan(
    plan: object,
) -> tuple[tuple[str, int, dict[str, int], list[dict[str, object]]] | None, str | None]:
    """Validate one explicit ID plan (checked tuple, code)."""
    if not isinstance(plan, dict):
        return None, "profile-type"
    policy = plan.get("policy")
    origin = plan.get("counterOrigin")
    requests = plan.get("requests")
    if (
        policy not in ("counter", "digest", "native")
        or type(origin) is not int
        or origin < 0
        or not isinstance(requests, list)
    ):
        return None, "profile-type"
    order_of, code = _plan_order_of(plan.get("pages", []))
    if code is not None or order_of is None:
        return None, code or "profile-type"
    normalized: list[dict[str, object]] = []
    for entry in requests:
        request = _check_plan_request(entry)
        if request is None:
            return None, "profile-type"
        normalized.append(request)
    if not isinstance(policy, str) or type(origin) is not int:
        return None, "profile-type"
    return (policy, origin, order_of, normalized), None


def _plan_order_of(pages: object) -> tuple[dict[str, int] | None, str | None]:
    """Index one plan page list by page id (order map, code)."""
    if not isinstance(pages, list):
        return None, "profile-type"
    order_of: dict[str, int] = {}
    for page in pages:
        if (
            not isinstance(page, dict)
            or not isinstance(page.get("pageId"), str)
            or type(page.get("order")) is not int
        ):
            return None, "profile-type"
        order_of[str(page.get("pageId"))] = int(page.get("order"))  # type: ignore[arg-type]
    return order_of, None


def _plan_counter(
    requests: list[dict[str, object]], order_of: dict[str, int], origin: int
) -> PureResult:
    """Allocate counter ids in domain, page-order then key order."""
    keys: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for request in requests:
        key = (str(request["pageId"]), str(request["occurrenceKey"]), str(request["domain"]))
        if key not in seen:
            seen.add(key)
            keys.append(key)
    keys.sort(
        key=lambda key: (
            _DOMAIN_ORDER.index(key[2]),
            str(order_of.get(key[0], 0)).encode("utf-16-be"),
            key[1].encode("utf-16-be"),
        )
    )
    return PureSuccess(
        payload={
            "ids": [
                {
                    "pageId": key[0],
                    "occurrenceKey": key[1],
                    "domain": key[2],
                    "id": f"e_{origin + index}",
                }
                for index, key in enumerate(keys)
            ]
        }
    )


def _plan_digest(requests: list[dict[str, object]]) -> PureResult:
    """Allocate digest ids in first-request order."""
    payload: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for request in requests:
        key = (str(request["pageId"]), str(request["occurrenceKey"]), str(request["domain"]))
        if key in seen:
            continue
        seen.add(key)
        payload.append(
            {
                "pageId": key[0],
                "occurrenceKey": key[1],
                "domain": key[2],
                "id": f"e_{digest([key[0], key[1], key[2]])}",
            }
        )
    return PureSuccess(payload={"ids": payload})


def _plan_native(requests: list[dict[str, object]]) -> PureResult:
    """Reuse page and semantic ids, refusing ambiguous ones."""
    payload: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    seen_ids: dict[str, tuple[str, str, str]] = {}
    for request in requests:
        key = (str(request["pageId"]), str(request["occurrenceKey"]), str(request["domain"]))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key[2] == "page":
            allocated = key[0]
        else:
            semantic_id = request["semanticId"]
            if not isinstance(semantic_id, str):
                return PureRefused(code="export-id-ambiguous")
            allocated = semantic_id
        first = seen_ids.get(allocated)
        if first is not None and first != key:
            return PureRefused(code="export-id-ambiguous")
        seen_ids[allocated] = key
        payload.append(
            {"pageId": key[0], "occurrenceKey": key[1], "domain": key[2], "id": allocated}
        )
    return PureSuccess(payload={"ids": payload})
