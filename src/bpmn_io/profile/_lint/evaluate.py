# DESIGN R3.3 §§2.2-2.3, §6.4: declarative rule evaluation via the full evaluator.
"""Evaluate compiled declarative profile rules through the full evaluator.

Rule selection and assertion run on :func:`bpmn_io.profile.evaluate_predicate`
and :func:`bpmn_io.profile.select` over one immutable :class:`ReadContext`
built from the lint input tree: the stage snapshot carries the lint ``phase``,
the envelope support bindings and the compiled notions. Declared rule
bindings (``bind`` records with ``as`` / ``select`` / ``cardinality``)
evaluate per candidate before the assertion. A refused selection or
assertion (unknown operator, unbound name, cardinality mismatch, missing
pointer, unavailable capability) raises :class:`EvaluationError`, which the
caller reports as ``lint-rule-error``: the evaluator is unavailable for that
rule, never silently false.

Failing assertions emit one subfinding per candidate, ID-bearing candidates
first in selector order, then ID-less candidates by source pointer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bpmn_io.profile._evaluate import ReadContext, evaluate_predicate, select
from bpmn_io.profile._lint.c14n import utf16_key
from bpmn_io.profile._lint.index import walk_tree
from bpmn_io.profile._results import PureRefused

if TYPE_CHECKING:
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["EvaluationError", "SubFinding", "evaluate_rule"]


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


def evaluate_rule(
    rule: dict[str, Any],
    root: ModdleElement,
    *,
    phase: str,
    notions: dict[str, dict[str, Any]] | None = None,
    bindings: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> list[SubFinding]:
    """Evaluate one compiled rule on ``root`` and return its subfindings.

    ``phase`` is the current lint stage carried by the read context;
    ``notions`` maps compiled notion IDs to their records for
    notions-aware operators; ``bindings`` carries the envelope support
    bindings. Rules of another phase are skipped by the caller; this
    function assumes the rule belongs to the current stage. The input
    tree is only read.
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
    assertion = rule.get("assert")
    if not isinstance(assertion, dict):
        msg = f"compiled rule <{rule_id}> misses its assert predicate"
        raise EvaluationError(msg)
    profile_rule_id = f"profile:{rule_id}"
    context, pointers = _read_context(root, phase=phase, bindings=bindings)
    base_bindings: dict[str, Any] = {"root": root, "notions": dict(notions or {})}
    declared = rule.get("bindings", [])
    if not isinstance(declared, list):
        msg = f"compiled rule <{rule_id}> bindings must be an array"
        raise EvaluationError(msg)
    candidates = _select(rule.get("select"), context, base_bindings, rule_id=rule_id)
    findings: list[SubFinding] = []
    anonymous: list[SubFinding] = []
    for handle in candidates:
        local = _bind_rule(declared, context, base_bindings, handle.element, rule_id=rule_id)
        local["self"] = handle.element
        holds = _evaluate(assertion, context, local, rule_id=rule_id)
        if not holds:
            finding = SubFinding(
                profile_rule_id=profile_rule_id,
                code=code,
                message_key=message,
                source_pointer=_pointer_for(pointers, handle.element, rule_id=rule_id),
                target_id=handle.element_id,
            )
            if handle.element_id is None:
                anonymous.append(finding)
            else:
                findings.append(finding)
    anonymous.sort(key=lambda finding: utf16_key(finding.source_pointer))
    return findings + anonymous


def _read_context(
    root: ModdleElement,
    *,
    phase: str,
    bindings: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> tuple[ReadContext, dict[int, str]]:
    """Build the immutable read context and handle-pointer map of ``root``."""
    pairs = walk_tree(root)
    elements = tuple(node for node, _ in pairs)
    by_id: dict[str, object] = {
        node_id: node
        for node, _ in pairs
        if isinstance((node_id := node.get("id")), str) and node_id
    }
    support = tuple(dict(entry) for entry in bindings) if bindings else ()
    return ReadContext(root=root, elements=elements, by_id=by_id, bindings=support, stage=phase), {
        id(node): pointer for node, pointer in pairs
    }


def _select(
    selector: Any,  # noqa: ANN401 - compiled rule content
    context: ReadContext,
    bindings: dict[str, Any],
    *,
    rule_id: str,
) -> list[Any]:
    """Run one selector through the full evaluator (refusals stay errors)."""
    result = select(selector, context, bindings)
    if isinstance(result, PureRefused):
        msg = f"compiled rule <{rule_id}> selection is unavailable: {result.code}"
        raise EvaluationError(msg)
    handles = result.payload
    if not isinstance(handles, list):
        msg = f"compiled rule <{rule_id}> selection is unavailable"
        raise EvaluationError(msg)
    return handles


def _evaluate(
    assertion: dict[str, Any],
    context: ReadContext,
    bindings: dict[str, Any],
    *,
    rule_id: str,
) -> bool:
    """Run one assert predicate through the full evaluator (never false)."""
    result = evaluate_predicate(assertion, context, bindings)
    if isinstance(result, PureRefused):
        msg = f"compiled rule <{rule_id}> assertion is unavailable: {result.code}"
        raise EvaluationError(msg)
    if not isinstance(result.payload, bool):
        msg = f"compiled rule <{rule_id}> assert is not a predicate"
        raise EvaluationError(msg)
    return result.payload


def _bind_rule(
    declared: list[Any],
    context: ReadContext,
    base: dict[str, Any],
    candidate: Any,  # noqa: ANN401 - native element handle
    *,
    rule_id: str,
) -> dict[str, Any]:
    """Evaluate the declared rule bindings of one candidate (in order)."""
    bindings = dict(base)
    bindings["self"] = candidate
    for entry in declared:
        if not isinstance(entry, dict):
            msg = f"compiled rule <{rule_id}> binding must be an object"
            raise EvaluationError(msg)
        name = entry.get("as")
        if not isinstance(name, str) or not name:
            msg = f"compiled rule <{rule_id}> binding misses its name"
            raise EvaluationError(msg)
        handles = _select(entry.get("select"), context, bindings, rule_id=rule_id)
        bound = _apply_cardinality(entry.get("cardinality"), handles, rule_id)
        if bound is not None:
            bindings[name] = bound
    return bindings


def _apply_cardinality(cardinality: Any, handles: list[Any], rule_id: str) -> Any:  # noqa: ANN401
    """Bind one selection under its cardinality (mismatches refuse).

    ``one`` needs exactly one handle, ``zeroOrOne`` at most one (absent
    bindings simply stay unbound) and ``first`` takes the ordered head.
    A mismatch is an unavailable evaluation, never a false assertion
    (DESIGN R3.3 §6.4 outcome table).
    """
    if cardinality == "one":
        if len(handles) != 1:
            msg = f"compiled rule <{rule_id}> binding <one> matched {len(handles)}"
            raise EvaluationError(msg)
        return handles[0].element
    if cardinality == "zeroOrOne":
        if len(handles) > 1:
            msg = f"compiled rule <{rule_id}> binding <zeroOrOne> matched {len(handles)}"
            raise EvaluationError(msg)
        return handles[0].element if handles else None
    if cardinality == "first":
        return handles[0].element if handles else None
    msg = f"compiled rule <{rule_id}> binding needs a cardinality"
    raise EvaluationError(msg)


def _pointer_for(pointers: dict[int, str], element: Any, *, rule_id: str) -> str:  # noqa: ANN401
    """Return the absolute source pointer of one selected element."""
    pointer = pointers.get(id(element))
    if pointer is None:
        msg = f"compiled rule <{rule_id}> candidate misses its source pointer"
        raise EvaluationError(msg)
    return pointer
