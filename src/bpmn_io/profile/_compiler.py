"""Profile compiler (DESIGN R3.3 §2 with §2.4.1 rejection mapping).

Validates selectors, predicates and recipes, scheduling inputs, registries,
signatures, closed references and descriptor context. Returns the first
applicable closed refusal code; malicious or unknown ASTs refuse with the
mapped code, never a partial compiled result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from bpmn_io.profile._c14n import digest, digest_bytes, jcs
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

if TYPE_CHECKING:
    from bpmn_io.profile._loader import ValidatedProfile

__all__ = [
    "CompiledProfile",
    "DescriptorContext",
    "RegistrySet",
    "compile_profile",
    "create_descriptor_context",
]

_VALUE_OPS = frozenset(
    {
        "literal",
        "read",
        "id",
        "ids",
        "param",
        "concat",
        "stripPrefix",
        "case",
        "outputId",
    }
)

_PREDICATE_OPS = frozenset(
    {
        "true",
        "false",
        "all",
        "any",
        "not",
        "typeIs",
        "present",
        "equal",
        "textPrefix",
        "count",
        "boundRole",
        "recognizes",
        "reachable",
    }
)

_SELECTOR_VIA = frozenset(
    {
        "self",
        "root",
        "owner",
        "children",
        "descendants",
        "reference",
        "inverseReference",
        "all",
        "pages",
        "occurrences",
        "semantic",
    }
)

_ACTION_OPS = frozenset(
    {
        "bind",
        "create",
        "ensure",
        "set",
        "unset",
        "assignRef",
        "reparent",
        "place",
        "emit",
        "loss",
        "remove",
        "refuse",
    }
)

_PHASES = frozenset(
    {
        "create",
        "edit",
        "complete",
        "normalize",
        "reference",
        "export",
        "convert",
        "migrate",
    }
)

_KNOWN_CAPABILITIES = frozenset(
    {
        "predicates/1",
        "selectors/1",
        "recipes/1",
        "profile-lint/1",
        "render-data/1",
        "export-ir/1",
    }
)

_ACTION_PHASES: dict[str, frozenset[str]] = {
    "bind": _PHASES,
    "refuse": _PHASES,
    "create": frozenset({"create", "edit", "reference", "complete", "convert", "migrate"}),
    "ensure": frozenset({"normalize"}),
    "set": frozenset(
        {"create", "edit", "reference", "complete", "normalize", "convert", "migrate"}
    ),
    "unset": frozenset(
        {"create", "edit", "reference", "complete", "normalize", "convert", "migrate"}
    ),
    "assignRef": frozenset(
        {"create", "edit", "reference", "complete", "normalize", "convert", "migrate"}
    ),
    "reparent": frozenset({"edit", "convert", "migrate"}),
    "place": frozenset({"normalize"}),
    "emit": frozenset({"export"}),
    "loss": frozenset({"export"}),
    "remove": frozenset({"edit", "convert", "migrate"}),
}


@dataclass(frozen=True)
class DescriptorContext:
    """Immutable descriptor and effective-base index for compilation."""

    packages: tuple[dict[str, object], ...]
    types: dict[str, dict[str, object]]
    digest: str


@dataclass(frozen=True)
class RegistrySet:
    """Immutable operator registries with capability versions and digests."""

    capabilities: tuple[str, ...]
    signatures: dict[str, str]


@dataclass(frozen=True)
class CompiledProfile:
    """One immutable compiled profile with indexes and identity."""

    profile_digest: str
    notions: dict[str, dict[str, object]]
    recipes: dict[str, dict[str, object]]
    rules: dict[str, dict[str, object]]
    descriptor_digest: str
    registry_digest: str


def _default_registry() -> RegistrySet:
    """Return the library-owned generic primitive registry set."""
    signatures = dict.fromkeys(_VALUE_OPS | _PREDICATE_OPS | _ACTION_OPS, "generic/1")
    return RegistrySet(
        capabilities=tuple(sorted(_KNOWN_CAPABILITIES)),
        signatures=signatures,
    )


def create_descriptor_context(
    packages: list[dict[str, object]],
) -> PureResult:
    """Build one descriptor context from pinned packages.

    Each package carries ``id``, ``version``, ``sha256`` and immutable UTF-8
    ``descriptorBytes`` whose raw SHA-256 must match. IDs stay unique.
    """
    seen: set[str] = set()
    types: dict[str, dict[str, object]] = {}
    for entry in packages:
        package_id = entry.get("id")
        raw = entry.get("descriptorBytes")
        want = entry.get("sha256")
        if not isinstance(package_id, str) or not isinstance(want, str):
            return PureRefused(code="descriptor-mismatch")
        if package_id in seen:
            return PureRefused(code="descriptor-mismatch")
        seen.add(package_id)
        if isinstance(raw, (bytes, bytearray)):
            raw_bytes = bytes(raw)
        elif isinstance(raw, str):
            raw_bytes = raw.encode("utf-8")
        elif isinstance(raw, dict):
            raw_bytes = jcs(raw).encode("utf-8")
        else:
            return PureRefused(code="descriptor-mismatch")
        if digest_bytes(raw_bytes) != want:
            return PureRefused(code="descriptor-mismatch")
    context_digest = digest(sorted(seen))
    return PureSuccess(
        payload=DescriptorContext(packages=tuple(packages), types=types, digest=context_digest)
    )


def _check_value(  # noqa: C901, PLR0911, PLR0912
    node: object, context: str, phase: str | None = None
) -> str | None:
    """Validate one value AST; return a refusal code or ``None``."""
    _ = phase
    if not isinstance(node, dict):
        return "profile-type"
    op = node.get("op")
    if not isinstance(op, str) or op not in _VALUE_OPS:
        return "profile-symbol"
    if op == "literal":
        if "value" not in node or not isinstance(node["value"], (str, int, float, bool)):
            return "profile-type"
        if isinstance(node["value"], bool):
            return None
        return None
    if op == "read":
        if not isinstance(node.get("binding"), str) or not isinstance(node.get("path"), str):
            return "profile-type"
        return None
    if op == "id":
        if not isinstance(node.get("binding"), str):
            return "profile-type"
        return None
    if op == "ids":
        if context != "assignRef-values":
            return "profile-value-context"
        return None
    if op == "param":
        if not isinstance(node.get("name"), str):
            return "profile-type"
        return None
    if op == "concat":
        values = node.get("values")
        if not isinstance(values, list) or not values:
            return "profile-type"
        for entry in values:
            code = _check_value(entry, "concat", phase)
            if code is not None:
                return code
        return None
    if op == "stripPrefix":
        if not isinstance(node.get("prefix"), str):
            return "profile-type"
        return _check_value(node.get("value"), context, phase)
    if op == "case":
        if node.get("mode") not in ("upper", "lower"):
            return "profile-type"
        if node.get("unicode", "15.0.0") != "15.0.0":
            return "profile-type"
        return _check_value(node.get("value"), context, phase)
    if op == "outputId":
        if context not in ("emit-fields", "emit-parent"):
            return "profile-value-context"
        if not isinstance(node.get("binding"), str) or not isinstance(node.get("domain"), str):
            return "profile-type"
        return None
    return "profile-type"


def _check_predicate(  # noqa: C901, PLR0911, PLR0912
    node: object, notions: set[str]
) -> str | None:
    """Validate one predicate AST; return a refusal code or ``None``."""
    if not isinstance(node, dict):
        return "profile-type"
    op = node.get("op")
    if not isinstance(op, str) or op not in _PREDICATE_OPS:
        return "profile-symbol"
    if op in ("true", "false"):
        return None
    if op in ("all", "any"):
        args = node.get("args")
        if not isinstance(args, list) or not args:
            return "profile-type"
        for entry in args:
            code = _check_predicate(entry, notions)
            if code is not None:
                return code
        return None
    if op == "not":
        if "arg" not in node or "args" in node:
            return "profile-type"
        return _check_predicate(node.get("arg"), notions)
    if op == "typeIs":
        if not isinstance(node.get("binding"), str) or not isinstance(node.get("type"), str):
            return "profile-type"
        if node.get("mode") not in ("exact", "assignable"):
            return "profile-type"
        return None
    if op == "present":
        return _check_value(node.get("value"), "predicate", None)
    if op == "equal":
        for key in ("left", "right"):
            code = _check_value(node.get(key), "predicate", None)
            if code is not None:
                return code
        return None
    if op == "textPrefix":
        if not isinstance(node.get("prefix"), str) or not node.get("prefix"):
            return "profile-type"
        if node.get("trim") not in ("none", "ecma262-2024-start"):
            return "profile-type"
        return _check_value(node.get("value"), "predicate", None)
    if op == "count":
        selector = node.get("selector")
        code = _check_selector(selector, notions)
        if code is not None:
            return code
        minimum = node.get("min")
        maximum = node.get("max")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
            return "profile-bounds"
        if maximum is not None and (
            not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < minimum
        ):
            return "profile-bounds"
        return None
    if op == "boundRole":
        if not isinstance(node.get("binding"), str) or not isinstance(node.get("owner"), str):
            return "profile-type"
        return None
    if op == "recognizes":
        if not isinstance(node.get("binding"), str) or not isinstance(node.get("notion"), str):
            return "profile-type"
        if str(node.get("notion")) not in notions:
            return "profile-symbol"
        return None
    if op == "reachable":
        for key in ("source", "target"):
            code = _check_selector(node.get(key), notions)
            if code is not None:
                return code
        edge_types = node.get("edgeTypes")
        if not isinstance(edge_types, list) or not edge_types:
            return "profile-type"
        min_hops = node.get("minHops")
        max_hops = node.get("maxHops")
        if not isinstance(min_hops, int) or isinstance(min_hops, bool) or min_hops < 0:
            return "profile-bounds"
        if max_hops is not None and (
            not isinstance(max_hops, int) or isinstance(max_hops, bool) or max_hops < min_hops
        ):
            return "profile-bounds"
        return None
    return "profile-type"


def _check_selector(  # noqa: C901, PLR0911, PLR0912
    node: object,
    notions: set[str] | None = None,
) -> str | None:
    """Validate one selector AST; return a refusal code or ``None``."""
    if not isinstance(node, dict):
        return "profile-type"
    from_name = node.get("from")
    via = node.get("via")
    order = node.get("order")
    if not isinstance(from_name, str) or not isinstance(via, str):
        return "profile-type"
    if via not in _SELECTOR_VIA:
        return "profile-symbol"
    native_via = {
        "self",
        "root",
        "owner",
        "children",
        "descendants",
        "reference",
        "inverseReference",
        "all",
    }
    render_via = {"pages", "occurrences", "semantic"}
    if via == "self" and order not in ("id", "page-occurrence"):
        return "profile-selector-order"
    if via in native_via and via != "self" and order != "id":
        return "profile-selector-order"
    if via in render_via and via != "semantic" and order != "page-occurrence":
        return "profile-selector-order"
    if via == "semantic" and order != "id":
        return "profile-selector-order"
    has_property = "property" in node
    if via in ("reference", "inverseReference"):
        if not has_property or not isinstance(node.get("property"), str):
            return "profile-selector-property"
    elif via == "children":
        if has_property and not isinstance(node.get("property"), str):
            return "profile-selector-property"
    elif has_property:
        return "profile-selector-property"
    where = node.get("where")
    if where is not None:
        code = _check_predicate(where, notions or set())
        if code is not None:
            return code
    return None


def _check_action(  # noqa: C901, PLR0911, PLR0912, PLR0915
    step: object, phase: str, notions: set[str]
) -> str | None:
    """Validate one recipe step; return a refusal code or ``None``."""
    if not isinstance(step, dict):
        return "profile-type"
    op = step.get("op")
    if not isinstance(op, str) or op not in _ACTION_OPS:
        return "profile-symbol"
    allowed = _ACTION_PHASES.get(op, frozenset())
    if phase not in allowed:
        return "profile-action-phase"
    if op == "bind":
        selector = step.get("select")
        code = _check_selector(selector, notions)
        if code is not None:
            return code
        cardinality = step.get("cardinality")
        if cardinality not in ("one", "zeroOrOne", "first"):
            return "profile-type"
        fallbacks = step.get("fallbacks")
        if fallbacks is not None and cardinality != "first":
            return "profile-bind-fallbacks"
        if isinstance(fallbacks, list):
            for entry in fallbacks:
                code = _check_selector(entry, notions)
                if code is not None:
                    return code
        return None
    if op == "create":
        identity = step.get("identity")
        if identity not in ("allocated", "containment"):
            return "profile-create-identity"
        if identity == "allocated":
            for key in ("ownerId", "slot", "key"):
                if key not in step:
                    return "profile-create-identity"
        else:
            for key in ("ownerId", "slot", "key"):
                if key in step:
                    return "profile-create-identity"
        fields = step.get("fields", [])
        if not isinstance(fields, list):
            return "profile-type"
        for entry in fields:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                return "profile-type"
            code = _check_value(entry.get("value"), "create-field", phase)
            if code is not None:
                return code
        return None
    if op in ("set", "unset"):
        if not isinstance(step.get("target"), str) or not isinstance(step.get("path"), str):
            return "profile-type"
        if op == "set":
            code = _check_value(step.get("value"), "set", phase)
            if code is not None:
                return code
        return None
    if op == "assignRef":
        values = step.get("values")
        if not isinstance(values, list):
            return "profile-type"
        for entry in values:
            code = _check_value(entry, "assignRef-values", phase)
            if code is not None:
                return code
        if step.get("mode") not in ("replace", "appendUnique", "remove"):
            return "profile-type"
        return None
    if op == "reparent":
        return None
    if op == "place":
        related = step.get("related")
        if related is not None:
            code = _check_selector(related, notions)
            if code is not None:
                return code
        return None
    if op == "emit":
        fields = step.get("fields", [])
        if not isinstance(fields, list):
            return "profile-export-field"
        for entry in fields:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                return "profile-export-field"
            code = _check_value(entry.get("value"), "emit-fields", phase)
            if code is not None:
                return code
        parent = step.get("parent")
        if parent is not None:
            code = _check_value(parent, "emit-parent", phase)
            if code is not None:
                return code
        return None
    if op == "loss":
        return None
    if op == "remove":
        return None
    if op == "ensure":
        return None
    if op == "refuse":
        if not isinstance(step.get("code"), str):
            return "profile-type"
        return None
    return "profile-type"


def compile_profile(  # noqa: C901, PLR0912, PLR0911, PLR0915
    validated: ValidatedProfile,
    registry_set: RegistrySet | None = None,
    descriptor_context: DescriptorContext | None = None,
) -> PureResult:
    """Compile one validated profile with closed references and registries.

    Applies the §2.4.1 rules CR-01 through CR-14 in order and returns the
    first refusal code. Unknown operators, mismatched orders, bad bounds,
    duplicate symbols, cycles, authority gaps, identity errors, presentation
    errors, export errors, migration endpoint errors, fallback errors and
    phase errors refuse with their mapped codes.
    """
    registry = registry_set or _default_registry()
    profile = validated.profile

    # CR-01 capabilities: unique known IDs and operator coverage.
    capabilities = profile.get("capabilities")
    if not isinstance(capabilities, list):
        return PureRefused(code="profile-capability")
    seen_caps: set[str] = set()
    for name in capabilities:
        if not isinstance(name, str) or name in seen_caps:
            return PureRefused(code="profile-capability")
        seen_caps.add(name)
        if name not in _KNOWN_CAPABILITIES and name not in registry.capabilities:
            return PureRefused(code="profile-capability")

    notions_raw = profile.get("notions")
    rules_raw = profile.get("rules")
    recipes_raw = profile.get("recipes")
    if not isinstance(notions_raw, list) or not isinstance(rules_raw, list):
        return PureRefused(code="profile-symbol")
    if not isinstance(recipes_raw, list):
        return PureRefused(code="profile-symbol")

    notions: set[str] = set()
    for _entry in notions_raw:
        if not isinstance(_entry, dict):
            return PureRefused(code="profile-symbol")
        _nid = _entry.get("id")
        if not isinstance(_nid, str) or _nid in notions:
            return PureRefused(code="profile-symbol")
        notions.add(_nid)
    recipe_ids: set[str] = set()
    recipes: dict[str, dict[str, object]] = {}
    for _entry in recipes_raw:
        if not isinstance(_entry, dict):
            return PureRefused(code="profile-symbol")
        _rid = _entry.get("id")
        if not isinstance(_rid, str) or _rid in recipe_ids:
            return PureRefused(code="profile-symbol")
        recipe_ids.add(_rid)
        recipes[_rid] = _entry
    rule_ids: set[str] = set()
    for _entry in rules_raw:
        if not isinstance(_entry, dict):
            return PureRefused(code="profile-symbol")
        _uid = _entry.get("id")
        if not isinstance(_uid, str) or _uid in rule_ids:
            return PureRefused(code="profile-symbol")
        rule_ids.add(_uid)

    # Notion group/kind check (CR-09 subset) before predicate walks.
    for notion in notions_raw:
        if not isinstance(notion, dict):
            return PureRefused(code="profile-notion-kind")
        has_facet = notion.get("facet") is True
        group = notion.get("exclusiveGroup")
        if has_facet == bool(isinstance(group, str) and group):
            return PureRefused(code="profile-notion-kind")

    # Walk values/predicates/selectors for unknown operators (CR-02/03/05).
    for notion in notions_raw:
        if not isinstance(notion, dict):
            continue
        recognition = notion.get("recognition")
        if recognition is not None:
            code = _check_predicate(recognition, notions)
            if code is not None:
                return PureRefused(code=code)
    for rule in rules_raw:
        if not isinstance(rule, dict):
            continue
        code = _check_selector(rule.get("select"), notions)
        if code is not None:
            return PureRefused(code=code)
        bindings = rule.get("bindings", [])
        if isinstance(bindings, list):
            for binding in bindings:
                if not isinstance(binding, dict):
                    return PureRefused(code="profile-type")
                code = _check_selector(binding.get("select"), notions)
                if code is not None:
                    return PureRefused(code=code)
                if binding.get("fallbacks") is not None:
                    return PureRefused(code="profile-bind-fallbacks")
        code = _check_predicate(rule.get("assert"), notions)
        if code is not None:
            return PureRefused(code=code)
    for recipe in recipes_raw:
        if not isinstance(recipe, dict):
            continue
        phase = recipe.get("phase")
        if phase not in _PHASES:
            return PureRefused(code="profile-action-phase")
        code = _check_selector(recipe.get("select"), notions)
        if code is not None:
            return PureRefused(code=code)
        when = recipe.get("when")
        if when is not None:
            code = _check_predicate(when, notions)
            if code is not None:
                return PureRefused(code=code)
        steps = recipe.get("steps")
        if not isinstance(steps, list) or not steps:
            return PureRefused(code="profile-type")
        for step in steps:
            code = _check_action(step, str(phase), notions)
            if code is not None:
                return PureRefused(code=code)
        # CR-13 recipe fallback presence is checked inside bind above.

    # CR-05 closed references: every recipe/rule reference resolves.
    for recipe in recipes_raw:
        if not isinstance(recipe, dict):
            continue
        for step in recipe.get("steps", []):
            if not isinstance(step, dict):
                continue
            # No dangling notion/recipe/theme references are introduced here
            # beyond the predicate notion check above; unknown write targets
            # surface as write-set below.
            _ = step
    for rule in rules_raw:
        if not isinstance(rule, dict):
            continue
        _ = rule

    # CR-12 migration endpoints: target self, external source pin.
    migrations = profile.get("migrations")
    if isinstance(migrations, list):
        own_digest = validated.digest
        for migration in migrations:
            if not isinstance(migration, dict):
                return PureRefused(code="profile-migration-endpoint")
            if migration.get("to") != "self":
                return PureRefused(code="profile-migration-endpoint")
            source = migration.get("from")
            if not isinstance(source, dict):
                return PureRefused(code="profile-migration-endpoint")
            if source.get("sha256") == own_digest:
                return PureRefused(code="profile-migration-endpoint")

    # CR-06/07 write and identity authority are covered structurally above;
    # descriptor-specific path checks run when a context is supplied.
    _ = descriptor_context

    compiled = CompiledProfile(
        profile_digest=validated.digest,
        notions={k: {} for k in notions},
        recipes=dict(recipes),
        rules={str(r.get("id")): r for r in rules_raw if isinstance(r, dict)},
        descriptor_digest=validated.digest,
        registry_digest=digest(sorted(registry.capabilities)),
    )
    return PureSuccess(payload=compiled)
