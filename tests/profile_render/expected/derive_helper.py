"""Standalone derivation helper for the sealed lot-4 expectations.

Arithmetic and hashing only: RFC 8785 JCS with UTF-16 key order, SHA-256,
RFC 6902 patches over the vendored contract files, ties-to-even rounding and
the counter/digest output-ID formulas of DESIGN R3.3 §10.2. It imports
nothing from ``bpmn_io`` (the seal test checks the AST) and never computes a
layout, a render record or an export: those records are written by hand in
the case files; this helper only hashes and assembles them.

Usage (from the repository root)::

    uv run python tests/profile_render/expected/derive_helper.py digest FILE POINTER
    uv run python tests/profile_render/expected/derive_helper.py binding FILE
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
MECHANISM = ROOT / "contracts" / "profile-mechanism" / "1"

Json = Any


# ---------------------------------------------------------------- JCS / H


def _ecma_number(value: float) -> str:
    """Render one finite binary64 like ECMAScript Number-to-string."""
    if math.isnan(value) or math.isinf(value):
        msg = "JCS rejects non-finite numbers"
        raise ValueError(msg)
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    digits_tuple = Decimal(repr(abs(value))).as_tuple()
    raw_digits = "".join(str(d) for d in digits_tuple.digits)
    digits = raw_digits.rstrip("0") or "0"
    exponent = digits_tuple.exponent
    if not isinstance(exponent, int):
        msg = "JCS rejects non-finite numbers"
        raise TypeError(msg)
    point = exponent + len(raw_digits)
    count = len(digits)
    if count <= point <= 21:
        text = digits + "0" * (point - count)
    elif 0 < point <= 21:
        text = digits[:point] + "." + digits[point:]
    elif -6 < point <= 0:
        text = "0." + "0" * (-point) + digits
    else:
        mantissa = digits if count == 1 else digits[0] + "." + digits[1:]
        power = point - 1
        text = f"{mantissa}e{'+' if power >= 0 else '-'}{abs(power)}"
    return sign + text


def _string(value: str) -> str:
    """Escape one string like JSON.stringify (no lone surrogates admitted)."""
    for char in value:
        if 0xD800 <= ord(char) <= 0xDFFF:
            msg = "JCS rejects lone surrogates"
            raise ValueError(msg)
    return json.dumps(value, ensure_ascii=False)


def utf16(value: str) -> bytes:
    """Return the UTF-16 code-unit sort key of one string."""
    return value.encode("utf-16-be")


def _scalar(value: Json) -> str:
    """Render one JSON scalar (null, boolean, number or string)."""
    if value is None or isinstance(value, bool):
        return {None: "null", True: "true", False: "false"}[value]
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _ecma_number(value)
    if isinstance(value, str):
        return _string(value)
    msg = f"not a JSON value: {type(value).__name__}"
    raise TypeError(msg)


def jcs(value: Json) -> str:
    """Return the RFC 8785 canonical text of one JSON value."""
    if isinstance(value, list):
        return "[" + ",".join(jcs(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=utf16)
        return "{" + ",".join(_string(key) + ":" + jcs(value[key]) for key in keys) + "}"
    return _scalar(value)


def h(value: Json) -> str:
    """Return H(x) = lowercase hex SHA-256 over UTF-8 JCS bytes (DESIGN §3.1)."""
    return hashlib.sha256(jcs(value).encode("utf-8")).hexdigest()


def b(data: bytes) -> str:
    """Return B(bytes) = lowercase hex SHA-256 over raw bytes (DESIGN §3.1)."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------- RFC 6901/6902


def _segments(pointer: str) -> list[str]:
    """Split one RFC 6901 pointer into unescaped segments."""
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        msg = f"bad pointer {pointer!r}"
        raise ValueError(msg)
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def _child(holder: Json, part: str) -> Json:
    return holder[int(part)] if isinstance(holder, list) else holder[part]


def resolve(document: Json, pointer: str) -> Json:
    """Resolve one RFC 6901 pointer inside ``document``."""
    current = document
    for part in _segments(pointer):
        current = _child(current, part)
    return current


def _apply_list(holder: list[Json], key: str, kind: str, value: Json) -> None:
    index = len(holder) if key == "-" else int(key)
    if kind == "add":
        holder.insert(index, copy.deepcopy(value))
    elif kind == "remove":
        del holder[index]
    elif kind == "replace":
        holder[index] = copy.deepcopy(value)
    else:
        msg = f"unsupported op {kind!r}"
        raise ValueError(msg)


def _apply_object(holder: dict[str, Json], key: str, kind: str, value: Json) -> None:
    if kind == "replace" and key not in holder:
        msg = f"replace of absent member {key!r}"
        raise KeyError(msg)
    if kind in ("add", "replace"):
        holder[key] = copy.deepcopy(value)
    elif kind == "remove":
        del holder[key]
    else:
        msg = f"unsupported op {kind!r}"
        raise ValueError(msg)


def apply_patch(document: Json, patch: list[dict[str, Json]]) -> Json:
    """Apply RFC 6902 ``add``/``remove``/``replace`` operations to a deep copy."""
    result = copy.deepcopy(document)
    for operation in patch:
        parts = _segments(str(operation["path"]))
        holder = result
        for part in parts[:-1]:
            holder = _child(holder, part)
        if isinstance(holder, list):
            _apply_list(holder, parts[-1], operation["op"], operation.get("value"))
        else:
            _apply_object(holder, parts[-1], operation["op"], operation.get("value"))
    return result


def contract(name: str) -> Json:
    """Load one vendored ``contracts/profile-mechanism/1`` JSON file."""
    return json.loads((MECHANISM / name).read_text(encoding="utf-8"))


def profile_from_ref(ref: dict[str, Json]) -> Json:
    """Materialize one ``{"base": file, "patch": [...]}`` profile reference."""
    return apply_patch(contract(str(ref["base"])), list(ref.get("patch", [])))


# ------------------------------------------------- package table (spec §16)

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
PACKAGES = {
    "neutral-descriptors/1": (MECHANISM / "neutral-descriptors.json", "fixture-2"),
    "neutral-base/1": (MECHANISM / "neutral-base.json", "fixture-2"),
    "neutral-render-descriptors/1": (ARTIFACTS / "render-descriptors.json", "fixture-1"),
    "neutral-render-base/1": (ARTIFACTS / "render-base.json", "fixture-1"),
}


def package_bytes(package_id: str) -> bytes:
    """Return the raw bytes of one pinned package of the closed package table."""
    return PACKAGES[package_id][0].read_bytes()


def package_pin(package_id: str) -> dict[str, str]:
    """Return ``{id, version, sha256 = B(raw bytes)}`` of one package."""
    return {
        "id": package_id,
        "version": PACKAGES[package_id][1],
        "sha256": b(package_bytes(package_id)),
    }


def admitted_types(profile: dict[str, Json]) -> set[str]:
    """Return the native types of every descriptor package the profile pins."""
    names: set[str] = set()
    for pin in profile["descriptors"]:
        document = json.loads(package_bytes(str(pin["id"])).decode("utf-8"))
        names.update(document["types"])
    return names


def _is_element(value: Json) -> bool:
    return isinstance(value, dict) and isinstance(value.get("$type"), str)


def tree_types(tree: Json) -> set[str]:
    """Return every element ``$type`` of one native JSON tree (explicit stack)."""
    found: set[str] = set()
    stack = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            if _is_element(node):
                found.add(str(node["$type"]))
            stack.extend(node.values())
    return found


def native_preorder_ids(tree: Json) -> list[str]:
    """Return the IDs of ID-bearing elements in native pre-order (DESIGN §9.1 coverage).

    An element precedes its contained elements; containment members (element
    or element-array values) are visited in UTF-16 member-name order and
    arrays in index order; ID-less elements are traversed but not listed.
    """
    out: list[str] = []
    stack: list[Json] = [tree]
    while stack:
        node = stack.pop()
        if not _is_element(node):
            continue
        if isinstance(node.get("id"), str):
            out.append(str(node["id"]))
        children: list[Json] = []
        for key in sorted(node, key=utf16):
            value = node[key]
            if _is_element(value):
                children.append(value)
            elif isinstance(value, list) and value and all(_is_element(item) for item in value):
                children.extend(value)
        stack.extend(reversed(children))
    return out


# -------------------------------------------------------- identities (§3.1)


def profile_identity(profile: dict[str, Json]) -> dict[str, Json]:
    """Return the closed ``profileIdentity`` record of one profile (§5.1)."""
    return {
        "mechanismVersion": profile["mechanismVersion"],
        "schemaVersion": profile["schemaVersion"],
        "profile": profile["profile"],
        "version": profile["version"],
        "sha256": h(profile),
        "base": profile["base"],
        "descriptors": profile["descriptors"],
    }


def sort_bindings(bindings: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sort support bindings by ownerId, role, targetId (UTF-16)."""
    return sorted(
        bindings,
        key=lambda item: (utf16(item["ownerId"]), utf16(item["role"]), utf16(item["targetId"])),
    )


def semantic_revision(tree: Json, identity: Json, bindings: list[dict[str, str]]) -> str:
    """Return H({tree, profileIdentity, bindings}) for a DI-free tree (§3.1)."""
    return h({"tree": tree, "profileIdentity": identity, "bindings": sort_bindings(bindings)})


# ------------------------------------------------------- digests (§9.2)


def descriptor_digest(pins: list[dict[str, str]]) -> str:
    """Return H(pins sorted by unique id), each pin exactly {id,version,sha256}."""
    return h(
        sorted(
            ({"id": p["id"], "version": p["version"], "sha256": p["sha256"]} for p in pins),
            key=lambda p: utf16(p["id"]),
        )
    )


def theme_chain(themes: list[dict[str, Json]], theme_id: str) -> list[dict[str, Json]]:
    """Return the fallback chain from the fallback root to the selected theme."""
    by_id = {str(theme["id"]): theme for theme in themes}
    chain: list[dict[str, Json]] = []
    current: str | None = theme_id
    while current is not None:
        theme = by_id[current]
        chain.insert(0, theme)
        fallback = theme.get("fallback")
        current = str(fallback) if fallback is not None else None
    return chain


def theme_digest(themes: list[dict[str, Json]], theme_id: str) -> str:
    """Return H({themeId, themes}) over the resolved chain (§9.2)."""
    return h({"themeId": theme_id, "themes": theme_chain(themes, theme_id)})


def _sorted_tokens(tokens: list[dict[str, Json]]) -> list[dict[str, Json]]:
    return sorted(
        ({"name": t["name"], "value": t["value"]} for t in tokens),
        key=lambda t: utf16(str(t["name"])),
    )


def _occurrence_bag(records: list[dict[str, Json]]) -> list[dict[str, Json]]:
    bag = [
        {
            "pageId": r["pageId"],
            "occurrenceKey": r["occurrenceKey"],
            "tokens": _sorted_tokens(r["tokens"]),
        }
        for r in records
    ]
    return sorted(bag, key=lambda r: (utf16(str(r["pageId"])), utf16(str(r["occurrenceKey"]))))


def normalize_overrides(value: dict[str, Json]) -> dict[str, Json]:
    """Sort an Overrides/1 record (semanticId; pageId, occurrenceKey; token name)."""
    semantic = sorted(
        (
            {"semanticId": r["semanticId"], "tokens": _sorted_tokens(r["tokens"])}
            for r in value["semantic"]
        ),
        key=lambda r: utf16(str(r["semanticId"])),
    )
    return {"semantic": semantic, "occurrence": _occurrence_bag(value["occurrence"])}


def normalize_di_styles(value: dict[str, Json]) -> dict[str, Json]:
    """Sort a DiStyles/1 record by the same occurrence/name order."""
    return {"native": _occurrence_bag(value["native"]), "bioc": _occurrence_bag(value["bioc"])}


def metrics_digest(resources: list[dict[str, str]]) -> str:
    """Return H([{id,sha256}] sorted by unique resource id)."""
    return h(
        sorted(
            ({"id": r["id"], "sha256": r["sha256"]} for r in resources),
            key=lambda r: utf16(r["id"]),
        )
    )


def payload_digest(render: dict[str, Json]) -> str:
    """Return H({pages, occurrences, coverage, diagnostics}) of one RenderData/1."""
    return h({key: render[key] for key in ("pages", "occurrences", "coverage", "diagnostics")})


def view_revision(binding: dict[str, Json]) -> str:
    """Return the §9.2 viewRevision of one binding record."""
    keys = (
        "semanticRevision",
        "layoutDigest",
        "themeId",
        "themeDigest",
        "overridesDigest",
        "diStylesDigest",
        "metricsDigest",
    )
    return h({key: binding[key] for key in keys})


def theme_metric_resources(profile: dict[str, Json], theme_id: str) -> list[dict[str, str]]:
    """Return the {id, sha256} pins of the metric resources the chain references."""
    chain = theme_chain(profile["themes"], theme_id)
    wanted = {str(theme["metricsResource"]) for theme in chain}
    return [
        {"id": str(r["id"]), "sha256": str(r["sha256"])}
        for r in profile["resources"]
        if r["id"] in wanted
    ]


def render_binding(case_input: dict[str, Json], render: dict[str, Json]) -> dict[str, Json]:
    """Assemble one RenderData/1 binding from a case input and a hand-written payload."""
    profile = profile_from_ref(case_input["profile"])
    identity = profile_identity(profile)
    theme_id = str(case_input.get("resolvedThemeId", case_input["themeId"]))
    return {
        "semanticRevision": semantic_revision(case_input["tree"], identity, case_input["bindings"]),
        "profileDigest": identity["sha256"],
        "descriptorDigest": descriptor_digest(identity["descriptors"]),
        "layoutDigest": h(case_input["layout"]),
        "themeId": theme_id,
        "themeDigest": theme_digest(profile["themes"], theme_id),
        "overridesDigest": h(normalize_overrides(case_input["overrides"])),
        "diStylesDigest": h(normalize_di_styles(case_input["diStyles"])),
        "metricsDigest": metrics_digest(theme_metric_resources(profile, theme_id)),
        "payloadDigest": payload_digest(render),
    }


# --------------------------------------------------- arithmetic (§3.1)


def round_even(value: Fraction) -> int:
    """Round one rational to the nearest integer, ties to even (§3.1)."""
    floor = math.floor(value)
    rest = value - floor
    if rest > Fraction(1, 2):
        return floor + 1
    if rest < Fraction(1, 2):
        return floor
    return floor if floor % 2 == 0 else floor + 1


def decimal_ratio(value: float) -> Fraction:
    """Return the exact rational of a number's shortest round-trip decimal form."""
    return Fraction(Decimal(_ecma_number(value)))


# -------------------------------------------------- export IDs (§10.2)

DOMAINS = ("page", "node", "edge", "label")


def counter_ids(
    keys: list[tuple[str, str, str]], page_order: dict[str, int], origin: int
) -> dict[tuple[str, str, str], str]:
    """Allocate ``e_<n>`` for (pageId, occurrenceKey, domain) keys (§10.2 counter policy)."""
    unique = sorted(
        set(keys),
        key=lambda k: (DOMAINS.index(k[2]), page_order[k[0]], utf16(k[1])),
    )
    return {key: f"e_{origin + index}" for index, key in enumerate(unique)}


def digest_id(page_id: str, occurrence_key: str, domain: str) -> str:
    """Return ``e_`` + full SHA-256 of JCS [pageId, occurrenceKey, domain] (§10.2)."""
    return "e_" + h([page_id, occurrence_key, domain])


def synthetic_key(declaration_id: str, owner_id: str, page_id: str) -> str:
    """Return the synthetic occurrence key JCS([id, owner.id, pageId]) (§9.3)."""
    return jcs([declaration_id, owner_id, page_id])


# -------------------------------------------------------------- CLI


def _main(argv: list[str]) -> int:
    command, path = argv[1], Path(argv[2])
    case = json.loads(path.read_text(encoding="utf-8"))
    if command == "digest":
        sys.stdout.write(h(resolve(case, argv[3])) + "\n")
        return 0
    if command == "binding":
        render = resolve(case, "/expected/payload")
        binding = render_binding(case["input"], render)
        binding["viewRevision"] = view_revision(binding)
        sys.stdout.write(json.dumps(binding, indent=2) + "\n")
        return 0
    sys.stderr.write(f"unknown command {command!r}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
