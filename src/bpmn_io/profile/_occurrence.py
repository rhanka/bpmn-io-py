"""Occurrence-query evaluator (prototype of the PY-R4 ruling, R5 order).

Transcription of ``lot4-query.ts`` (bpmn-canvas fec4dae) lines 116-360:
``resolveBinding``, ``evaluateOccurrenceValue``, ``testOccurrencePredicate``
and ``runOccurrenceSelect``. Used by the export map for capability ``when``,
recipe ``select``, ``bind`` selects and emit values. Element predicates,
``reachable`` and other value ops delegate to the native evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NoReturn

from bpmn_io.profile._evaluate import (
    _MISSING,
    ReadContext,
    _eval_predicate,
    _eval_value,
)

MISSING = _MISSING


def _fail(code: str | None) -> NoReturn:
    raise ValueError(code if code is not None else "operation-error")


@dataclass
class OccurrenceScope:
    occurrences: list[dict[str, object]]
    pages: list[dict[str, object]]
    by_id: dict[str, object]
    context: ReadContext
    bound: dict[str, object] = field(default_factory=dict)

    def with_self(self, value: object) -> OccurrenceScope:
        return OccurrenceScope(
            self.occurrences, self.pages, self.by_id, self.context, {**self.bound, "self": value}
        )


def _is_occurrence(item: object) -> bool:
    return (
        isinstance(item, dict)
        and isinstance(item.get("pageId"), str)
        and isinstance(item.get("occurrenceKey"), str)
    )


def _semantic_of(scope: OccurrenceScope, occurrence: object) -> object | None:
    sid = occurrence.get("semanticId") if isinstance(occurrence, dict) else None
    return scope.by_id.get(sid) if isinstance(sid, str) else None


def _resolve(name: object, scope: OccurrenceScope) -> object:
    if name == "self":
        return scope.bound.get("self")
    found = scope.bound.get(name) if isinstance(name, str) else None
    return MISSING if found is None else found


def read_path(target: object, path: object) -> object:
    """``readPath``: plain JSON walk, array indexes, absent = MISSING."""
    if not isinstance(path, str) or not path.startswith("/"):
        return MISSING
    current = target
    for segment in path[1:].split("/"):
        if current is None or current is MISSING or not isinstance(current, (dict, list)):
            return MISSING
        if isinstance(current, list):
            if not segment.isdigit() or (len(segment) > 1 and segment[0] == "0"):
                return MISSING
            index = int(segment)
            current = current[index] if index < len(current) else None
            if current is None:
                return MISSING
            continue
        if segment not in current:
            return MISSING
        current = current[segment]
    return current


def _shared_bindings(scope: OccurrenceScope) -> dict[str, object]:
    out: dict[str, object] = {"self": scope.context.root}
    for name, value in scope.bound.items():
        if value is MISSING or value is None or not isinstance(value, dict):
            continue
        out[name] = value
    return out


def _delegate_value(ast: dict[str, object], scope: OccurrenceScope) -> object:
    return _eval_value(ast, scope.context, _shared_bindings(scope))


def _lit(operand: object) -> dict[str, object]:
    if not isinstance(operand, str):
        _fail("profile-type")
    return {"op": "literal", "value": operand}


def evaluate_occurrence_value(  # noqa: C901, PLR0911, PLR0912 - one branch per value op
    value: object, scope: OccurrenceScope
) -> object:
    if not isinstance(value, dict):
        return MISSING
    op = value.get("op")
    if op == "literal":
        return MISSING if "value" not in value else value.get("value")
    if op == "read":
        target = _resolve(value.get("binding"), scope)
        if target is MISSING:
            return MISSING
        return read_path(target, value.get("path"))
    if op == "outputId":
        return MISSING
    if op == "concat":
        inputs = value.get("values")
        if not isinstance(inputs, list) or not inputs:
            _fail("profile-schema")
        parts = []
        for item in inputs:
            part = evaluate_occurrence_value(item, scope)
            if not isinstance(part, str):
                _fail("profile-type")
            parts.append(part)
        return _delegate_value({"op": "concat", "values": [_lit(p) for p in parts]}, scope)
    if op == "stripPrefix":
        raw = evaluate_occurrence_value(value.get("value"), scope)
        if not isinstance(raw, str):
            _fail("profile-type")
        return _delegate_value(
            {
                "op": "stripPrefix",
                "value": _lit(raw),
                "prefix": value.get("prefix"),
                "trim": value.get("trim"),
            },
            scope,
        )
    if op == "case":
        raw = evaluate_occurrence_value(value.get("value"), scope)
        if not isinstance(raw, str):
            _fail("profile-type")
        return _delegate_value({"op": "case", "value": _lit(raw), "mode": value.get("mode")}, scope)
    if op == "id":
        target = _resolve(value.get("binding"), scope)
        if target is MISSING:
            return MISSING
        ident = target.get("id") if isinstance(target, dict) else getattr(target, "id", None)
        return ident if isinstance(ident, str) else MISSING
    if op == "param":
        _fail("profile-symbol")
    if op == "ids":
        _fail("profile-value-context")
    return _delegate_value(value, scope)


def _owner_of(scope: OccurrenceScope, element_id: str) -> object | None:
    owners = {b.get("ownerId") for b in scope.context.bindings if b.get("targetId") == element_id}
    if len(owners) != 1:
        return None
    owner = next(iter(owners))
    return scope.by_id.get(owner) if isinstance(owner, str) else None


def test_occurrence_predicate(predicate: object, scope: OccurrenceScope) -> bool:  # noqa: C901, PLR0911, PLR0912
    if not isinstance(predicate, dict):
        return False
    op = predicate.get("op")
    if op == "true":
        return True
    if op == "false":
        return False
    if op == "all":
        return all(test_occurrence_predicate(a, scope) for a in predicate.get("args", []))
    if op == "any":
        return any(test_occurrence_predicate(a, scope) for a in predicate.get("args", []))
    if op == "not":
        return not test_occurrence_predicate(predicate.get("arg"), scope)
    if op == "equal":
        left = evaluate_occurrence_value(predicate.get("left"), scope)
        right = evaluate_occurrence_value(predicate.get("right"), scope)
        if left is MISSING or right is MISSING:
            return False
        if isinstance(left, bool) or isinstance(right, bool):
            return isinstance(left, bool) and isinstance(right, bool) and left == right
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left == right
        return type(left) is type(right) and left == right
    if op == "present":
        return evaluate_occurrence_value(predicate.get("value"), scope) is not MISSING
    if op == "textPrefix":
        raw = evaluate_occurrence_value(predicate.get("value"), scope)
        if raw is MISSING:
            return False
        if not isinstance(raw, str):
            _fail("profile-type")
        return bool(
            _eval_predicate(
                {
                    "op": "textPrefix",
                    "value": _lit(raw),
                    "prefix": predicate.get("prefix"),
                    "trim": predicate.get("trim"),
                },
                scope.context,
                _shared_bindings(scope),
            )
        )
    if op == "reachable":
        return bool(_eval_predicate(predicate, scope.context, _shared_bindings(scope)))
    if op == "count":
        found = run_occurrence_select(predicate.get("select"), scope)
        mn, mx = predicate.get("min"), predicate.get("max")
        if isinstance(mn, int) and len(found) < mn:
            return False
        return not (isinstance(mx, int) and len(found) > mx)
    if op in ("typeIs", "recognizes", "boundRole"):
        name = predicate.get("binding")
        if not isinstance(name, str) or name not in scope.bound:
            _fail("profile-symbol")
        target = scope.bound[name]
        if target is MISSING or not isinstance(target, dict):
            return False
        element = _semantic_of(scope, target) if _is_occurrence(target) else target
        if element is None:
            return False
        ident = element.get("id") if isinstance(element, dict) else None
        owner = _owner_of(scope, ident) if isinstance(ident, str) else None
        bindings: dict[str, object] = {"self": element}
        if owner is not None:
            bindings["bindingOwner"] = owner
        return bool(_eval_predicate(predicate, scope.context, bindings))
    return False


def run_occurrence_select(selector: object, scope: OccurrenceScope) -> list[object]:  # noqa: C901, PLR0911, PLR0912
    if not isinstance(selector, dict):
        _fail(None)
    frm, via = selector.get("from"), selector.get("via")
    where = selector.get("where") or {"op": "true"}

    def collect(candidates: list[object]) -> list[object]:
        return [c for c in candidates if test_occurrence_predicate(where, scope.with_self(c))]

    if frm == "render" and via == "pages":
        return collect(list(scope.pages))
    if frm == "render" and via == "occurrences":
        return collect(list(scope.occurrences))
    if frm == "self" and via == "self":
        return [scope.bound.get("self")] if test_occurrence_predicate(where, scope) else []
    if frm == "self" and via == "semantic":
        self_value = scope.bound.get("self")
        element = _semantic_of(scope, self_value) if _is_occurrence(self_value) else None
        if element is None:
            return []
        return [element] if test_occurrence_predicate(where, scope.with_self(element)) else []
    if frm == "root" and via == "self":
        root = scope.context.root
        return [root] if test_occurrence_predicate(where, scope.with_self(root)) else []
    source = _resolve(frm, scope)
    if source is MISSING:
        _fail(None)
    if via == "self":
        return [source] if test_occurrence_predicate(where, scope.with_self(source)) else []
    if via == "semantic":
        element = _semantic_of(scope, source) if _is_occurrence(source) else None
        if element is None:
            return []
        return [element] if test_occurrence_predicate(where, scope.with_self(element)) else []
    if via == "children":
        if not isinstance(source, dict):
            _fail(None)
        value = source.get(selector.get("property"))
        items = value if isinstance(value, list) else ([value] if value else [])
        return collect([i for i in items if isinstance(i, dict)])
    if frm == "self" and via == "reference":
        self_value = scope.bound.get("self")
        if not isinstance(self_value, dict):
            _fail(None)
        ref = self_value.get(selector.get("property"))
        refs = ref if isinstance(ref, list) else [ref]
        wanted = {
            (r.get("pageId"), r.get("occurrenceKey"))
            for r in refs
            if isinstance(r, dict)
            and isinstance(r.get("pageId"), str)
            and isinstance(r.get("occurrenceKey"), str)
        }
        return collect(
            [o for o in scope.occurrences if (o.get("pageId"), o.get("occurrenceKey")) in wanted]
        )
    _fail(None)
