# DESIGN R3.3 §§2.2-2.3: declarative rule evaluation for the lint bridge (lot-1 subset).
"""Evaluate compiled declarative profile rules against the immutable input tree.

Lot 1 covers the recognition subset used by the neutral fixtures: selectors
with ``from: root`` / ``via: all`` / ``order: id``, the predicates
``true`` / ``false`` / ``all`` / ``any`` / ``not`` / ``typeIs`` /
``present`` / ``equal`` / ``count``, and the values ``literal`` / ``read`` /
``id``. Anything else (other traversals, text, reachability, binding and
export-only operators) raises :class:`EvaluationError`, which the caller
reports as ``lint-rule-error``: the evaluator is unavailable for that rule,
never silently false. Lot 2 replaces this module with the full evaluator;
the subfinding shape it returns is already the final one.

Semantics follow DESIGN R3.3 exactly within the subset: ``present`` is
false only for ``MISSING`` (empty string, ``false`` and zero are present);
``equal`` needs the same scalar type and value with no coercion and is
false when either side is ``MISSING``; ``where`` errors are errors, never
false; ``all`` / ``any`` evaluate every branch in array order and propagate
errors. A failing assertion emits one subfinding per candidate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from bpmn_io._bpmnlint_utils import is_
from bpmn_io._js import UNDEFINED
from bpmn_io.profile._lint.c14n import utf16_key
from bpmn_io.profile._lint.index import walk_tree

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["MISSING", "EvaluationError", "SubFinding", "evaluate_rule"]

#: Predicate operators evaluated here (DESIGN R3.3 §2.3, lot-1 subset).
_PREDICATES = frozenset(
    {"true", "false", "all", "any", "not", "typeIs", "present", "equal", "count"}
)

#: Value operators evaluated here (DESIGN R3.3 §2.2, lot-1 subset).
_VALUES = frozenset({"literal", "read", "id"})


class _Missing:
    """Sentinel for absent values (distinct from ``None`` and ``null``)."""

    def __repr__(self) -> str:
        """Describe the sentinel for diagnostics."""
        return "MISSING"

    def __bool__(self) -> bool:
        """Refuse truthiness tests: missing values decide explicitly."""
        msg = "MISSING must never be tested for truthiness"
        raise EvaluationError(msg)


#: The absent-value sentinel returned by ``read`` for missing properties.
MISSING = _Missing()


class EvaluationError(Exception):
    """A rule AST cannot be evaluated here (maps to ``lint-rule-error``)."""


class SubFinding:
    """One failing candidate: metadata for the unified report entry."""

    def __init__(
        self,
        *,
        profile_rule_id: str,
        code: str,
        message_key: str,
        source_pointer: str,
        target_id: str | None,
    ) -> None:
        """Create the subfinding with its validated metadata."""
        self.profile_rule_id = profile_rule_id
        self.code = code
        self.message_key = message_key
        self.source_pointer = source_pointer
        self.target_id = target_id

    def raw_report(self) -> dict[str, Any]:
        """Render the upstream-shaped raw report for this subfinding."""
        return {
            "id": self.target_id,
            "message": self.message_key,
            "profileRuleId": self.profile_rule_id,
            "code": self.code,
            "messageKey": self.message_key,
            "sourcePointer": self.source_pointer,
        }


def evaluate_rule(rule: dict[str, Any], root: ModdleElement) -> list[SubFinding]:
    """Evaluate one compiled rule on ``root`` and return its subfindings.

    Rules of another phase are skipped by the caller; this function assumes
    the rule belongs to the current stage. The input tree is only read.
    """
    rule_id = rule.get("id")
    code = rule.get("code")
    message = rule.get("message")
    if not isinstance(rule_id, str) or not rule_id:
        msg = "compiled rule misses its string id"
        raise EvaluationError(msg)
    if not isinstance(code, str) or not code:
        msg = f"compiled rule <{rule_id}> misses its string code"
        raise EvaluationError(msg)
    if not isinstance(message, str) or not message:
        msg = f"compiled rule <{rule_id}> misses its string message"
        raise EvaluationError(msg)
    profile_rule_id = f"profile:{rule_id}"
    candidates = _select(rule.get("select"), root)
    assertion = rule.get("assert")
    if not isinstance(assertion, dict):
        msg = f"compiled rule <{rule_id}> misses its assert predicate"
        raise EvaluationError(msg)
    findings: list[SubFinding] = []
    for node, pointer in candidates:
        holds = _predicate(assertion, {"root": root, "self": node})
        if not isinstance(holds, bool):
            msg = f"compiled rule <{rule_id}> assert is not a predicate"
            raise EvaluationError(msg)
        if not holds:
            target = node.get("id")
            findings.append(
                SubFinding(
                    profile_rule_id=profile_rule_id,
                    code=code,
                    message_key=message,
                    source_pointer=pointer,
                    target_id=target if isinstance(target, str) and target else None,
                )
            )
    return findings


def _select(selector: Any, root: ModdleElement) -> list[tuple[ModdleElement, str]]:  # noqa: ANN401
    """Run a recognition selector and return ordered ``(node, pointer)`` pairs."""
    if not isinstance(selector, dict):
        msg = "selector must be an object"
        raise EvaluationError(msg)
    if selector.get("from") != "root":
        msg = f"unsupported selector from: {selector.get('from')!r}"
        raise EvaluationError(msg)
    if selector.get("via") != "all":
        msg = f"unsupported selector via: {selector.get('via')!r}"
        raise EvaluationError(msg)
    if selector.get("order") != "id":
        msg = f"unsupported selector order: {selector.get('order')!r}"
        raise EvaluationError(msg)
    where = selector.get("where")
    if not isinstance(where, dict):
        msg = "selector misses its where predicate"
        raise EvaluationError(msg)
    matched = [
        (node, pointer)
        for node, pointer in walk_tree(root)
        if _predicate(where, {"root": root, "self": node}) is True
    ]
    return _order_by_id(matched)


def _order_by_id(
    pairs: list[tuple[ModdleElement, str]],
) -> list[tuple[ModdleElement, str]]:
    """Order handles: ID-bearing first (UTF-16 ID), then ID-less by pointer.

    Deduplicates by native handle, never by optional ID.
    """
    seen: set[int] = set()
    unique: list[tuple[ModdleElement, str]] = []
    for node, pointer in pairs:
        handle = id(node)
        if handle in seen:
            continue
        seen.add(handle)
        unique.append((node, pointer))

    def _key(pair: tuple[ModdleElement, str]) -> tuple[int, bytes, bytes]:
        node, pointer = pair
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id:
            return (0, utf16_key(node_id), b"")
        return (1, b"", utf16_key(pointer))

    unique.sort(key=_key)
    return unique


def _predicate(node: Any, bindings: dict[str, Any]) -> Any:  # noqa: ANN401
    """Evaluate a predicate AST node (errors propagate, never become false)."""
    if not isinstance(node, dict):
        msg = f"predicate must be an object, got {node!r}"
        raise EvaluationError(msg)
    op = node.get("op")
    if op not in _PREDICATES:
        msg = f"unsupported predicate op: {op!r}"
        raise EvaluationError(msg)
    if op == "true":
        return True
    if op == "false":
        return False
    return _compound(op, node, bindings)


def _compound(op: str, node: dict[str, Any], bindings: dict[str, Any]) -> bool:
    """Evaluate a compound predicate through its dedicated handler."""
    if op in ("all", "any"):
        return _branch(op, node, bindings)
    if op == "not":
        return _negation(node, bindings)
    if op == "typeIs":
        return _type_is(node, bindings)
    if op == "present":
        return _value(node.get("value"), bindings) is not MISSING
    if op == "equal":
        return _equal(node.get("left"), node.get("right"), bindings)
    return _count(node, bindings)


def _negation(node: dict[str, Any], bindings: dict[str, Any]) -> bool:
    """Evaluate ``not`` over exactly one ``arg`` predicate."""
    arg = node.get("arg")
    if not isinstance(arg, dict):
        msg = "not needs exactly one arg predicate"
        raise EvaluationError(msg)
    return not _predicate(arg, bindings)


def _branch(op: str, node: dict[str, Any], bindings: dict[str, Any]) -> bool:
    """Evaluate ``all`` / ``any`` over every branch in array order."""
    args = node.get("args")
    if not isinstance(args, list) or not args:
        msg = f"{op} needs a nonempty args array"
        raise EvaluationError(msg)
    results = [_predicate(arg, bindings) for arg in args]
    if any(not isinstance(result, bool) for result in results):
        msg = f"{op} branches must be predicates"
        raise EvaluationError(msg)
    return all(results) if op == "all" else any(results)


def _binding(name: Any, bindings: dict[str, Any]) -> ModdleElement:  # noqa: ANN401
    """Resolve a binding name to its element (MISSING use refuses)."""
    if not isinstance(name, str) or name not in bindings:
        msg = f"undeclared binding: {name!r}"
        raise EvaluationError(msg)
    value = bindings[name]
    if value is MISSING:
        msg = f"required use of MISSING binding: {name!r}"
        raise EvaluationError(msg)
    if not hasattr(value, "get") or not hasattr(value, "type_"):
        msg = f"binding is not an element: {name!r}"
        raise EvaluationError(msg)
    return cast("ModdleElement", value)


def _type_is(node: dict[str, Any], bindings: dict[str, Any]) -> bool:
    """Evaluate ``typeIs`` in exact or assignable mode."""
    element = _binding(node.get("binding"), bindings)
    expected = node.get("type")
    mode = node.get("mode")
    if not isinstance(expected, str) or not expected:
        msg = f"invalid typeIs type: {expected!r}"
        raise EvaluationError(msg)
    if mode not in ("exact", "assignable"):
        msg = f"invalid typeIs mode: {mode!r}"
        raise EvaluationError(msg)
    if mode == "assignable":
        return is_(element, expected)
    actual = getattr(element, "type_", None)
    wanted = expected if ":" in expected else f"bpmn:{expected}"
    return actual == wanted


def _equal(left: Any, right: Any, bindings: dict[str, Any]) -> bool:  # noqa: ANN401
    """Evaluate ``equal``: same scalar type and value, no coercion."""
    first = _value(left, bindings)
    second = _value(right, bindings)
    if first is MISSING or second is MISSING:
        return False
    if isinstance(first, bool) or isinstance(second, bool):
        return isinstance(first, bool) and isinstance(second, bool) and first == second
    if not isinstance(first, (str, int, float)) or not isinstance(second, (str, int, float)):
        msg = f"equal needs scalar operands, got {first!r} and {second!r}"
        raise EvaluationError(msg)
    return type(first) is type(second) and first == second


def _value(node: Any, bindings: dict[str, Any]) -> Any:  # noqa: ANN401
    """Evaluate a value AST node (scalars, MISSING, or element handles)."""
    if not isinstance(node, dict):
        msg = f"value must be an object, got {node!r}"
        raise EvaluationError(msg)
    op = node.get("op")
    if op not in _VALUES:
        msg = f"unsupported value op: {op!r}"
        raise EvaluationError(msg)
    if op == "literal":
        scalar = node.get("value")
        if isinstance(scalar, (bool, str, int, float)):
            return scalar
        msg = f"literal needs a scalar value, got {scalar!r}"
        raise EvaluationError(msg)
    if op == "id":
        element = _binding(node.get("binding"), bindings)
        element_id = element.get("id")
        if not isinstance(element_id, str) or not element_id:
            msg = "id needs an identified element"
            raise EvaluationError(msg)
        return element_id
    return _read(node, bindings)


def _read(node: dict[str, Any], bindings: dict[str, Any]) -> Any:  # noqa: ANN401
    """Evaluate ``read``: raw scalar/reference value or ``MISSING``."""
    element = _binding(node.get("binding"), bindings)
    path = node.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        msg = f"read needs an RFC 6901 path, got {path!r}"
        raise EvaluationError(msg)
    current: Any = element
    for raw in path.split("/")[1:]:
        segment = raw.replace("~1", "/").replace("~0", "~")
        numbered = segment.removeprefix("-")
        if numbered.isdigit() and numbered:
            msg = "array indexing is not a recognition read"
            raise EvaluationError(msg)
        if not hasattr(current, "get"):
            return MISSING
        current = current.get(segment)
        if current is None or current is UNDEFINED:
            return MISSING
    return current


def _count(node: dict[str, Any], bindings: dict[str, Any]) -> bool:
    """Evaluate ``count`` over a nested selector with inclusive bounds."""
    selector = node.get("selector")
    minimum = node.get("min")
    maximum = node.get("max")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
        msg = f"count needs a nonnegative min, got {minimum!r}"
        raise EvaluationError(msg)
    if maximum is not None and (
        isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0
    ):
        msg = f"count needs a nonnegative max, got {maximum!r}"
        raise EvaluationError(msg)
    if isinstance(maximum, int) and maximum < minimum:
        msg = f"count min exceeds max: {minimum} > {maximum}"
        raise EvaluationError(msg)
    if not isinstance(selector, dict):
        msg = "count needs a selector"
        raise EvaluationError(msg)
    root = bindings.get("root")
    if root is None or root is MISSING:
        msg = "count needs the root binding"
        raise EvaluationError(msg)
    total = len(_select(selector, root))
    if total < minimum:
        return False
    return maximum is None or total <= maximum
