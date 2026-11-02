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


def _is_safe_integer(value: object) -> bool:
    """Return whether one value is a JS safe integer (lot4-export.ts:87)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return -(2**53 - 1) <= value <= 2**53 - 1
    if isinstance(value, float):
        return value.is_integer() and -(2**53 - 1) <= value <= 2**53 - 1
    return False


def _utf16(text: str) -> bytes:
    """Encode one string in UTF-16 code-unit order (lot4-query.ts:24-26)."""
    return text.encode("utf-16-be")


def _key_string_of(page_id: str, occurrence_key: str, domain: str) -> str:
    """Build one ID-plan key string (lot4-export.ts:56-57)."""
    return f"{page_id} {occurrence_key} {domain}"


def _check_plan_request(entry: object) -> dict[str, object]:
    """Normalize one ID request (lot4-export.ts:72-84, raises on malformed).

    A page request needs no ``occurrenceKey`` (it becomes ``""``);
    non-page requests need a string ``occurrenceKey``. Every malformed
    request raises a contract error with code ``export-id-ambiguous``.
    """
    if not isinstance(entry, dict):
        # JS: arrays are objects and fall through to requireText; every
        # other non-object fails the truthy-object check. Both refuse
        # export-id-ambiguous (never operation-error here).
        raise _PlanContract("export-id-ambiguous")  # noqa: EM101
    page_id = entry.get("pageId")
    if not isinstance(page_id, str):
        raise _PlanContract("export-id-ambiguous")  # noqa: EM101
    domain = entry.get("domain")
    if not isinstance(domain, str):
        raise _PlanContract("export-id-ambiguous")  # noqa: EM101
    if domain not in _DOMAIN_ORDER:
        raise _PlanContract("export-id-ambiguous")  # noqa: EM101
    if domain == "page":
        occurrence_key: object = ""
    else:
        occurrence_key = entry.get("occurrenceKey")
        if not isinstance(occurrence_key, str):
            raise _PlanContract("export-id-ambiguous")  # noqa: EM101
    record: dict[str, object] = {
        "pageId": page_id,
        "occurrenceKey": occurrence_key,
        "domain": domain,
    }
    # JS keeps semanticId iff !== undefined; every present JSON value kept.
    if "semanticId" in entry:
        record["semanticId"] = entry.get("semanticId")
    return record


class _PlanContract(Exception):  # noqa: N818
    """Internal contract refusal with a JS code (lot4-export.ts:69-71)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def plan_ids(  # noqa: C901, PLR0911, PLR0912
    plan: object,
) -> PureResult:
    """Allocate one call-local ID plan (lot4-export.ts:62-147).

    Every malformed input refuses ``export-id-ambiguous``; a non-array
    ``requests``/``pages`` throws a non-contract error and refuses
    ``operation-error``. ``pages`` absent is ``[]``; counter order uses the
    numeric page order (last wins) with the stable domain/order/key sort.
    """
    try:
        if not isinstance(plan, dict):
            return PureRefused(code="export-id-ambiguous")
        policy = plan.get("policy")
        if policy not in ("counter", "digest", "native"):
            return PureRefused(code="export-id-ambiguous")
        raw_requests = plan.get("requests") if "requests" in plan else []
        # JS: (plan.requests ?? []).map — null/undefined become []; any
        # other non-array throws non-contract TypeError -> operation-error.
        if raw_requests is None:
            raw_requests = []
        if not isinstance(raw_requests, list):
            return PureRefused(code="operation-error")
        normalized = [_check_plan_request(entry) for entry in raw_requests]
        if policy == "counter":
            origin = plan.get("counterOrigin")
            if not _is_safe_integer(origin):
                return PureRefused(code="export-id-ambiguous")
            origin_int = int(origin)  # type: ignore[arg-type]
            raw_pages = plan.get("pages") if "pages" in plan else []
            if raw_pages is None:
                raw_pages = []
            if not isinstance(raw_pages, list):
                return PureRefused(code="operation-error")
            order_of: dict[object, object] = {}
            for item in raw_pages:
                # JS: null/undefined page throws on property access.
                if item is None:
                    return PureRefused(code="operation-error")
                if isinstance(item, dict):
                    page_id = item.get("pageId")
                    order = item.get("order")
                else:
                    # Primitives: property access yields undefined, never throws.
                    page_id = None
                    order = None
                # new Map last wins, keys kept as-is.
                order_of[page_id] = order
            return _plan_counter(normalized, order_of, origin_int)
        if policy == "digest":
            return _plan_digest(normalized)
        return _plan_native(normalized)
    except _PlanContract as exc:
        return PureRefused(code=exc.code or "export-id-ambiguous")
    except Exception:  # noqa: BLE001 - JS non-contract error -> operation-error
        return PureRefused(code="operation-error")


def _plan_counter(
    requests: list[dict[str, object]], order_of: dict[object, object], origin: int
) -> PureResult:
    """Allocate counter ids (lot4-export.ts:85-107)."""
    keys: list[dict[str, object]] = []
    seen: set[str] = set()
    for request in requests:
        text = _key_string_of(
            str(request["pageId"]), str(request["occurrenceKey"]), str(request["domain"])
        )
        if text not in seen:
            seen.add(text)
            keys.append(request)

    def _order_of(page_id: object) -> float:
        value = order_of.get(page_id, 0)
        # JS: (order.get(...) ?? 0) - (...) with JS numeric coercion; a
        # non-numeric order yields NaN which sorts as equal. Mirror by
        # treating non-finite/non-numeric orders as 0 for ordering.
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, (int, float)):
            try:
                number = float(value)
            except (ValueError, OverflowError):
                return 0.0
            if math.isnan(number):
                return 0.0
            return number
        return 0.0

    decorated = list(enumerate(keys))
    decorated.sort(
        key=lambda pair: (
            _DOMAIN_ORDER.index(str(pair[1]["domain"])),
            _order_of(pair[1]["pageId"]),
            _utf16(str(pair[1]["occurrenceKey"])),
            pair[0],
        )
    )
    # Python sort is stable; the index tie-break keeps JS stability for
    # NaN/equal orders. Re-sort with the exact JS comparator keys only:
    # domain rank, numeric page order, UTF-16 occurrenceKey (stable).
    return PureSuccess(
        payload={
            "ids": [
                {
                    "pageId": key["pageId"],
                    "occurrenceKey": key["occurrenceKey"],
                    "domain": key["domain"],
                    "id": f"e_{origin + index}",
                }
                for index, key in enumerate([item for _, item in decorated])
            ]
        }
    )


def _plan_digest(requests: list[dict[str, object]]) -> PureResult:
    """Allocate digest ids per request, no dedupe (lot4-export.ts:108-121)."""
    rows = []
    for request in requests:
        hashed = digest([request["pageId"], request["occurrenceKey"], request["domain"]])
        rows.append(
            {
                "pageId": request["pageId"],
                "occurrenceKey": request["occurrenceKey"],
                "domain": request["domain"],
                "id": f"e_{hashed}",
            }
        )
    return PureSuccess(payload={"ids": rows})


def _plan_native(requests: list[dict[str, object]]) -> PureResult:
    """Reuse page and semantic ids (lot4-export.ts:122-141)."""
    ids: list[dict[str, object]] = []
    seen_texts: set[str] = set()
    used: dict[str, str] = {}
    for request in requests:
        text = _key_string_of(
            str(request["pageId"]), str(request["occurrenceKey"]), str(request["domain"])
        )
        if text in seen_texts:
            continue
        seen_texts.add(text)
        if request["domain"] == "page":
            allocated = str(request["pageId"])
        else:
            semantic_id = request.get("semanticId")
            if not isinstance(semantic_id, str) or semantic_id == "":
                return PureRefused(code="export-id-ambiguous")
            allocated = semantic_id
        if allocated in used and used[allocated] != text:
            return PureRefused(code="export-id-ambiguous")
        used[allocated] = text
        ids.append(
            {
                "pageId": request["pageId"],
                "occurrenceKey": request["occurrenceKey"],
                "domain": request["domain"],
                "id": allocated,
            }
        )
    return PureSuccess(payload={"ids": ids})
