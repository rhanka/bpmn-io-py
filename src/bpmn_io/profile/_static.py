"""Static admission typing core (prototype of the PY-R4 ruling, R5 order).

Line-by-line transcription of ``compiler-static.ts`` (bpmn-canvas fec4dae):
binding domains, ``field``/``read``/``value``/``narrow``/``predicate``/
``select``/``bind``/``write``. Failures raise :class:`StaticRefusal` with the
JS code; callers convert at their boundary. ``Typing.metadata_free`` models
the Python-only metadata-free compile: native domains are unknown, checks
that need descriptors are undecidable (skipped), and an undecidable select
defers the rest of its node to the activation re-check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NoReturn

__all__ = ["Domain", "StaticRefusal", "Typing"]

_PATH = re.compile(r"(?:/(?:[^~/]|~[01])*)+")
RENDER_TYPES = ("RenderData", "PageHandle", "OccurrenceHandle")
_RENDER_FIELDS: dict[str, dict[str, str]] = {
    "RenderData": {},
    "PageHandle": {
        "/pageId": "string",
        "/name": "string",
        "/order": "number",
        "/semanticRootId": "string",
        "/bounds/x": "number",
        "/bounds/y": "number",
        "/bounds/width": "number",
        "/bounds/height": "number",
    },
    "OccurrenceHandle": {
        "/pageId": "string",
        "/occurrenceKey": "string",
        "/semanticId": "string",
        "/emittedType": "string",
        "/label/text": "string",
        "/bounds/x": "number",
        "/bounds/y": "number",
        "/bounds/width": "number",
        "/bounds/height": "number",
        "/role": "string",
    },
}


#: Sealed-forced deviations (see PY-R4 ruling §8); False reproduces JS exactly.
SEALED_GENERIC_UNKNOWN = True
SEALED_OCCURRENCE_PATHS = frozenset(
    {"/sourceOccurrence/occurrenceKey", "/targetOccurrence/occurrenceKey", "/glyphId"}
)


class StaticRefusal(Exception):  # noqa: N818 - mirrors failContract
    """One static admission refusal carrying its closed code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _Defer(Exception):  # noqa: N818
    """Metadata-free: the rest of this node is decided at activation."""


def _defer() -> NoReturn:
    """Defer the rest of one selector node to activation (metadata-free)."""
    raise _Defer


def fail(code: str) -> NoReturn:
    raise StaticRefusal(code)


@dataclass(frozen=True)
class Domain:
    """A binding domain: descriptor or render record types, generic flag."""

    types: tuple[str, ...]
    generic: bool = False
    known: bool = True

    @property
    def head(self) -> str | None:
        return self.types[0] if self.types else None


RENDER_DATA = Domain(("RenderData",))
PAGE = Domain(("PageHandle",))
OCCURRENCE = Domain(("OccurrenceHandle",))
UNKNOWN = Domain((), generic=True, known=False)


@dataclass(frozen=True)
class FieldInfo:
    type: str
    field: str
    kind: str
    targets: tuple[str, ...]
    value_type: str


def _unescape(part: str) -> str:
    return part.replace("~1", "/").replace("~0", "~")


def pointer_key(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


@dataclass
class Typing:
    """Admitted authority for one static walk (JS ``CompilerAuthority``)."""

    descriptors: dict[str, dict[str, object]] | None
    native_types: tuple[str, ...]
    id_ref_scalars: frozenset[str] = frozenset()
    notions: dict[str, dict[str, object]] = field(default_factory=dict)
    # (type, field, kind) -> producers; None = no base (grant check undecidable).
    grants: dict[tuple[str, str, str], frozenset[str]] | None = None
    supertypes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # (type, field) of the base fields; None without a base (undecidable).
    base_fields: frozenset[tuple[str, str]] | None = None

    @property
    def metadata_free(self) -> bool:
        return self.descriptors is None

    # -- domains ---------------------------------------------------------
    def native(self) -> Domain:
        if self.metadata_free:
            return UNKNOWN
        return Domain(self.native_types, generic=True)

    def elements(self) -> Domain:
        if self.metadata_free or self.descriptors is None:
            return UNKNOWN
        return Domain(tuple(t for t in self.native_types if self._has_id(t)), generic=True)

    def root(self) -> Domain:
        return UNKNOWN if self.metadata_free else Domain(("bpmn:Definitions",))

    def base_env(self) -> dict[str, Domain]:
        return {"root": self.root(), "self": self.native(), "bindingOwner": self.elements()}

    def _desc(self, name: str) -> dict[str, object] | None:
        if self.descriptors is None:
            return None
        found = self.descriptors.get(name)
        return found if isinstance(found, dict) else None

    def _has_id(self, name: str) -> bool:
        d = self._desc(name)
        return bool(d is not None and d.get("id") is True)

    def _declares(self, name: str, member: str) -> bool:
        return (
            member in self._refs(name)
            or member in self._containment(name)
            or member in self._scalars(name)
        )

    def _is_descriptor(self, name: str) -> bool:
        return self._desc(name) is not None

    def _refs(self, name: str) -> dict[str, tuple[str, ...]]:
        d = self._desc(name) or {}
        refs = d.get("references", {})
        return refs if isinstance(refs, dict) else {}

    def _containment(self, name: str) -> dict[str, tuple[str, ...]]:
        d = self._desc(name) or {}
        cont = d.get("containment", {})
        return cont if isinstance(cont, dict) else {}

    def _scalars(self, name: str) -> tuple[str, ...]:
        d = self._desc(name) or {}
        sc = d.get("scalars", ())
        return tuple(sc) if isinstance(sc, (list, tuple)) else ()

    def _scalar_type(self, name: str, member: str) -> str:
        d = self._desc(name) or {}
        st = d.get("scalarTypes", {})
        if isinstance(st, dict) and isinstance(st.get(member), str):
            return str(st[member])
        return "scalar"

    # -- JS helpers ---------------------------------------------------------
    def type_matches(self, actual: str, expected: str, mode: str) -> bool:
        if not self._is_descriptor(actual) or not self._is_descriptor(expected):
            fail("profile-type")
        if actual == expected:
            return True
        if mode == "exact":
            return False
        seen: set[str] = set()

        def inherits(name: str) -> bool:
            if name in seen:
                return False
            seen.add(name)
            return any(
                parent == expected or inherits(parent) for parent in self.supertypes.get(name, ())
            )

        return inherits(actual)

    def check_type(self, name: object) -> None:
        """JS ``type``: a declared descriptor type admitted by the base."""
        if self.metadata_free:
            return
        if (
            not isinstance(name, str)
            or not self._is_descriptor(name)
            or name not in self.native_types
        ):
            fail("profile-type")

    @staticmethod
    def binding(env: dict[str, Domain], name: object) -> Domain:
        if not isinstance(name, str) or name not in env:
            fail("profile-symbol")
        return env[name]

    def symbol_notion(self, name: object) -> dict[str, object]:
        if not isinstance(name, str) or name not in self.notions:
            fail("profile-symbol")
        return self.notions[name]

    @staticmethod
    def expect_type(actual: str, expected: str, code: str = "profile-type") -> None:
        if actual not in (expected, "scalar"):
            fail(code)

    # -- field / read ---------------------------------------------------------
    def field(  # noqa: C901 - one branch per path position and kind
        self, domain: Domain, path: object, kind: str | None = None
    ) -> list[FieldInfo]:
        if not isinstance(path, str) or not _PATH.fullmatch(path):
            fail("profile-type")
        if not domain.known:
            raise _Undecided
        parts = [_unescape(p) for p in str(path)[1:].split("/")]
        names: list[str] = list(domain.types)
        for i, name in enumerate(parts):
            fields: list[FieldInfo] = []
            for t in names:
                d = self._desc(t)
                if d is None:
                    continue
                refs, cont = self._refs(t), self._containment(t)
                if name in refs:
                    fields.append(
                        FieldInfo(
                            t, name, "reference", tuple(refs[name]), self._scalar_type(t, name)
                        )
                    )
                elif name in cont:
                    fields.append(
                        FieldInfo(
                            t, name, "containment", tuple(cont[name]), self._scalar_type(t, name)
                        )
                    )
                elif name in self._scalars(t):
                    fields.append(FieldInfo(t, name, "scalar", (), self._scalar_type(t, name)))
            if not fields or (not domain.generic and len(fields) != len(names)):
                fail("profile-type")
            if i == len(parts) - 1:
                if kind is not None and any(f.kind != kind for f in fields):
                    fail("profile-type")
                return fields
            if any(f.kind != "containment" or len(f.targets) != 1 for f in fields):
                fail("profile-type")
            names = [t for f in fields for t in f.targets]
        fail("profile-type")

    def read(self, domain: Domain, path: object) -> str:
        record = domain.types[0] if domain.known and len(domain.types) == 1 else ""
        if record in _RENDER_FIELDS:
            found = _RENDER_FIELDS[record].get(path) if isinstance(path, str) else None
            if found is None and record == "OccurrenceHandle" and path in SEALED_OCCURRENCE_PATHS:
                found = "string"  # SF-2 (sealed-forced, owner decision O-7)
            if found is None:
                fail("profile-type")
            return str(found)
        if (
            SEALED_GENERIC_UNKNOWN
            and domain.known
            and domain.generic
            and isinstance(path, str)
            and _PATH.fullmatch(path)
            and not any(self._declares(t, _unescape(path[1:].split("/")[0])) for t in domain.types)
        ):
            return "scalar"  # SF-1 (sealed-forced, owner decisions O-1 / O-3 generic)
        try:
            fields = self.field(domain, path)
        except _Undecided:
            return "scalar"
        if any(f.kind == "containment" for f in fields):
            fail("profile-type")
        kinds = {"string" if f.kind == "reference" else f.value_type for f in fields}
        return next(iter(kinds)) if len(kinds) == 1 else "scalar"

    # -- value ---------------------------------------------------------------------
    def value(  # noqa: C901, PLR0911, PLR0912 - one branch per value op
        self, v: object, env: dict[str, Domain], params: dict[str, str], location: str
    ) -> str:
        node = v if isinstance(v, dict) else {}
        op = node.get("op")
        if op == "literal":
            val = node.get("value")
            if isinstance(val, bool):
                return "boolean"
            if isinstance(val, (int, float)):
                return "number"
            if isinstance(val, str):
                return "string"
            return "undefined"
        if op == "param":
            name = node.get("name")
            if not isinstance(name, str) or name not in params:
                fail("profile-symbol")
            t = params[str(name)]
            return "string" if t == "element" else t
        if op == "read":
            return self.read(self.binding(env, node.get("binding")), node.get("path"))
        if op == "id":
            d = self.binding(env, node.get("binding"))
            if d.known and all(not self._has_id(t) for t in d.types):
                fail("profile-type")
            if not d.known and self.metadata_free:
                return "string"
            return "string"
        if op == "concat":
            values = node.get("values")
            for part in values if isinstance(values, list) else []:
                self.expect_type(self.value(part, env, params, location), "string")
            return "string"
        if op in ("case", "stripPrefix"):
            self.expect_type(self.value(node.get("value"), env, params, location), "string")
            return "string"
        if op == "ids":
            if location != "assignRef.values":
                fail("profile-value-context")
            d = self.select(node.get("select"), env, params, location)
            if d.known and any(not self._has_id(t) for t in d.types):
                fail("profile-type")
            return "ids"
        if op == "outputId":
            if not location.startswith("emit."):
                fail("profile-value-context")
            d = self.binding(env, node.get("binding"))
            dom = node.get("domain")
            if (
                "RenderData" in d.types
                or ("PageHandle" in d.types and dom != "page")
                or ("OccurrenceHandle" in d.types and dom == "page")
            ):
                fail("profile-type")
            return "string"
        fail("profile-schema")

    # -- narrow / predicate -----------------------------------------------------------------
    def narrow(self, ast: object, env: dict[str, Domain]) -> dict[str, Domain]:
        out = dict(env)
        node = ast if isinstance(ast, dict) else {}
        op = node.get("op")
        if op == "typeIs":
            self.check_type(node.get("type"))
            old = self.binding(out, node.get("binding"))
            if not old.known:
                out[str(node.get("binding"))] = UNKNOWN
            else:
                out[str(node.get("binding"))] = Domain(
                    tuple(
                        t
                        for t in old.types
                        if self._is_descriptor(t)
                        and self.type_matches(t, str(node.get("type")), str(node.get("mode")))
                    )
                )
        elif op == "recognizes":
            n = self.symbol_notion(node.get("notion"))
            old = self.binding(out, node.get("binding"))
            native_types = n.get("nativeTypes", [])
            if not old.known:
                out[str(node.get("binding"))] = UNKNOWN
            else:
                out[str(node.get("binding"))] = Domain(
                    tuple(
                        t for t in old.types if isinstance(native_types, list) and t in native_types
                    )
                )
        elif op == "all":
            current = out
            for a in node.get("args", []) if isinstance(node.get("args"), list) else []:
                current = self.narrow(a, current)
            return current
        return out

    def predicate(  # noqa: C901, PLR0911, PLR0912 - one branch per predicate op
        self, ast: object, env: dict[str, Domain], params: dict[str, str], location: str
    ) -> None:
        node = ast if isinstance(ast, dict) else {}
        op = node.get("op")
        if op in ("true", "false"):
            return
        if op == "all":
            refined = self.narrow(node, env)
            for a in node.get("args", []):
                self.predicate(a, refined, params, location)
            return
        if op == "any":
            for a in node.get("args", []):
                self.predicate(a, dict(env), params, location)
            return
        if op == "not":
            self.predicate(node.get("arg"), env, params, location)
            return
        if op in ("typeIs", "recognizes"):
            d = self.binding(env, node.get("binding"))
            if (
                d.known
                and any(not self._is_descriptor(t) for t in d.types)
                and not self.metadata_free
            ):
                fail("profile-type")
            if self.metadata_free and d.known and any(t in RENDER_TYPES for t in d.types):
                fail("profile-type")
            if op == "typeIs":
                self.check_type(node.get("type"))
            else:
                self.symbol_notion(node.get("notion"))
            return
        if op == "boundRole":
            self.binding(env, node.get("binding"))
            self.binding(env, node.get("owner"))
            return
        if op == "present":
            self.value(node.get("value"), env, params, "predicate")
            return
        if op == "equal":
            self.value(node.get("left"), env, params, "predicate")
            self.value(node.get("right"), env, params, "predicate")
            return
        if op == "textPrefix":
            self.expect_type(self.value(node.get("value"), env, params, "predicate"), "string")
            return
        if op == "count":
            self.select(node.get("select"), env, params, location)
            return
        if op == "reachable":
            self.select(node.get("from"), env, params, location)
            self.select(node.get("to"), env, params, location)
            for t in node.get("edgeTypes", []):
                self.check_type(t)
                if self.metadata_free:
                    continue
                self.field(Domain((str(t),)), "/sourceRef", "reference")
                self.field(Domain((str(t),)), "/targetRef", "reference")
            return
        fail("profile-schema")

    # -- select ------------------------------------------------------------------------------
    def select(  # noqa: C901, PLR0912, PLR0915 - one branch per selector via
        self, s: object, env: dict[str, Domain], params: dict[str, str], location: str
    ) -> Domain:
        node = s if isinstance(s, dict) else {}
        frm = self.binding(env, node.get("from"))
        domain = frm.head if frm.known else "#native"
        result = frm
        order = "id"
        exporting = location in ("export", "render")
        via = node.get("via")
        prop = node.get("property")
        non_descriptor = frm.known and any(
            (t in RENDER_TYPES) if self.metadata_free else (not self._is_descriptor(t))
            for t in frm.types
        )
        if non_descriptor and via not in ("pages", "occurrences", "semantic", "self", "reference"):
            fail("profile-type")
        try:
            if via == "pages":
                if not exporting or domain != "RenderData":
                    fail("profile-type")
                result, order = PAGE, "page-occurrence"
            elif via == "occurrences":
                if not exporting or domain not in ("RenderData", "PageHandle"):
                    fail("profile-type")
                result, order = OCCURRENCE, "page-occurrence"
            elif via == "semantic":
                if not exporting or domain != "OccurrenceHandle":
                    native_domain = domain is not None and domain not in RENDER_TYPES
                    if not native_domain or location != "capability":
                        fail("profile-type")
                result = self.native()
            elif via == "self":
                if domain in ("PageHandle", "OccurrenceHandle"):
                    order = "page-occurrence"
            elif via == "root":
                result = self.root()
            elif via == "all":
                result = self.native()
            elif via == "owner":
                if not frm.known:
                    result = UNKNOWN
                else:
                    result = Domain(
                        tuple(
                            t
                            for t in self.native_types
                            if any(
                                any(
                                    self.type_matches(actual, target, "assignable")
                                    for actual in frm.types
                                )
                                for ts in self._containment(t).values()
                                for target in ts
                            )
                        ),
                        generic=True,
                    )
            elif via in ("children", "descendants"):
                if prop:
                    try:
                        targets = [
                            t
                            for f in self.field(frm, "/" + pointer_key(str(prop)), "containment")
                            for t in f.targets
                        ]
                    except _Undecided:
                        raise _Defer from None
                elif frm.known:
                    targets = [
                        t for ft in frm.types for ts in self._containment(ft).values() for t in ts
                    ]
                else:
                    targets = []
                if via == "descendants":
                    result = self.native()
                else:
                    result = Domain(tuple(dict.fromkeys(targets))) if frm.known else UNKNOWN
            elif via in ("reference", "inverseReference"):
                if domain == "OccurrenceHandle" and via == "reference":
                    if not exporting or prop not in ("sourceOccurrence", "targetOccurrence"):
                        fail("profile-selector-property")
                    result, order = OCCURRENCE, "page-occurrence"
                else:
                    names = frm if via == "reference" else self.native()
                    if not names.known:
                        _defer()
                    refs: list[tuple[str, tuple[str, ...]]] = []
                    for t in names.types:
                        if self._desc(t) is None:
                            continue
                        r = self._refs(t)
                        if isinstance(prop, str) and prop in r:
                            refs.append((t, tuple(r[prop])))
                        elif f"{t}.{prop}" in self.id_ref_scalars:
                            refs.append((t, self.native_types))
                    if not refs:
                        fail("profile-selector-property")
                    if via == "reference":
                        result = Domain(tuple(dict.fromkeys(x for _, ts in refs for x in ts)))
                    else:
                        result = Domain(
                            tuple(
                                dict.fromkeys(
                                    t
                                    for t, ts in refs
                                    if any(
                                        any(
                                            self.type_matches(actual, target, "assignable")
                                            for actual in frm.types
                                        )
                                        for target in ts
                                    )
                                )
                            )
                        )
            else:
                fail("profile-type")
        except _Defer:
            return UNKNOWN
        if node.get("order") != order:
            fail("profile-selector-order")
        if "property" in node and via not in ("children", "reference", "inverseReference"):
            fail("profile-selector-property")
        local = dict(env)
        local["self"] = result
        self.predicate(node.get("where"), local, params, location)
        return self.narrow(node.get("where"), local)["self"]

    def bind(
        self, step: dict[str, object], env: dict[str, Domain], params: dict[str, str], phase: str
    ) -> None:
        if step.get("as") in env:
            fail("profile-symbol")
        selected = self.select(step.get("select"), env, params, phase)
        raw_fallbacks = step.get("fallbacks", [])
        for fallback in raw_fallbacks if isinstance(raw_fallbacks, list) else []:
            d = self.select(fallback, env, params, phase)
            if selected.known and d.known:
                selected = Domain(tuple(dict.fromkeys([*selected.types, *d.types])))
            else:
                selected = UNKNOWN
        env[str(step.get("as"))] = selected

    def write(self, domain: Domain, path: object, kind: str, phase: str) -> None:
        try:
            fields = self.field(domain, path, kind)
        except _Undecided:
            return
        if self.grants is None:
            return
        actor = "code" if phase in ("complete", "normalize") else "editor"
        for f in fields:
            grant = self.grants.get((f.type, f.field, kind))
            if grant is None or actor not in grant:
                fail("profile-producer")


class _Undecided(Exception):  # noqa: N818
    """A descriptor-dependent check in metadata-free mode."""


# ---------------------------------------------------------------- structure (compiler.ts:148-265)
_VALUE_OPS = ("literal", "read", "id", "ids", "param", "concat", "stripPrefix", "case", "outputId")
_PREDICATE_OPS = (
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
)
_VIAS = (
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
)
_EMIT_LOCATION = re.compile(r"emit\.(?:fields|parent)(?:\.|$)")


def _record(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        fail("profile-schema")
    return value


def _safe_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and abs(value) <= 2**53 - 1


def structure_value(value: object, location: str) -> None:  # noqa: C901
    s = _record(value)
    op = s.get("op")
    if not isinstance(op, str) or op not in _VALUE_OPS:
        fail("profile-schema")
    if op == "literal":
        lit = s.get("value")
        if not isinstance(lit, (str, int, float)) or (isinstance(lit, bool) and False):
            fail("profile-schema")
        return
    if op == "ids":
        if location != "assignRef.values":
            fail("profile-value-context")
        structure_selector(_record(s.get("select")))
        return
    if op == "concat":
        values = s.get("values")
        if not isinstance(values, list) or not values:
            fail("profile-schema")
        for item in values:
            structure_value(item, location)
        return
    if op in ("stripPrefix", "case"):
        structure_value(s.get("value"), location)
        return
    if op == "outputId" and not _EMIT_LOCATION.match(location):
        fail("profile-value-context")


def structure_selector(selector: object) -> None:
    s = _record(selector)
    if not isinstance(s.get("from"), str) or not s.get("from"):
        fail("profile-schema")
    if s.get("via") not in _VIAS:
        fail("profile-schema")
    if s.get("via") in ("reference", "inverseReference"):
        if not isinstance(s.get("property"), str) or not s.get("property"):
            fail("profile-selector-property")
    elif "property" in s and s.get("via") != "children":
        fail("profile-selector-property")
    if s.get("order") not in ("id", "page-occurrence"):
        fail("profile-schema")
    structure_predicate(s.get("where"))


def structure_predicate(predicate: object) -> None:  # noqa: C901, PLR0912
    s = _record(predicate)
    op = s.get("op")
    if not isinstance(op, str) or op not in _PREDICATE_OPS:
        fail("profile-schema")
    if op in ("all", "any"):
        args = s.get("args")
        if not isinstance(args, list) or not args:
            fail("profile-schema")
        for a in args:
            structure_predicate(a)
    elif op == "not":
        if not isinstance(s.get("arg"), dict) or isinstance(s.get("args"), list):
            fail("profile-schema")
        structure_predicate(s.get("arg"))
    elif op == "present":
        structure_value(s.get("value"), "predicate")
    elif op == "equal":
        structure_value(s.get("left"), "predicate")
        structure_value(s.get("right"), "predicate")
    elif op == "textPrefix":
        structure_value(s.get("value"), "predicate")
    elif op == "count":
        structure_selector(_record(s.get("select")))
        mn, mx = s.get("min"), s.get("max")
        if not _safe_int(mn) or mn < 0:  # type: ignore[operator]
            fail("profile-bounds")
        if mx is not None and (not _safe_int(mx) or mx < mn):  # type: ignore[operator]
            fail("profile-bounds")
    elif op == "reachable":
        structure_selector(_record(s.get("from")))
        structure_selector(_record(s.get("to")))
        mn, mx = s.get("minHops"), s.get("maxHops")
        if not _safe_int(mn) or mn < 0:  # type: ignore[operator]
            fail("profile-bounds")
        if mx is not None and (not _safe_int(mx) or mx < mn):  # type: ignore[operator]
            fail("profile-bounds")


def structure_bind(step: object) -> None:
    s = _record(step)
    structure_selector(s.get("select"))
    if "fallbacks" in s:
        if s.get("cardinality") != "first":
            fail("profile-bind-fallbacks")
        raw_fallbacks = s.get("fallbacks", [])
        for fb in raw_fallbacks if isinstance(raw_fallbacks, list) else []:
            structure_selector(fb)


_ACTION_OPS = (
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
)
_SUPPORT_TYPES = ("bpmn:Collaboration", "bpmn:Participant", "bpmn:LaneSet", "bpmn:Lane")
_EMIT_OPTIONAL = {
    "page": (),
    "node": (
        "name",
        "shape",
        "fill",
        "stroke",
        "textColor",
        "fontFamily",
        "fontSize",
        "strokeWidth",
    ),
    "edge": ("name", "stroke", "dash", "arrow", "strokeWidth"),
    "label": (),
    "metadata": (),
}
_ACTION_PHASES = {
    "bind": (
        "create",
        "edit",
        "reference",
        "complete",
        "normalize",
        "convert",
        "migrate",
        "export",
    ),
    "refuse": (
        "create",
        "edit",
        "reference",
        "complete",
        "normalize",
        "convert",
        "migrate",
        "export",
    ),
    "create": ("create", "edit", "reference", "complete", "convert", "migrate"),
    "ensure": ("normalize",),
    "set": ("create", "edit", "reference", "complete", "normalize", "convert", "migrate"),
    "unset": ("create", "edit", "reference", "complete", "normalize", "convert", "migrate"),
    "assignRef": ("create", "edit", "reference", "complete", "normalize", "convert", "migrate"),
    "reparent": ("edit", "convert", "migrate", "normalize"),
    "place": ("normalize",),
    "emit": ("export",),
    "loss": ("export",),
    "remove": ("edit", "convert", "migrate"),
}


def _text(s: dict[str, object], key: str, code: str = "profile-schema") -> None:
    if not isinstance(s.get(key), str) or not s.get(key):
        fail(code)


def structure_action(step: object) -> None:  # noqa: C901, PLR0912, PLR0915
    s = _record(step)
    op = s.get("op")
    if op not in _ACTION_OPS:
        fail("profile-schema")
    if op == "bind":
        structure_bind(s)
    elif op == "refuse":
        _text(s, "code")
        _text(s, "target")
    elif op == "create":
        for k in ("as", "type", "parent", "property"):
            _text(s, k)
        if s.get("identity") == "allocated":
            if not isinstance(s.get("slot"), str) or not s.get("slot"):
                fail("profile-create-identity")
            if not isinstance(s.get("ownerId"), dict) or not isinstance(s.get("key"), dict):
                fail("profile-create-identity")
        elif any(s.get(k) is not None for k in ("ownerId", "slot", "key")):
            fail("profile-create-identity")
        for f in _list(s.get("fields")):
            fr = _record(f)
            _text(fr, "name")
            structure_value(fr.get("value"), "create.fields")
    elif op == "ensure":
        for k in ("as", "type", "parent", "property", "owner", "role"):
            _text(s, k)
        if s.get("type") not in _SUPPORT_TYPES:
            fail("profile-producer")
        if not isinstance(s.get("slot"), str) or not s.get("slot"):
            fail("profile-create-identity")
        structure_value(s.get("ownerId"), "ensure.ownerId")
        structure_value(s.get("key"), "ensure.key")
        for f in _list(s.get("fields")):
            fr = _record(f)
            _text(fr, "name")
            structure_value(fr.get("value"), "ensure.fields")
    elif op in ("set", "unset"):
        _text(s, "target")
        _text(s, "path")
        if str(s.get("path")).split("/")[-1] == "id":
            fail("profile-producer")
        if op == "set":
            structure_value(s.get("value"), "set.value")
    elif op == "assignRef":
        _text(s, "target")
        _text(s, "path")
        for v in _list(s.get("values")):
            structure_value(v, "assignRef.values")
    elif op == "reparent":
        for k in ("target", "parent", "property"):
            _text(s, k)
    elif op == "place":
        for k in ("target", "owner", "region"):
            _text(s, k)
    elif op == "emit":
        _text(s, "as")
        kind = str(s.get("kind"))
        names: set[object] = set()
        for f in _list(s.get("fields")):
            fr = _record(f)
            if not isinstance(fr.get("name"), str) or fr.get("name") in names:
                fail("profile-export-field")
            names.add(fr.get("name"))
            if fr.get("name") not in (*_EMIT_REQUIRED.get(kind, ()), *_EMIT_OPTIONAL.get(kind, ())):
                fail("profile-export-field")
            structure_value(fr.get("value"), "emit.fields")
        if any(n not in names for n in _EMIT_REQUIRED.get(kind, ())):
            fail("profile-export-field")
        if kind == "page" and "parent" in s:
            fail("profile-type")
    elif op == "loss":
        _text(s, "target")
    elif op == "remove":
        _text(s, "target")
        structure_selector(_record(s.get("dependents")))


def _required_writes(  # noqa: C901, PLR0911 - one branch per recipe step op
    step: dict[str, object],
) -> list[str]:
    import json  # noqa: PLC0415

    def w(binding: object, path: object, mode: str) -> str:
        return json.dumps({"binding": binding, "mode": mode, "path": path}, sort_keys=True)

    op = step.get("op")
    prop = "/" + pointer_key(str(step.get("property")))
    if op in ("bind", "refuse"):
        return []
    if op == "create":
        return [w(step.get("parent"), prop, "create")]
    if op == "ensure":
        return [w(step.get("parent"), prop, "create"), w("envelope", "/bindings", "binding")]
    if op in ("set", "unset"):
        return [w(step.get("target"), step.get("path"), str(op))]
    if op == "assignRef":
        return [w(step.get("target"), step.get("path"), "reference")]
    if op == "reparent":
        return [w(step.get("target"), "", "reparent"), w(step.get("parent"), prop, "reparent")]
    if op == "place":
        return [w(step.get("target"), "", "placement")]
    if op == "emit":
        return [w("self", "", "artifact")]
    if op == "loss":
        return [w(step.get("target"), "", "report")]
    if op == "remove":
        return [w(step.get("target"), "", "remove")]
    fail("profile-schema")


def structure_recipe(recipe: object) -> None:
    """compiler.ts checkRecipeStructure (select, when, steps, write set)."""
    import json  # noqa: PLC0415

    r = _record(recipe)
    structure_selector(_record(r.get("select")))
    structure_predicate(r.get("when"))
    steps = _list(r.get("steps"))
    for step in steps:
        structure_action(step)
    writes = _list(r.get("writes"))
    if not writes and not all(_record(x).get("op") in ("bind", "refuse") for x in steps):
        fail("profile-write-set")
    phase = r.get("phase")
    for step in steps:
        if phase not in _ACTION_PHASES.get(str(_record(step).get("op")), ()):
            fail("profile-action-phase")
    declared = {json.dumps(x, sort_keys=True) for x in writes if isinstance(x, dict)}
    for step in steps:
        for need in _required_writes(_record(step)):
            if need not in declared:
                fail("profile-write-set")


# ---------------------------------------------------------------- whole-profile walk
_EMIT_REQUIRED = {
    "page": ("id", "name"),
    "node": ("id",),
    "edge": ("id", "source", "target"),
    "label": ("id", "text"),
    "metadata": ("name", "value"),
}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _unique_by_key(items: object, key: str) -> bool:
    """JS unique helper (compiler-static.ts:16-21): True when unique.

    Two entries with the same key value (including two missing keys)
    make the list non-unique; callers refuse ``profile-symbol``.
    """
    if not isinstance(items, list):
        return True
    seen: set[object] = set()
    for entry in items:
        value = entry.get(key) if isinstance(entry, dict) else None
        try:
            hash(value)
            marker: object = value
        except Exception:  # noqa: BLE001 - unhashable keys compare by repr
            marker = repr(value)
        if marker in seen:
            return False
        seen.add(marker)
    return True


def static_walk(  # noqa: C901, PLR0912, PLR0915 - JS admission order transcribed
    profile: dict[str, object], t: Typing
) -> None:
    """CheckWholeProfile typing, JS order (binding domains and locations)."""

    def notion_self(n: dict[str, object]) -> Domain:
        types = n.get("nativeTypes", [])
        if t.metadata_free:
            return UNKNOWN
        return Domain(
            tuple(x for x in types if isinstance(x, str)) if isinstance(types, list) else ()
        )

    notions = [n for n in _list(profile.get("notions")) if isinstance(n, dict)]
    for n in notions:
        for nt in _list(n.get("nativeTypes")):
            t.check_type(nt)
        env = t.base_env()
        env["self"] = notion_self(n)
        t.predicate(n.get("recognition"), env, {}, "recognition")
        # compiler-static.ts:227: nested notion uniqueness, profile-symbol.
        if not _unique_by_key(n.get("labels"), "name"):
            fail("profile-symbol")
        if not _unique_by_key(n.get("fields"), "id"):
            fail("profile-symbol")
    for r in (x for x in _list(profile.get("rules")) if isinstance(x, dict)):
        env = t.base_env()
        params: dict[str, str] = {}
        env["self"] = t.select(r.get("select"), env, params, "validation")
        for b in _list(r.get("bindings")):
            t.bind(_record(b), env, params, "validation")
        t.predicate(r.get("assert"), env, params, "validation")
    for recipe in (x for x in _list(profile.get("recipes")) if isinstance(x, dict)):
        phase = str(recipe.get("phase"))
        env, params = t.base_env(), {}
        for p in _list(recipe.get("parameters")):
            pr = _record(p)
            params[str(pr.get("name"))] = str(pr.get("type"))
            if pr.get("type") == "element":
                if pr.get("name") in env:
                    fail("profile-symbol")
                env[str(pr.get("name"))] = t.elements()
        if phase == "export":
            env["render"] = RENDER_DATA
        env["self"] = t.select(recipe.get("select"), env, params, phase)
        t.predicate(recipe.get("when"), env, params, phase)
        for step in _list(recipe.get("steps")):
            _static_step(t, _record(step), env, params, phase)
        for w in _list(recipe.get("writes")):
            b = _record(w).get("binding")
            if b not in ("envelope", "artifact"):
                t.binding(env, b)
    # compiler-static.ts:322: nested theme uniqueness, profile-symbol.
    for theme in (x for x in _list(profile.get("themes")) if isinstance(x, dict)):
        if not _unique_by_key(theme.get("tokens"), "name"):
            fail("profile-symbol")
        if not _unique_by_key(theme.get("glyphs"), "id"):
            fail("profile-symbol")
        if not _unique_by_key(theme.get("syntheticOccurrences"), "id"):
            fail("profile-symbol")
    # compiler-static.ts:375: nested label-text uniqueness, profile-symbol.
    for message in (x for x in _list(profile.get("messages")) if isinstance(x, dict)):
        if not _unique_by_key(message.get("texts"), "name"):
            fail("profile-symbol")
    for n in notions:
        env = t.base_env()
        env["self"] = notion_self(n)
        for b in _list(n.get("renderBindings")):
            label = _record(b).get("label")
            if label is not None:
                t.expect_type(t.value(label, env, {}, "render"), "string")
        for f in (x for x in _list(n.get("fields")) if isinstance(x, dict)):
            t.read(t.binding(env, "self"), f.get("path"))
            for key in ("visible", "mutable", "when"):
                if f.get(key) is not None:
                    t.predicate(f.get(key), env, {}, "ui")
    for theme in (x for x in _list(profile.get("themes")) if isinstance(x, dict)):
        for s in (x for x in _list(theme.get("syntheticOccurrences")) if isinstance(x, dict)):
            env = t.base_env()
            env["self"] = t.select(s.get("select"), env, {}, "render")
            if s.get("label") is not None:
                t.expect_type(t.value(s.get("label"), env, {}, "render"), "string")
    for entry in (x for x in _list(profile.get("ui")) if isinstance(x, dict)):
        env = t.base_env()
        for key in ("visible", "mutable", "when"):
            if entry.get(key) is not None:
                t.predicate(entry.get(key), env, {}, "ui")
        for tt in _list(entry.get("targetTypes")):
            t.check_type(tt)
    for endpoint in (x for x in _list(profile.get("exports")) if isinstance(x, dict)):
        for cap in (x for x in _list(endpoint.get("capabilities")) if isinstance(x, dict)):
            t.predicate(cap.get("when"), t.base_env(), {}, "capability")


def _static_step(  # noqa: C901, PLR0912, PLR0915 - one branch per recipe step op
    t: Typing,
    step: dict[str, object],
    env: dict[str, Domain],
    params: dict[str, str],
    phase: str,
) -> None:
    op = step.get("op")
    if op == "bind":
        t.bind(step, env, params, phase)
    elif op in ("create", "ensure"):
        t.check_type(step.get("type"))
        parent = t.binding(env, step.get("parent"))
        path = "/" + pointer_key(str(step.get("property")))
        try:
            targets = t.field(parent, path, "containment")
            if any(
                not any(t.type_matches(str(step.get("type")), x, "assignable") for x in f.targets)
                for f in targets
            ):
                fail("profile-type")
        except _Undecided:
            pass
        declared = op == "ensure" or step.get("identity") == "allocated"
        allocated = (
            declared if t.base_fields is None else (str(step.get("type")), "id") in t.base_fields
        )
        if declared != allocated:
            fail("profile-create-identity")
        if True:
            if allocated:
                if op == "ensure":
                    t.binding(env, step.get("owner"))
                for key in ("ownerId", "key"):
                    t.expect_type(
                        t.value(step.get(key), env, params, f"{op}.{key}"),
                        "string",
                        "profile-create-identity",
                    )
                if not t.metadata_free:
                    t.write(Domain((str(step.get("type")),)), "/id", "scalar", phase)
        t.write(parent, path, "containment", phase)
        # compiler-static.ts:273 (unique helper :16-21): duplicate create or
        # ensure field names refuse profile-symbol before field typing.
        seen_names: list[object] = []
        for f in _list(step.get("fields")):
            field_name = _record(f).get("name")
            if field_name in seen_names:
                fail("profile-symbol")
            seen_names.append(field_name)
        for f in _list(step.get("fields")):
            fr = _record(f)
            name = str(fr.get("name"))
            dom = UNKNOWN if t.metadata_free else Domain((str(step.get("type")),))
            try:
                target = t.field(dom, "/" + pointer_key(name), "scalar")
            except _Undecided:
                target = []
            if name == "id":
                fail("profile-producer")
            actual = t.value(fr.get("value"), env, params, "create.fields")
            if actual not in ("string", "number", "boolean", "scalar"):
                fail("profile-type")
            if target and target[0].value_type != "scalar":
                t.expect_type(actual, target[0].value_type)
            t.write(dom, "/" + pointer_key(name), "scalar", phase)
        if step.get("as") in env:
            fail("profile-symbol")
        env[str(step.get("as"))] = UNKNOWN if t.metadata_free else Domain((str(step.get("type")),))
    elif op in ("set", "unset"):
        domain = t.binding(env, step.get("target"))
        raw_path = step.get("path")
        if isinstance(raw_path, str) and raw_path.split("/")[-1] == "id":
            fail("profile-producer")
        t.write(domain, raw_path, "scalar", phase)
        if op == "set":
            actual = t.value(step.get("value"), env, params, "set.value")
            if actual not in ("string", "number", "boolean", "scalar"):
                fail("profile-type")
            try:
                for f in t.field(domain, raw_path):
                    if f.value_type != "scalar":
                        t.expect_type(actual, f.value_type)
            except _Undecided:
                pass
    elif op == "assignRef":
        t.write(t.binding(env, step.get("target")), step.get("path"), "reference", phase)
        for v in _list(step.get("values")):
            if t.value(v, env, params, "assignRef.values") not in ("string", "ids"):
                fail("profile-type")
    elif op == "reparent":
        t.binding(env, step.get("target"))
        t.write(
            t.binding(env, step.get("parent")),
            "/" + pointer_key(str(step.get("property"))),
            "containment",
            phase,
        )
        if phase == "normalize":
            fail("profile-producer")
    elif op == "place":
        t.binding(env, step.get("target"))
        t.binding(env, step.get("owner"))
        if step.get("anchor"):
            t.binding(env, step.get("anchor"))
        if step.get("related"):
            t.select(step.get("related"), env, params, phase)
    elif op == "emit":
        fields = _list(step.get("fields"))
        for f in fields:
            fr = _record(f)
            want = "number" if fr.get("name") in ("fontSize", "strokeWidth") else "string"
            t.expect_type(
                t.value(fr.get("value"), env, params, "emit.fields"), want, "profile-export-field"
            )
        names = {_record(f).get("name") for f in fields}
        if any(n not in names for n in _EMIT_REQUIRED.get(str(step.get("kind")), ())):
            fail("profile-export-field")
        if step.get("parent") is not None:
            t.expect_type(
                t.value(step.get("parent"), env, params, "emit.parent"),
                "string",
                "profile-export-field",
            )
    elif op in ("loss", "refuse"):
        t.binding(env, step.get("target"))
    elif op == "remove":
        t.binding(env, step.get("target"))
        t.select(step.get("dependents"), env, params, phase)
