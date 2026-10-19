"""Standalone derivation helper for the sealed lot-4 expectations.

Arithmetic and hashing only: RFC 8785 JCS with UTF-16 key order, SHA-256,
RFC 6902 patches over the vendored contract files, ties-to-even rounding and
the counter/digest output-ID formulas of DESIGN R3.3 §10.2. It imports
nothing from ``bpmn_io`` (the seal test checks the AST) and never computes a
layout, a render record or an export: those records are written by hand in
the case files; this helper only hashes and assembles them. It also carries the
pins of the JS lot-4 cases vendored by the block-B parity sync (``VENDORED``,
``VENDORED_CONTRACTS``, ``ALIASES``) and returns vendored bytes only after
checking their pin.

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


# ------------------------------- vendored JS lot-4 cases (block-B parity sync, §17.6)

JS_SEAL_SHA256 = "5d50127e5eac2791d4699f6cf4094b803bd05c1681a445298bf74a06b892f2c0"
TREES = {"render": "tests/profile_render/expected", "export": "tests/profile_export/expected"}
VENDOR = "vendor/js"

# Path relative to <tree>/vendor/js/ -> raw SHA-256 (the digest the JS seal.json lists).
VENDORED: dict[str, dict[str, str]] = {
    "render": {
        "artifacts/choices-host-case.layout.json": (
            "eb52095d26572d1bf7e40eeca47cc7138cab68121e3ec3846fa6a891a521f165"
        ),
        "artifacts/choices-locale-case.layout.json": (
            "a489390de2d22bbbf6dfb34f6d1ab92d3f5dcdd11d7b896e74097c2d6bf5a60d"
        ),
        "artifacts/choices-lower.layout.json": (
            "2d32aee2ca1bb9f05d8a52fd867c3b19b84944f060af4287a8a4dfbcb77a5b9f"
        ),
        "artifacts/choices-lowered.resolve-result.json": (
            "ed8cc8ca6a175c3fef8ef662be15e2e2dacf42ffdcb3b65bd0e547efdce2a15e"
        ),
        "artifacts/choices-plain.resolve-result.json": (
            "3cc15d217e1dd22418dd0a9bfaf097352b0923ff399f934019e4d337e08361b6"
        ),
        "artifacts/choices-upper.layout.json": (
            "7bd3025f8326ed634ab5bf8db830860543ee8f15d756bfae5f9d359074a2b3b5"
        ),
        "artifacts/choices.envelope.json": (
            "38d28f627fb5e0b6f739ef218db7ac74a249fe3f7ec34640bb436dc2f390432d"
        ),
        "artifacts/digest-003-baseline.record.json": (
            "991b7734880dad287ff1fdc52ac9910845ba8426af106b05cc7658f59f3581bc"
        ),
        "artifacts/digest-004-descriptor-pins-reversed.record.json": (
            "c0cebef3a537a219dbd4598ad386ae2583f490c1658a7bd88e66c195b8421b3e"
        ),
        "artifacts/digest-005-metric-resources-reversed.record.json": (
            "ba6d9a0b2f360e68db1226ba62c71760ae186fbd0ed8a56e3ef7349ee2abcf37"
        ),
        "artifacts/digest-006-metric-byte-changed.record.json": (
            "2392768a153a110f4a95d1c7fde13270bb0136745884f54cc5bebd8537cb1ebe"
        ),
        "artifacts/digest-007-bags-sorted.record.json": (
            "20b4f52bf3dd468b21f2b953d377f7c0fef0f4aa88223167bed59513357ad380"
        ),
        "artifacts/digest-008-bags-reversed.record.json": (
            "1022ecbf200e5e6c0604775f50298e7f6d9da96191488d9384e9224415a5fe71"
        ),
        "artifacts/empty-plain.resolve-result.json": (
            "7d222cb609ecc5827c8194811fd80f6a1a271e0b8c3a3beeb22bf4aefc84a2a2"
        ),
        "artifacts/empty-striped.base-geometry.json": (
            "23fc7b828a0fe06edddc82a7a16925941c5249a81980df7f66bb247f5742ef62"
        ),
        "artifacts/empty.base-geometry.json": (
            "23fc7b828a0fe06edddc82a7a16925941c5249a81980df7f66bb247f5742ef62"
        ),
        "artifacts/empty.envelope.json": (
            "0a7e64513915c17d08eeba54176afdfd6fbbc2311abb044d48206d0b16f7c175"
        ),
        "artifacts/empty.layout.json": (
            "23fc7b828a0fe06edddc82a7a16925941c5249a81980df7f66bb247f5742ef62"
        ),
        "artifacts/empty.placements.json": (
            "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"
        ),
        "artifacts/grid-fixture.envelope.json": (
            "76720af1fa9f44f1518133c8509f03cbbd86b632208d3f4b5aa08f5342db3db0"
        ),
        "artifacts/grid-fixture.layout.json": (
            "1ab03574225a1fed29a4356ea4c24e71d3e3d0e2fd2aa53ecc28bef85f953cf1"
        ),
        "artifacts/grid-fixture.placements.json": (
            "19e28fd824dd11ec28b3f8a931f2b4e382a5088aebd5f5a43a0aa74ff7b63592"
        ),
        "artifacts/grid-successor-plain.resolve-result.json": (
            "e9d6c95fcec44d0faa57971d065f72698b7ae741947173248fa7dfcf0766a8f2"
        ),
        "artifacts/grid-successor.base-geometry.json": (
            "2a357d0d32ee3bb7ca3e2ba2eb550d77f324fffeaf0a53d699fb59151d64ee89"
        ),
        "artifacts/grid-successor.envelope.json": (
            "28ed484a6e23de6e4117e0f13aae43bb97df262698b9e6bcacd0f2ef0425cb50"
        ),
        "artifacts/grid-successor.layout.json": (
            "38e5487934bc7e951f9cc2e737d111d1931e2fa31c6d60d1cfcad5045f50573a"
        ),
        "artifacts/grid-successor.profile.json": (
            "e39fbd775d1538c825cdefe9c7d3a5cd179c7553cd2b243a23ead5a3c122f8d8"
        ),
        "artifacts/layout-001-main.result.json": (
            "c79b8af7fdbbb8c503ddf1e9fe9a1b8569c478ea84049afc74c77a818ccb0fc9"
        ),
        "artifacts/layout-002-repeated-views.result.json": (
            "3cc09f2fb86f78a6d2111088789216ded845f5fce4c1841969a37b33d3f408e6"
        ),
        "artifacts/layout-003-multi-process.result.json": (
            "4a4d88fb3795a1e39703c7803e12572af67f06e738377ef479312ad83414f928"
        ),
        "artifacts/layout-004-empty-process.result.json": (
            "3f1d116de4bd0c02d622fc2f54c5a5b7225dd8c5756f9a23b15a40e914a40dfb"
        ),
        "artifacts/layout-005-missing-lane.result.json": (
            "29ca2f499919a374f3c9a4d22fb17ea975303d451a91be9b237ef6e718bbf9f4"
        ),
        "artifacts/layout-006-neutral-fixture.result.json": (
            "9e53dee29d505eef079840e824db2fb3f82573e84844f4ffc00da653c7089162"
        ),
        "artifacts/layout-007-grid-fixture.result.json": (
            "265a2d70a1a3a8c5f7702c176a45e9b53b6406743e3fc2de6ad4f93a424a4dd2"
        ),
        "artifacts/layout-008-neutral-successor.result.json": (
            "ee1ea1ec3b7686fc6f6d7d459caf758b871e40ffbf793e4c19bf5accfc0077cb"
        ),
        "artifacts/layout-009-grid-successor.result.json": (
            "086f6e09c6114748113113b82647b9fddbdac4d7c0d27b07b2ed9d8f4577fc10"
        ),
        "artifacts/layout-010-anchor-twice.result.json": (
            "2ed05950649849e3b2ac3b77ab106f2898649adff660128ee44b41569cb8eb8f"
        ),
        "artifacts/layout-011-geometry-theme-gated.result.json": (
            "099e0c49b8b66016e2f90774b835c50147b77d9d7e13187ddbf0ed5bfb2926f4"
        ),
        "artifacts/main-aid-noanchor.placements.json": (
            "928d6f6b9d06417106c460aa3978f85056f52dd70d0359e1778a23deb3abfd28"
        ),
        "artifacts/main-aid-plain.base-geometry.json": (
            "070b165f3bfe02f92255ef1bd260f00220818b1a3fafd5c1cf7e8f6b83b7fab6"
        ),
        "artifacts/main-aid.placements.json": (
            "bf011f7f55f1df9df2fb6e1f7724135f0b8ca365b59fc6864916224db3493244"
        ),
        "artifacts/main-badged-hidden.base-geometry.json": (
            "070b165f3bfe02f92255ef1bd260f00220818b1a3fafd5c1cf7e8f6b83b7fab6"
        ),
        "artifacts/main-badged-noanchor.base-geometry.json": (
            "070b165f3bfe02f92255ef1bd260f00220818b1a3fafd5c1cf7e8f6b83b7fab6"
        ),
        "artifacts/main-badged.base-geometry.json": (
            "070b165f3bfe02f92255ef1bd260f00220818b1a3fafd5c1cf7e8f6b83b7fab6"
        ),
        "artifacts/main-badged.layout.json": (
            "d75ec3b205da99f61ac81feb2dc056484f0defe9cbb0990203561f9d4b813406"
        ),
        "artifacts/main-badged.resolve-result.json": (
            "f374fb289727c98286a1843263ff42fdb1a152a5da32f64d6328dd0fb9a4ded5"
        ),
        "artifacts/main-dim-precedence.resolve-result.json": (
            "6e2478a18c9c785aa52379c1c2defef5a688c7c1645f305391b6938a4cdb0181"
        ),
        "artifacts/main-extra-label.layout.json": (
            "1dfe36e88b96f12d1cb8c91791ea1b60836c06027b7d64a0b0d633daef77c73a"
        ),
        "artifacts/main-label-moved.layout.json": (
            "e8f28d287d48902302edb4efa488eade8dfb9ca4f674bca9a9198ba2fadcf59e"
        ),
        "artifacts/main-label-moved.resolve-result.json": (
            "c3c892d8eca944cf621c8145b0cb4c0bdbf620d707f2f5b1d824522d54a23e8b"
        ),
        "artifacts/main-legacy-colored.resolve-result.json": (
            "1963931af11b1fb9e4f3f9a5be67e77279547ea108893e1e74c72b05bc610ac0"
        ),
        "artifacts/main-legacy-custom.resolve-result.json": (
            "2951181699ab018c82b040f392b152a1e5cb3774da80ccc80fbe0f4ef3b08a40"
        ),
        "artifacts/main-metric-z.resolve-result.json": (
            "73abb6c81bfaeddeb5cbaaafecbaba643c9c497d11c8202823c3e898879c36fe"
        ),
        "artifacts/main-missing-label.layout.json": (
            "e8e40dc3b05e4aac8decb7c14a13247f568f588fb563e5623298fb2b9fddb964"
        ),
        "artifacts/main-nolane.base-geometry.json": (
            "070b165f3bfe02f92255ef1bd260f00220818b1a3fafd5c1cf7e8f6b83b7fab6"
        ),
        "artifacts/main-nolane.envelope.json": (
            "d796d102d076152a165d98caa2dfc113f0826f84274164ab4bcfe9ffc1bcc825"
        ),
        "artifacts/main-note.envelope.json": (
            "88aa47074d31769ac83558876320d36587c6b7d925ee7f47ee083443e06025cf"
        ),
        "artifacts/main-note.layout.json": (
            "4e2b461cb568dc576c3520d2b764b475c3d1b038e5f29b5728ea0113f454483f"
        ),
        "artifacts/main-plain.resolve-result.json": (
            "4a813014557f60303cbd1f0071bef7cdd4e735ab29bdb025e67a470a87ada3fa"
        ),
        "artifacts/main-renamed.layout.json": (
            "b8828280b41db622ab90ea7fd9b79003f5f0a1a56dbfdd2763409c4894d78e5b"
        ),
        "artifacts/main-renamed.resolve-result.json": (
            "a7abe411597ab20897e7f989ef0d10f4984de68a2dd25d6e4131746f7541a301"
        ),
        "artifacts/main-stale-choice.layout.json": (
            "a4abef27bb28e37c3aa8420b5526ab24ed9eaedd1159be1aeed841e1f201cbc5"
        ),
        "artifacts/main-striped.base-geometry.json": (
            "070b165f3bfe02f92255ef1bd260f00220818b1a3fafd5c1cf7e8f6b83b7fab6"
        ),
        "artifacts/main-striped.layout.json": (
            "0c01c961f1f84f4ae19b58e7654be110947cf7ced83726aef0e81cb60d92517a"
        ),
        "artifacts/main-striped.resolve-result.json": (
            "0698d72714e103c0157c6c23d5ee2568e2bb2b3edba6e0e823d78be57658d0c0"
        ),
        "artifacts/main-twice-badged.base-geometry.json": (
            "34f5836f3b27b70c04447e28bfd7398c832b693989b2824ff7b4d4672487ff6b"
        ),
        "artifacts/main-twice.base-geometry.json": (
            "34f5836f3b27b70c04447e28bfd7398c832b693989b2824ff7b4d4672487ff6b"
        ),
        "artifacts/main-wide-own.base-geometry.json": (
            "070b165f3bfe02f92255ef1bd260f00220818b1a3fafd5c1cf7e8f6b83b7fab6"
        ),
        "artifacts/main.base-geometry.json": (
            "070b165f3bfe02f92255ef1bd260f00220818b1a3fafd5c1cf7e8f6b83b7fab6"
        ),
        "artifacts/main.envelope.json": (
            "407e44da330ed1d26bd6e151411ae9415dd3771b6915f84b553c10120d81c61f"
        ),
        "artifacts/main.layout.json": (
            "377e069bbaf287e4addb152628c4a4537bca331059eaae7002106a0036d5b9d1"
        ),
        "artifacts/main.placements.json": (
            "4cf87df1d2bd304b8a014c3c3fc4370325b49496ee8f39ee1eb388958d88a4a4"
        ),
        "artifacts/main@conflict.envelope.json": (
            "9930889c3a7667e8e09428484067ab2777c2f1f2c0d5050fb9e23b85cfca62df"
        ),
        "artifacts/multi-plain.resolve-result.json": (
            "312e980a905aa94191f627515c4be75df3fed304255fc74efaf44b72447533f7"
        ),
        "artifacts/multi-striped.base-geometry.json": (
            "bb11f184c580db656d0316786599941b0d30f90acfef813cc4a0e39fccff3844"
        ),
        "artifacts/multi.base-geometry.json": (
            "bb11f184c580db656d0316786599941b0d30f90acfef813cc4a0e39fccff3844"
        ),
        "artifacts/multi.envelope.json": (
            "d2a0ebf7ec84fd68fc39e362b41c5895cba75d40701026aa029d868b7c2c8940"
        ),
        "artifacts/multi.layout.json": (
            "daafd1f8ce0b8fc6fed2a3542c564946cb60d5a89d71864b548aa9c91a43e2b0"
        ),
        "artifacts/multi.placements.json": (
            "a94b95900e2c6c9bdf5f253a2964402086f98a76ea5eaa4ad96695f14d0d4bec"
        ),
        "artifacts/neutral-fixture.envelope.json": (
            "8248f93b1e73045e810089da5be0c056220085ccd0d355e8623ea1691f490cab"
        ),
        "artifacts/neutral-fixture.layout.json": (
            "3258973f7068f9317ce8660d7eb1660dd8d149307b6be34d07023bc31387feb8"
        ),
        "artifacts/neutral-fixture.placements.json": (
            "5c17530cc39f63084c06e97fb5462ffb1c00e5b413ffe423090ad2e0a2a2fc4d"
        ),
        "artifacts/neutral-lot4-base.json": (
            "3599ac08a9ba1ce429f739f39ab6654d01ae57060ed612f8b14196bad817e7e8"
        ),
        "artifacts/neutral-lot4-byte-claim.profile.json": (
            "fcc858c1c50d41a3b0241e275ea8d3b2989e3f3028c80acd1cfd5867ccc7edad"
        ),
        "artifacts/neutral-lot4-conflict.profile.json": (
            "2be44d8e2987a0af70105408ff360b0bbbbca4d93d474745f2d43086b3b1b88b"
        ),
        "artifacts/neutral-lot4-descriptors.json": (
            "a2578b19578280b307d8140696cbf5a0b66cd0af6bf788e49e399e60f1d9390a"
        ),
        "artifacts/neutral-lot4-dup-emit.profile.json": (
            "ab2a92fb91ef95185a225286ec8d7e87337e830e929e96df85feea90afe394f3"
        ),
        "artifacts/neutral-lot4-labels-native.profile.json": (
            "25994e7567cfd36de3b62f4ccfb04b2332c2f72e702a767472fe91678cb01468"
        ),
        "artifacts/neutral-lot4-missing-field.profile.json": (
            "8d8c6d5553fc50975b31c9fe2e5da5219c539efa32189832cbf37122333ee7ac"
        ),
        "artifacts/neutral-lot4-parent-order.profile.json": (
            "ae7a40cd1f47e85b8ee637e21ce5597a2c3cf0f200281df713d5b362b70f9f16"
        ),
        "artifacts/neutral-lot4-profile.json": (
            "6b8f27c2ef5778cf29882fa8c7278b4945eb409105ebaf5ceb4e97c6c25b26c6"
        ),
        "artifacts/neutral-lot4-unsupported.profile.json": (
            "9c13886579df461b5f6ce7891407851d955170ebe7a53e0f52ddac8ab4ce4883"
        ),
        "artifacts/neutral-plain.resolve-result.json": (
            "b075f83bfbbf0009d17633746b69bbf5d6a45951a52c275f25afdb1aa982e92e"
        ),
        "artifacts/neutral-successor-plain.resolve-result.json": (
            "10c09ff30d09286e5577b9d2e9203a996b2121d4f56ebc39fb20245c6d7e5b6b"
        ),
        "artifacts/neutral-successor.base-geometry.json": (
            "ee11fbe1e3fb06cc157a799060d04e9f7b6279b0de8be3914e4c567af1218839"
        ),
        "artifacts/neutral-successor.envelope.json": (
            "399b75f2b82beea753d64661b504bcc7637d8ae45c85db6fee6c6c6829704ac9"
        ),
        "artifacts/neutral-successor.layout.json": (
            "ae975f82fa1e046ee0dd95af7904be58c7f0f2e714aedecdd83589d01dfb66ed"
        ),
        "artifacts/neutral-successor.profile.json": (
            "31387224e72609c153fc49e26c29e33de18fda7ab1fbabed55d25ba0bb21e658"
        ),
        "artifacts/note-plain.resolve-result.json": (
            "8eefc6758e9400c0751e8293f1e8590be212e08bd3073c11ef43b4ef98f9d197"
        ),
        "artifacts/repeated-plain.resolve-result.json": (
            "51a12ba3e55dd10c508b136b39fd596fcbe582cb64c9ec6e2cf8ec8862a1bd1f"
        ),
        "artifacts/repeated-semantic.resolve-result.json": (
            "8f897bf193d5060700d45b086c1e9074b4eeeb496ebb0c421ec6211d78009d07"
        ),
        "artifacts/repeated-sparse.resolve-result.json": (
            "f4920454ee26278ee6f454d3a4566f866fbd88816252410bb044261ec05960b2"
        ),
        "artifacts/repeated-striped.base-geometry.json": (
            "b375f4263aee517efd257c662bb06031b0bb3100130709d74e24911db82e6562"
        ),
        "artifacts/repeated.base-geometry.json": (
            "b375f4263aee517efd257c662bb06031b0bb3100130709d74e24911db82e6562"
        ),
        "artifacts/repeated.layout.json": (
            "1eb7c1be5ac25ec87328fe8c95ac5f9bb5ea50920429801d108961a0bafc21a4"
        ),
        "artifacts/synthetic-001-band-stripe.result.json": (
            "54470732c978b167de0daedef3d6822f483a428ddf2f9ec29917625c7e450789"
        ),
        "artifacts/synthetic-002-per-page.result.json": (
            "90d3b8926671095dd710d26ffb7a8de2893a0a32c0a955a7a486a9d9eda36f2a"
        ),
        "artifacts/synthetic-003-per-owner.result.json": (
            "9f55fce2ae04688d741aa9999b4fa5d342cb39fb2e102bac90d8a6d2a317610e"
        ),
        "artifacts/synthetic-004-region-missing.result.json": (
            "d68676fb21361583f4b07a0e860bbd694f121916e6e09fa0f8bda95fcc26212f"
        ),
        "artifacts/synthetic-005-grid-fixture.result.json": (
            "265a2d70a1a3a8c5f7702c176a45e9b53b6406743e3fc2de6ad4f93a424a4dd2"
        ),
        "artifacts/synthetic-006-attached-badge.result.json": (
            "d4e722dbdbf8581b7c1e7ffdcc16c7123e02c1d95e9d05e44aebdb27af24119b"
        ),
        "artifacts/synthetic-007-badge-ambiguous-anchor.result.json": (
            "460296ae3eae03dcc4b2b8af21fa3c650c37a2c21583790e38ae5f2fa7bc3ce7"
        ),
        "artifacts/synthetic-008-badge-no-anchor.result.json": (
            "460296ae3eae03dcc4b2b8af21fa3c650c37a2c21583790e38ae5f2fa7bc3ce7"
        ),
        "artifacts/synthetic-009-badge-hide-source.result.json": (
            "2b309d39c4217eeadf89e88b283f48b3bf1f6a1a8011f614b999052eda987753"
        ),
        "artifacts/synthetic-010-unbound-region.result.json": (
            "460296ae3eae03dcc4b2b8af21fa3c650c37a2c21583790e38ae5f2fa7bc3ce7"
        ),
        "artifacts/variety-plain.resolve-result.json": (
            "1d2a525147e49d1182de1b114b42d65f8d2cf4564d13b57510f3e378c4ae94b9"
        ),
        "artifacts/variety.envelope.json": (
            "7fe9f9ecd969547da2475e7dea1819539efe4c21e3dca68617e6ef4ee6ea581e"
        ),
        "artifacts/variety.layout.json": (
            "23f41da0a6c5f50c0ed5a413e515ecc61e3ad7b6ba18af11319bb50385c87736"
        ),
        "artifacts/z-metrics.json": (
            "baf2ae3eff1522d8fdd4b7c24790cfa80cecb67392096c08008aa20a1babe8a4"
        ),
        "cases/admission-001-lot4-package.json": (
            "0c9a6d974f4feadc5a9748a60c126725fb945a11fa0b003189505c6c19a85db9"
        ),
        "cases/admission-002-variant-conflict.json": (
            "6403c646430424b6cb15beaa822fb8b02d4a86405a06faac54602e1d1a677904"
        ),
        "cases/admission-003-variant-labels-native.json": (
            "6d0aa5eea4ed11608eea0ae51dbd9e7116e449b77393cd7df86c2f42ee25ad2b"
        ),
        "cases/admission-004-variant-byte-claim.json": (
            "3c00fa7903a29472ee67511ef7ac5ce99bc1f5eebec1986713aab4304f67b909"
        ),
        "cases/admission-005-variant-unsupported.json": (
            "8a893b0500b8cbb23e3c680d517abd8fdb08cfafd6813c3d029b1172f88e95e2"
        ),
        "cases/admission-006-variant-parent-order.json": (
            "27a9317538a3a761998e458cc65fee6ce60ee10f7377dd76d94eb4fe636c6884"
        ),
        "cases/admission-007-variant-dup-emit.json": (
            "e3a62bad3ad34de94487e49820d971ac72cfba5b407f24710f7241128145baec"
        ),
        "cases/admission-008-variant-missing-field.json": (
            "5a0bb9e60b4a28c871043bf11e28e97397b7e59ddf7b0c26905d262cdb94cb68"
        ),
        "cases/admission-009-neutral-successor.json": (
            "c473eb94bf32f058bae5e8d5cba73eac9a0275a6cb3d1f24929632b623414775"
        ),
        "cases/admission-010-grid-successor.json": (
            "262c2c30f9f46bc2145100523452d73ec8a3dc772406b3a5f2c830388c7c9ee2"
        ),
        "cases/decision-001-question-and-choices.json": (
            "e242d084a590c8f0b1c96885ce75473106501ec56f62ed373e1f1991615a5bf5"
        ),
        "cases/decision-002-lower-final-sigma.json": (
            "b5da134cb5a942d7e415c24e36a59709913c612bb0857f55b6caa1202e67642c"
        ),
        "cases/decision-003-host-case-stale.json": (
            "c3b1dd079b533bd1a1e7c0364afcccd5e9194c4265c7987dfd3f481328ffa87c"
        ),
        "cases/decision-004-locale-case-stale.json": (
            "e3ed86391466c1e6fa17ec4cb56e03f7e49864eafea867c2e5099464b3b0e506"
        ),
        "cases/decision-005-case-operator.json": (
            "4621c654ad321d122a9903bd5a5c412d28f79987b011323b24cb80cafa5855f7"
        ),
        "cases/digest-001-page-rename.json": (
            "4bddc0560586fa52dab56caf4d904a420ed965bac36a64debee8b1db1869cbea"
        ),
        "cases/digest-002-label-move.json": (
            "2a40621a6f39af1df13f70d37233cf9a24b288789fc17fbd8dfd0f8fbcf60790"
        ),
        "cases/digest-003-baseline.json": (
            "5af1b51b49778ab028bccee726cae6852a053d02dc9835364669a5ea7cdc11aa"
        ),
        "cases/digest-004-descriptor-pins-reversed.json": (
            "97e7e147bc3d1dba490ef95344ba9671e4cb03cf01102ffb3fd52e0ed49cfd4b"
        ),
        "cases/digest-005-metric-resources-reversed.json": (
            "66a9fc9bede954ea0c0a914d7b8f251a35d715ef5d64c57eec8fc2bf769b328e"
        ),
        "cases/digest-006-metric-byte-changed.json": (
            "c25ddba919da2720126c26960222e03b09141e65bf6f30fe4be55e3d994001f3"
        ),
        "cases/digest-007-bags-sorted.json": (
            "d039fff63fa856a130c4b618dee18366abca4d33c066d38aa9fdc19303f69841"
        ),
        "cases/digest-008-bags-reversed.json": (
            "2da94b9419af163011a61f2c7a49e9ef76e8c6c93bd331156c69607bfe8ca574"
        ),
        "cases/history-001-theme-round-trip.json": (
            "eec3fa7c54e2d03604e6c367d35def50e32cb1f8a9f7bce8b51b191981923a47"
        ),
        "cases/history-002-override-round-trip.json": (
            "3caa7754f7a37615ca41ba5f0232cffa9e5674a5af47b6bc98e8d1318f0d5eaa"
        ),
        "cases/layout-001-main.json": (
            "a8c1247eaba99f750b33c57ba5148a2d94d937cc1f3bd8d1f96b48de768b14dd"
        ),
        "cases/layout-002-repeated-views.json": (
            "776e7bfaf8c30484bd9a7fcc71c92ac1ad3af2f49431449d335025ad49a1079f"
        ),
        "cases/layout-003-multi-process.json": (
            "4c94d4689f4a5690e95660347330f404b92931bd6742debe1b1d42cb9b47a1a1"
        ),
        "cases/layout-004-empty-process.json": (
            "84fc78bd7ad5d1f8886f525cdd086aa382d20d9ef4c30be7f67be5eb0cafd5ea"
        ),
        "cases/layout-005-missing-lane.json": (
            "3d46bde4d5690f7dab442eb1e1f8af870c01de3a5ecdf78c370c3a8b03e5b6dd"
        ),
        "cases/layout-006-neutral-fixture.json": (
            "4243a2bbfaf1ec75b50d1c2ea8a3d0f9d0c253926c39df19f7c371a11401fc06"
        ),
        "cases/layout-007-grid-fixture.json": (
            "0ab82f778bb3228c246d3c3fd64f3c85b2249fe418c099a1ae42867a5bc36959"
        ),
        "cases/layout-008-neutral-successor.json": (
            "48c4eebc28c12ed2b1c14e24404e7bc158837a956ef89ad3417ac54c53c5211e"
        ),
        "cases/layout-009-grid-successor.json": (
            "3db848f14bac6f14df714012e682c7276ff2364ff5f1b8198699d48420fc2679"
        ),
        "cases/layout-010-anchor-twice.json": (
            "d5dfc0b0815ec0c67d3348ef462b19d8dbf1c21594a5e2ef26bac4dc2053fc70"
        ),
        "cases/layout-011-geometry-theme-gated.json": (
            "1d54213a2d9fa6f5c8dc9d3fd9225c856cb8d24499ecefca21bee0134399cb8f"
        ),
        "cases/legacy-001-standard.json": (
            "9f17f68d2b0261d2c9c2358cd3a6e64c50ce768dee0bbb892738b0d5d5af62d9"
        ),
        "cases/legacy-002-legend.json": (
            "a0c83773dfbd776cf52ad450a2049fedbdada2b9f151492991dff9de2570b2a7"
        ),
        "cases/legacy-003-colored.json": (
            "ec94cf07958ae2d18746105ca2ac6075456c5d8f49025284c12b34ba34c204de"
        ),
        "cases/legacy-004-no-alias-data.json": (
            "34036d32cec0deaf9684f867791a4186a1141e0c58f6c21a70bab242b61c476e"
        ),
        "cases/legacy-005-exact-name.json": (
            "099239ae1171476f044d18ff728c5eedc51f2518e1ee93774f0cd4a6307c5276"
        ),
        "cases/legacy-006-alias-not-theme.json": (
            "ac84cfe0babcd411d4b2753237780b471f4377d040107d47f91baa7464fd5e5f"
        ),
        "cases/legacy-007-colored-sparse-di.json": (
            "a61c35b3f1b791232820ef2930cc715a001aa08edf28e4ecdb6a7ead22b6c5ea"
        ),
        "cases/legacy-008-look-independent-recognition.json": (
            "dfebc0f09098ce4b59c35aab42c987daef08f15e5d86476c8b7f0da29dd787ab"
        ),
        "cases/region-001-single-anchored.json": (
            "68194ca434c30b1a80953391190068d67037ddda36c2266a3aa6844e9a7e05b1"
        ),
        "cases/region-002-wider-label.json": (
            "793864a778928d554bd3264baf7bdf1a4729a85b2cc64d145ce6c892804a3090"
        ),
        "cases/region-003-collision-shift.json": (
            "cc4cb76d982407b1adc4ada1d7e3e8b4ec648ea830941a8af1420c0b29852292"
        ),
        "cases/region-004-no-anchor-sequence.json": (
            "9c0a3b1ad21142921b500b87cdf6020b1d09a92efaa584325f369b53d490053a"
        ),
        "cases/region-005-mixed-anchor.json": (
            "9eab4443fb649f24ecb457101685b9ba5ebd764b0e90a5830a5b74b8e60c022f"
        ),
        "cases/region-006-clamp-left.json": (
            "98dfe904ae626a6089d52cbef5d3ca1b235c38ae47b0847a2ce036d9b9215576"
        ),
        "cases/region-007-grow-lane-width.json": (
            "38143dc2ab79e78053f645283f2c4135ff14605fc056b576459ed40007a3efca"
        ),
        "cases/region-008-grow-page.json": (
            "379015f2c1ea5d75c1d90b0ec81a1fc339e00d4c708b3ede446019b77babf60a"
        ),
        "cases/region-009-grow-lane-height.json": (
            "508028239862e1a7c98675cfc49984380aa2e84c54c827cff6ce01075e9b361e"
        ),
        "cases/region-011-single-rounding.json": (
            "abdbc4e8c26d3c63952ec82b7fef2376880567ee4be1570afb0d6c6514d1c373"
        ),
        "cases/region-012-band-row.json": (
            "59855eeec54af0cdc2cf89c77a0b3c12744c453d868460f318124124e9ddb1f2"
        ),
        "cases/region-013-empty-region.json": (
            "f49d847e71a226ac554134ed99e5390869501e711f56a6cc9c376893d6b106ac"
        ),
        "cases/region-014-zero-tokens.json": (
            "55b6c78eb7ea85d7b8b407ebad9fae949fc0667835aada3e0ce77a11f665e07f"
        ),
        "cases/region-015-repeated-view.json": (
            "0f47b883fe1fec2822d4878dd13f5c13c706aaa69cc752e90e71a54c35b0f5b6"
        ),
        "cases/region-016-multi-band-a.json": (
            "87c87da1015e74609d34cedc93432439717c3df43bd54f9156e287b2e4c45c18"
        ),
        "cases/region-017-multi-band-b.json": (
            "327445905385dfc1fc1ea4ee8db26adc46efd9ecdbca773a7c2a40eeb3f7049a"
        ),
        "cases/render-001-main-plain.json": (
            "5184acadf1d81c5527a73435b5e04b8d38d2b12cbcce4e3b5e302db805376075"
        ),
        "cases/render-002-repeated-views.json": (
            "9681182b6a06a628b2845dce4954c5f9602126dd2d018d8b108abd8623b5a815"
        ),
        "cases/render-003-multi-process.json": (
            "24eb03d8e0c404a31aad8495a1ec8805cb2e5103b2ccdf7c62b252d6ad79f80e"
        ),
        "cases/render-004-empty-process.json": (
            "377b2815261aad079c238e20248219882d08efb27f2f8b9b3a7870c091917a80"
        ),
        "cases/render-005-neutral-fixture.json": (
            "a2314d2d192862d7c4452280b2615b2162318e7232ba0071351bc6f339029a94"
        ),
        "cases/render-006-token-precedence.json": (
            "16ae7434bb5ee856d7671b2f9297637b0ef5d2193ad2a1da533a61dbad75984a"
        ),
        "cases/render-007-reordered-bags.json": (
            "fced1b6c1f8ad07c570da88510b4e0cede141c309cbe8054b67a91b63649368b"
        ),
        "cases/render-008-sparse-occurrence-override.json": (
            "695a20f40d545e9a2116fec1fd1da29bc158d82297e6d71b4973c09330277c18"
        ),
        "cases/render-009-semantic-override.json": (
            "9182dc018023cd928c30046f473450ddfe8734e8502f428923d7e58f1d08c1ce"
        ),
        "cases/render-010-style-conflict.json": (
            "769441a4f1f526b09bd71995fb5cc483b9f872b0671a3f2b7d504a21c345b5b7"
        ),
        "cases/render-011-token-unknown.json": (
            "41f214524b5a0edd2e18646ed85cd6dee933bd8e721977ac2684c74e76929eeb"
        ),
        "cases/render-012-token-value.json": (
            "c15448f34227b43ff67223a8e8890c25bda252872d617b352c1eb4004a1fa056"
        ),
        "cases/render-013-token-negative.json": (
            "6bbb18045bc6ca3722500ab6f7dd005aaac0a60693f77f406778f5dd2e89af40"
        ),
        "cases/render-014-stale-choice-label.json": (
            "f8a6b97906ad6af1ba7dc731972e092baa6b462a8502a9d84473f1887479eefe"
        ),
        "cases/render-015-missing-label.json": (
            "b549be862be32141462b929f4ca9334ea408efe7aee34d704f4531fe274ba0c6"
        ),
        "cases/render-016-extra-label.json": (
            "98fd3b4cc92bf8e6a6f1c1c2316502d8471d78c8a2d9b280b0a6495704be29b1"
        ),
        "cases/render-017-unsupported-coverage.json": (
            "205af640bdaa794df82c10379aad7a1814dab3b9fffc8179f37ee2d9e471fb0d"
        ),
        "cases/render-018-unknown-theme.json": (
            "247b24c809f3868d46746e1cdb565da2e8a0d6093dfef1007e1d4f3bc525514a"
        ),
        "cases/render-019-theme-alias.json": (
            "3cc61036021f7b5153b281bdfbf5b6a450947ad3cfd887394dafd492ed87953c"
        ),
        "cases/render-020-geometry-theme-gated.json": (
            "57dcb6d7674366f43a4bd17d02102966eb59e65b05894ffd09fd0e4a27d1840c"
        ),
        "cases/render-021-neutral-successor.json": (
            "4adf4c7a37d47e596864a9d60400cc0b8f4e4a1ad98d7fa776b53fecd8fed805"
        ),
        "cases/render-022-grid-successor.json": (
            "e36dc310694a3093737681f688da608764a3a1c056fb8e7f0238926022301a6d"
        ),
        "cases/render-023-metric-chain.json": (
            "9c3d2941fa6e6300435986ae778642df2c3022504a800bc0f3310f7f5daa03f1"
        ),
        "cases/render-024-variety.json": (
            "8b1e08655c065ec730d6dc118ef8b81e6d7913506ec140a98740725591285911"
        ),
        "cases/switch-001-paint-only.json": (
            "37eb12819d299ff95aca0427ce98d42c86564a65865751077bf486dc6d630c3f"
        ),
        "cases/switch-002-region-token.json": (
            "f56d2909b4e8b73a5c0ab53f92fd78c5e024301a8f6b5c2be5b81c3b94ca7c78"
        ),
        "cases/switch-003-text-fit-token.json": (
            "29391c78624ea808e84482b8c22f6ace8b651a343cfdc29589900ecb0ed9008f"
        ),
        "cases/switch-004-own-geometry.json": (
            "ae61a8a213172ada9b07f668acd75a576857f997b77145415c3beb8c84b6ba3d"
        ),
        "cases/switch-005-missing-token.json": (
            "d1549f5a7524012127618989058b9a72b49a396243220a084ffd9bf77e3247e9"
        ),
        "cases/switch-006-legacy-chain.json": (
            "03489cd6e00dffa84710407bf00d3947493338a1c13053a112156b6235e7e565"
        ),
        "cases/switch-007-metrics-resource.json": (
            "35c79ac13c5f9b49aabfa06edb956988a15cc6df9f63419d32a9a3c9d56c27bf"
        ),
        "cases/synthetic-001-band-stripe.json": (
            "5f2c29dd974fb77bf018c93a6b78a3d610301fac63196b4c28c7d4ef7d4f4be9"
        ),
        "cases/synthetic-002-per-page.json": (
            "ba18bdd89897af2c8869f16772ca31e98f9366c4cbf0ec8217163dfb3377dd8f"
        ),
        "cases/synthetic-003-per-owner.json": (
            "4ab726bec7f7105f587f136334c4dad47462a66063b926bc670db9cbe344c03f"
        ),
        "cases/synthetic-004-region-missing.json": (
            "a14cd189cc5c7e26e7cd7a9dccf95e5184eb645f4bf111575ccb7175db14dccb"
        ),
        "cases/synthetic-005-grid-fixture.json": (
            "a07cd2c8d5fa36f103ad3734e517a863b7101ffe6556d00c696a1509b02769d4"
        ),
        "cases/synthetic-006-attached-badge.json": (
            "dda4fb81ab1d606094a3a18208b56d98dfbd68f4d6497073601e4d1c0d76bd34"
        ),
        "cases/synthetic-007-badge-ambiguous-anchor.json": (
            "370c662e4f929e8c3171325460459617bd15898c66cdccd5d2a2ec02265b7b9f"
        ),
        "cases/synthetic-008-badge-no-anchor.json": (
            "497926ad3a24b6f49cbf58121cf283a4a5010ca632e57af71f8f03acb3111dc5"
        ),
        "cases/synthetic-009-badge-hide-source.json": (
            "18881a2b4b2d7f53434d72e707703942ce78d91c05fc2efe449214c280f36bdc"
        ),
        "cases/synthetic-010-unbound-region.json": (
            "ec51ac148ba3ba894e13151fa4d01fed06e5c642d3c135b3a6671287eede8f26"
        ),
        "cases/synthetic-011-stripe-styled.json": (
            "8ae71a0f1a452e168afac5c8c19e710621ce253dd047af0ddcb6d77030351a87"
        ),
        "cases/synthetic-012-badge-styled.json": (
            "0aeabc3adafcb8692e77d1e459019572ddf595f5163fe474de1d55f5906d08be"
        ),
        "cases/synthetic-013-foreign-record.json": (
            "d59236a9bc632ac85aec6fb966d924a807b79b18faf52a5a1cd4aca04bc5167b"
        ),
        "cases/ticks-002-rational-not-binary.json": (
            "0d5ca097ae2a89d6f0f6694885aa5b62869eae21098de9044093ccdbcd3493e8"
        ),
        "cases/ticks-003-negative-zero-and-tiny.json": (
            "fe64da45a74bd97f0e07b7ca6c2dee139ab42eb48473c7f06dd73205fb804240"
        ),
        "cases/ticks-004-large-and-integral.json": (
            "d88ac00acee6127a626114c8a7fc1141a3ec67e0d3fdf05c82629263c22869d0"
        ),
        "manifest.json": "5648d7f2b9ab4ba1cc45487cf643d4545d55173f480ddde7f0f4cb520fbe4bf1",
        "seal.json": "5d50127e5eac2791d4699f6cf4094b803bd05c1681a445298bf74a06b892f2c0",
    },
    "export": {
        "artifacts/choices-plain.render.json": (
            "e5e007cbc2d871e238db9a043bfe2b4f277c71a9088755d673d6535406de0a49"
        ),
        "artifacts/choices-upper.layout.json": (
            "7bd3025f8326ed634ab5bf8db830860543ee8f15d756bfae5f9d359074a2b3b5"
        ),
        "artifacts/choices.envelope.json": (
            "38d28f627fb5e0b6f739ef218db7ac74a249fe3f7ec34640bb436dc2f390432d"
        ),
        "artifacts/empty-plain.render.json": (
            "9602802673762c7a5cf25d217d1f941fb4ea7dc7cc7cb152e38015436160df81"
        ),
        "artifacts/empty.envelope.json": (
            "0a7e64513915c17d08eeba54176afdfd6fbbc2311abb044d48206d0b16f7c175"
        ),
        "artifacts/empty.layout.json": (
            "23fc7b828a0fe06edddc82a7a16925941c5249a81980df7f66bb247f5742ef62"
        ),
        "artifacts/empty@byte-claim-plain.render.json": (
            "577cc9bcddb6f609b16922989cb347ebf083643c211a5b1725bfd69a80789987"
        ),
        "artifacts/empty@byte-claim.envelope.json": (
            "7eee7dadf4e186c482e1334c818d46b5dd7c229fa77f8b527a7770a7fe1d35d9"
        ),
        "artifacts/export-001-main-drawio.map-result.json": (
            "b388e5d6e05050bf5105c98e4a25677756fa1faed11e6e83acb610793da856b0"
        ),
        "artifacts/export-002-main-sparx-native.map-result.json": (
            "ad2cb94307bb7e0da244e997e452ae16ce931f0d1e862d8a6b07e7fcc250e9e9"
        ),
        "artifacts/export-003-repeated-drawio.map-result.json": (
            "cd10884bf45fbf60b0b657cf970148f7d53c51297ce245bda3c72bfa1f5be26d"
        ),
        "artifacts/export-005-multi-drawio.map-result.json": (
            "9fa627dec3e0e11e2b9cfb9d65c9b0938f72faaa975bae4d8a3ca1c9d2bd8c03"
        ),
        "artifacts/export-006-empty-drawio.map-result.json": (
            "de3a511d0817ba25b719d324274c506e852f4ce8a2188d143af9f843f707af92"
        ),
        "artifacts/export-007-synthetic-drawio.map-result.json": (
            "1dd7d2da877639d9f75c3846bc9750f4a5dc63fd151f5bcb9769557d09450a95"
        ),
        "artifacts/export-009-neutral-fixture.map-result.json": (
            "4f4289e9aaf62378139686c58dfa399ab666cf03af5b92d31adc17ad59d0195e"
        ),
        "artifacts/export-010-decision-labels.map-result.json": (
            "540c26a7da675ac0156790b82d306ab6ff864e4a456882403fcf7877af6ffeea"
        ),
        "artifacts/export-017-byte-claim-unqualified.map-result.json": (
            "0cddb3c5c29dfccdad96cc5b4e1e05e28bca145b9bdf36e1697a547195f93bff"
        ),
        "artifacts/export-025-neutral-successor.map-result.json": (
            "80719a075829082f489dc3ef4fe2993582504be1287fa2fac7a7ac8704215fc4"
        ),
        "artifacts/export-026-grid-successor.map-result.json": (
            "f23bb6e80029d3ce50c2127dc8e876bed6dff59b33521bffa87528f158d2a093"
        ),
        "artifacts/export-027-variety-drawio.map-result.json": (
            "2079e42da47522f520edaed477c442069cfca241f3dbbb89991a2782492a38f7"
        ),
        "artifacts/export-028-variety-sparx.map-result.json": (
            "d730cc9e6cc6c92a351e1ccf3b04565e8e8d23024dcde87abbbf9f8dae8f886f"
        ),
        "artifacts/grid-successor-plain.render.json": (
            "8bda5168f3071ef72f759e757303c2675711a2ac337050cd755e913be1b059ec"
        ),
        "artifacts/grid-successor.envelope.json": (
            "28ed484a6e23de6e4117e0f13aae43bb97df262698b9e6bcacd0f2ef0425cb50"
        ),
        "artifacts/grid-successor.layout.json": (
            "38e5487934bc7e951f9cc2e737d111d1931e2fa31c6d60d1cfcad5045f50573a"
        ),
        "artifacts/grid-successor.profile.json": (
            "e39fbd775d1538c825cdefe9c7d3a5cd179c7553cd2b243a23ead5a3c122f8d8"
        ),
        "artifacts/main-moved-occurrence.render.json": (
            "ab47b6d96cef4d45641c9711d2ac8ea796b4b67d02649088b253dfd18004abd3"
        ),
        "artifacts/main-note.envelope.json": (
            "88aa47074d31769ac83558876320d36587c6b7d925ee7f47ee083443e06025cf"
        ),
        "artifacts/main-note.layout.json": (
            "4e2b461cb568dc576c3520d2b764b475c3d1b038e5f29b5728ea0113f454483f"
        ),
        "artifacts/main-plain.render.json": (
            "78436ad0eb46393eecaa95a7cee447c4d3e16f7d32d24811fc3387177ea69183"
        ),
        "artifacts/main-renamed.layout.json": (
            "b8828280b41db622ab90ea7fd9b79003f5f0a1a56dbfdd2763409c4894d78e5b"
        ),
        "artifacts/main-renamed.prepared.json": (
            "8e257a0ae3b234381a1d78ad045518e37685c12f21f732ec775e3453645cf57c"
        ),
        "artifacts/main-striped.layout.json": (
            "0c01c961f1f84f4ae19b58e7654be110947cf7ced83726aef0e81cb60d92517a"
        ),
        "artifacts/main-striped.render.json": (
            "d2b8691907afe0f1d6139245a341cf9c15aec4346ad3d187530f18bd1c96eb21"
        ),
        "artifacts/main-tampered-label.render.json": (
            "a7b293d665c414bab7e3d3e322b05533fbdae6a5fba2c8ca5ef8ba58dcdc55fa"
        ),
        "artifacts/main-tampered-theme.render.json": (
            "7bbc62f694fcfbf4d4b68c84b76e9db802e994dbcf5eb4f94c7398fe1d001be2"
        ),
        "artifacts/main.envelope.json": (
            "407e44da330ed1d26bd6e151411ae9415dd3771b6915f84b553c10120d81c61f"
        ),
        "artifacts/main.layout.json": (
            "377e069bbaf287e4addb152628c4a4537bca331059eaae7002106a0036d5b9d1"
        ),
        "artifacts/main.prepared.json": (
            "08662cbd3cdc832b5e1b6b013cb83fd1249c9cd37e79df504691da16a24d132c"
        ),
        "artifacts/main@dup-emit-plain.render.json": (
            "4f45567865064b1035e7faaf096f4903c1af32f10245a6f892458f2662bd09db"
        ),
        "artifacts/main@dup-emit.envelope.json": (
            "7d44b622e27d9d65cc9f8954a9040a04228af3413c11b172b7366710873f393f"
        ),
        "artifacts/main@labels-native-plain.render.json": (
            "2b51ec1214ddc878495bf203adc43efe9eb1b9e59990c5114bcbbdcae8a9291e"
        ),
        "artifacts/main@labels-native.envelope.json": (
            "4d3e943d5d68fc3d1830c038486813f0a7057066f539b0657e9336a3bc1f3bc7"
        ),
        "artifacts/main@missing-field-plain.render.json": (
            "d3bf08c45d48728d453fa4c861e571021bd413e752c78fcf20b39f1066be0b7d"
        ),
        "artifacts/main@missing-field.envelope.json": (
            "899ab22d0aefe8bc428bf4ebcfad29fa75d5c4e34967de57906bed53efa4ec41"
        ),
        "artifacts/main@parent-order-plain.render.json": (
            "1a48c0cdf4a91a051d7bcbc798198e315a488dba63691524024e563612006cd9"
        ),
        "artifacts/main@parent-order.envelope.json": (
            "e3cb66bc15b8eb24494d5804f3ef3107507d13702347651a028679cafa98856f"
        ),
        "artifacts/main@unsupported-plain.render.json": (
            "6bf7993eadbd15025192d5654ba1af6fc20d8eb3e0cb0368fd9d36df693bef33"
        ),
        "artifacts/main@unsupported.envelope.json": (
            "3aa654d9c53a0d60a8d80ca39b90eb4194b4ebd34e2d335f100a87704afdd06b"
        ),
        "artifacts/multi-plain.render.json": (
            "a3858ffaba6c6d820bf786b29bc9c0d22b40e53fad0b27e489ec102e3f5b232f"
        ),
        "artifacts/multi.envelope.json": (
            "d2a0ebf7ec84fd68fc39e362b41c5895cba75d40701026aa029d868b7c2c8940"
        ),
        "artifacts/multi.layout.json": (
            "daafd1f8ce0b8fc6fed2a3542c564946cb60d5a89d71864b548aa9c91a43e2b0"
        ),
        "artifacts/multi.prepared.json": (
            "11fdc9605955cec0a7763da8eb43e0211bd793523e0cf1a9875dd5f0e47b98a1"
        ),
        "artifacts/neutral-fixture.envelope.json": (
            "8248f93b1e73045e810089da5be0c056220085ccd0d355e8623ea1691f490cab"
        ),
        "artifacts/neutral-fixture.layout.json": (
            "3258973f7068f9317ce8660d7eb1660dd8d149307b6be34d07023bc31387feb8"
        ),
        "artifacts/neutral-lot4-base.json": (
            "3599ac08a9ba1ce429f739f39ab6654d01ae57060ed612f8b14196bad817e7e8"
        ),
        "artifacts/neutral-lot4-byte-claim.profile.json": (
            "fcc858c1c50d41a3b0241e275ea8d3b2989e3f3028c80acd1cfd5867ccc7edad"
        ),
        "artifacts/neutral-lot4-descriptors.json": (
            "a2578b19578280b307d8140696cbf5a0b66cd0af6bf788e49e399e60f1d9390a"
        ),
        "artifacts/neutral-lot4-dup-emit.profile.json": (
            "ab2a92fb91ef95185a225286ec8d7e87337e830e929e96df85feea90afe394f3"
        ),
        "artifacts/neutral-lot4-labels-native.profile.json": (
            "25994e7567cfd36de3b62f4ccfb04b2332c2f72e702a767472fe91678cb01468"
        ),
        "artifacts/neutral-lot4-missing-field.profile.json": (
            "8d8c6d5553fc50975b31c9fe2e5da5219c539efa32189832cbf37122333ee7ac"
        ),
        "artifacts/neutral-lot4-parent-order.profile.json": (
            "ae7a40cd1f47e85b8ee637e21ce5597a2c3cf0f200281df713d5b362b70f9f16"
        ),
        "artifacts/neutral-lot4-profile.json": (
            "6b8f27c2ef5778cf29882fa8c7278b4945eb409105ebaf5ceb4e97c6c25b26c6"
        ),
        "artifacts/neutral-lot4-unsupported.profile.json": (
            "9c13886579df461b5f6ce7891407851d955170ebe7a53e0f52ddac8ab4ce4883"
        ),
        "artifacts/neutral-plain.render.json": (
            "7bd96ba4bb9fca9d705d696d141f45881ddcba6dbd6f386500357f40106d0aad"
        ),
        "artifacts/neutral-successor-plain.render.json": (
            "83f3c488c149155b6fa8ae5c2f1d5d7f7b9e3badb866518396bf2bda1d47e591"
        ),
        "artifacts/neutral-successor.envelope.json": (
            "399b75f2b82beea753d64661b504bcc7637d8ae45c85db6fee6c6c6829704ac9"
        ),
        "artifacts/neutral-successor.layout.json": (
            "ae975f82fa1e046ee0dd95af7904be58c7f0f2e714aedecdd83589d01dfb66ed"
        ),
        "artifacts/neutral-successor.profile.json": (
            "31387224e72609c153fc49e26c29e33de18fda7ab1fbabed55d25ba0bb21e658"
        ),
        "artifacts/note-plain.render.json": (
            "d9f6c30a9a1240e26b0f4866966d6c4e13789bc433ff1482a1cfa0731431fdfe"
        ),
        "artifacts/repeated-plain.render.json": (
            "95c5ef427ad663432b1961147bf1bcca19b8a0d22bd37a946ba25f99773c9598"
        ),
        "artifacts/repeated.layout.json": (
            "1eb7c1be5ac25ec87328fe8c95ac5f9bb5ea50920429801d108961a0bafc21a4"
        ),
        "artifacts/repeated.prepared.json": (
            "b760ea55f22a872b5e4b6ce2f9c40738b4aeb14950f898c2804bf4ae4421dea1"
        ),
        "artifacts/serialize-001-main-drawio.serialize-result.json": (
            "e1ac23fdfdde4f2a719e519371fffcc406d216bf22323a5e5e5d1e6858aff0d0"
        ),
        "artifacts/serialize-002-repeated-drawio.serialize-result.json": (
            "dd3143b0be4d12c298a94927e08a47bccf6eadca79e32551713d93e4de732c05"
        ),
        "artifacts/serialize-003-xml-escaping.serialize-result.json": (
            "e1ac23fdfdde4f2a719e519371fffcc406d216bf22323a5e5e5d1e6858aff0d0"
        ),
        "artifacts/serialize-005-stale-binding.prepared.json": (
            "a5d5edf3623d6b8118195f9e4a465e2b410188e2276fb2f1fab14096b99f2968"
        ),
        "artifacts/serialize-006-revision-mismatch.prepared.json": (
            "88d65422d575b3827d046c64544ac68c57b37188168d431aa02ca06184398de2"
        ),
        "artifacts/serialize-007-stale-profile-digest.prepared.json": (
            "3f5f7ad783f4fc520b0c20f4d1728cb71e38589f8006516080693715bb5b0f26"
        ),
        "artifacts/serialize-008-stale-descriptor-digest.prepared.json": (
            "1932033df5a6a7b3006b350ab632931f24c1301b514a1788e9caa7e1d65b5f2c"
        ),
        "artifacts/variety-plain.render.json": (
            "aaa8759f0990c507d3fe0657d10b035472634d38ed3eaa5b2f8adaf2044b33a7"
        ),
        "artifacts/variety.envelope.json": (
            "7fe9f9ecd969547da2475e7dea1819539efe4c21e3dca68617e6ef4ee6ea581e"
        ),
        "artifacts/variety.layout.json": (
            "23f41da0a6c5f50c0ed5a413e515ecc61e3ad7b6ba18af11319bb50385c87736"
        ),
        "artifacts/z-metrics.json": (
            "baf2ae3eff1522d8fdd4b7c24790cfa80cecb67392096c08008aa20a1babe8a4"
        ),
        "cases/bpmn-001-main-native.json": (
            "319617533daaf16803092e926eacc85ace56fedefbb34f87466044e61fad3996"
        ),
        "cases/bpmn-002-multi-native.json": (
            "e0f0996846feb3777d0b1e769bafdf49aafb14af17b3f6c45f8855359a759204"
        ),
        "cases/bpmn-003-variety-native.json": (
            "d6aedb63d65fd2c3e5e8e51e2f8669ee1c65e9fb6ecafb3a659c43ea8fec242c"
        ),
        "cases/export-001-main-drawio.json": (
            "9ed86f848bd8df55e09f80b6ef3ed92283b6ba062e18b392e46f474cde2f36c7"
        ),
        "cases/export-002-main-sparx-native.json": (
            "29e06d170b1fcfd863160f207edbe5bc4c0e61f09390a3169d8b2d9011b85c25"
        ),
        "cases/export-003-repeated-drawio.json": (
            "bab2af58b765cbb58014bc633205b9c7bf9f46f206a8cfd803bc519e00c37a75"
        ),
        "cases/export-004-repeated-sparx-ambiguous.json": (
            "c2e8bddf5a3f4801569dcaeba69a1e2d1a0e61fd0c3ce82078730d52a11956cc"
        ),
        "cases/export-005-multi-drawio.json": (
            "25ce2e52917b9dd984b25ed2613f1b2f7f02ced6a84b5ac2e69356dec76c5a5c"
        ),
        "cases/export-006-empty-drawio.json": (
            "98700bd195e716a4c38b15cb5df0d09fa1ecfbd79ab04c53a660c4c17b378403"
        ),
        "cases/export-007-synthetic-drawio.json": (
            "098433aaaf305bcddb14f0bc741be9e62d771ccb63994b64c4c7410a2b8e46b2"
        ),
        "cases/export-008-synthetic-sparx-ambiguous.json": (
            "bc1aa44c416c29269220606c537c9ed965547343da67061b397b3666aec61fe5"
        ),
        "cases/export-009-neutral-fixture.json": (
            "bdfc2a8344678110c5010146a007caaaa8751ffdd9eef86f70811390b4093cde"
        ),
        "cases/export-010-decision-labels.json": (
            "a322d267ec9b57561ffacf7bd31b1d6311d0b30b5d3734f1e93de2989d15f856"
        ),
        "cases/export-011-labels-native-ambiguous.json": (
            "060a266b4cc3c641c5cf2dd9336e6778abfa7038a4517d64393e4cd9a9b56197"
        ),
        "cases/export-012-parent-order.json": (
            "ed5cdeef5beb9f20b6e4303108180b23175523705d5f4cbd870f621b565294d1"
        ),
        "cases/export-013-duplicate-key.json": (
            "0304b52715e5a81248e317f82b62c395fde6fe1572f704d948979ce1528fa65e"
        ),
        "cases/export-014-missing-required.json": (
            "9ac6e2b717f03a5552d286f078d9610e5e73c492a60188fc6b84fa74f17a5168"
        ),
        "cases/export-015-unknown-format.json": (
            "7e94fbcff1f9228a033a19e01802bd42d6a18e422acce8f0853966c0e80c29cb"
        ),
        "cases/export-016-page-shape.json": (
            "9f3e0fa073e129a7e6b3a21f08d7d0d60ce5159dd12f7e37f665742665380972"
        ),
        "cases/export-017-byte-claim-unqualified.json": (
            "a8b13150620def0ffd110402e3db9a31f667bd33a4f3e8c4b8e79ac1125c4d25"
        ),
        "cases/export-018-unsupported-capability.json": (
            "1f5512c6ba0e9a716c1d56241a8f3eb450074eec7a9493a2871f18004126835a"
        ),
        "cases/export-019-unsupported-coverage.json": (
            "7ca1d88e940a2f22eccec2d5306665a1a8134b345b96fb8fe3a9c95da2a8a9ed"
        ),
        "cases/export-020-stale-layout.json": (
            "ac6c6f7e7c3a3962e9a6b7b2418507461971e86ec7d8c62bee24b7bebf5f8b92"
        ),
        "cases/export-021-stale-envelope.json": (
            "79b8be38b2d9b92cfb0b357deeea16025547a0eb6a933434b75e1235aa0cba88"
        ),
        "cases/export-022-stale-payload.json": (
            "5840edff3c3aac38a0c441eda5922c0acb498aa02b46b5bb21fdc5d14691115d"
        ),
        "cases/export-023-stale-theme.json": (
            "dbfa9f3960d2a968f87837dfa62a9528db3a557f3f83ed5820ee053a6dbbdcdd"
        ),
        "cases/export-024-occurrence-mismatch.json": (
            "41bca93cfe91f624c24c6f6df14fb59e87a667027f635c4f05d79cfe5ee63d13"
        ),
        "cases/export-025-neutral-successor.json": (
            "8cc7301fddd9ffcfb3634de5ac434bce61dfe23bccf079b1bce330e9da9786cd"
        ),
        "cases/export-026-grid-successor.json": (
            "d1caf668397e28928cd052b93b89c97d7b3945e04b4ed2dcfaddffa7bf6db001"
        ),
        "cases/export-027-variety-drawio.json": (
            "c7555864475763d17ee948e5416686fb80b0586e59fdc19dba6c41663154de0f"
        ),
        "cases/export-028-variety-sparx.json": (
            "c30ef448019ab1241998d71665f90376fa38139428cb6175691db4e0c0ebf4a3"
        ),
        "cases/idplan-001-counter-grid.json": (
            "f04e1c49e357242866f61f1555fe89d063ccafb2bf40ae05baba75a022a9d274"
        ),
        "cases/idplan-002-counter-domains.json": (
            "6245e83ba28814248978915b26aaf793e40f9c696d18747de5670807ef8007ef"
        ),
        "cases/idplan-003-digest.json": (
            "d0e33c7b6c6f622220f8062b101a727bbde8fe0d56b38d3732b1454080b32099"
        ),
        "cases/idplan-004-native-unique.json": (
            "27d6465d35db8f0e67cc83b6260a19a69c6690bdb3b6298fa782201e8df14805"
        ),
        "cases/idplan-005-native-duplicate.json": (
            "af32037805a317c5a7ca840a0c1b47cf57fb1c12f8d31c1b4f14a8c71c7420e2"
        ),
        "cases/idplan-006-native-synthetic.json": (
            "0d5835c210f1669c97c8d3eadda4ca6a62be58d0f6f5d1556b61b8260abf9afc"
        ),
        "cases/idplan-007-utf16-key-order.json": (
            "4a2b65b33bfbd3aeaa8174295d15b56721cc1abc3ee77c3875632126838b511d"
        ),
        "cases/serialize-001-main-drawio.json": (
            "d6fbcf56b04df732543f3bd1400c91a701746f0a08a49486075b0a4b94a46e8a"
        ),
        "cases/serialize-002-repeated-drawio.json": (
            "f30e5e118a41d546b1fcdc134a0d3f52e2dd59a3f372e22e8802379378ccb84f"
        ),
        "cases/serialize-003-xml-escaping.json": (
            "9e8d414c317401e5c43bd7ab7dcf2fd81994469e6b762830889bf129810c2976"
        ),
        "cases/serialize-004-determinism.json": (
            "51ed5aaacddf8b24a4c8e0a0c55795dda8403f2a8793583c69142dd5aa96f4b0"
        ),
        "cases/serialize-005-stale-binding.json": (
            "e0c9532a7c23e8e21e095086c746f29dca7739205c71dd3254d2ef895c4a2bc8"
        ),
        "cases/serialize-006-revision-mismatch.json": (
            "b4678e4d3929a3b44c357e7c06c2a74ff3e631f47dce69afebcc2c879bb217ee"
        ),
        "cases/serialize-007-stale-profile-digest.json": (
            "5e8e2cb5ab1a5a097dc93ea5d2cc4327ddcc065a41f0dd2938c676278c36d447"
        ),
        "cases/serialize-008-stale-descriptor-digest.json": (
            "8ac04ab429c4235136dab1a714325909aee618dab95e05788fff170909f4289e"
        ),
        "manifest.json": "5648d7f2b9ab4ba1cc45487cf643d4545d55173f480ddde7f0f4cb520fbe4bf1",
        "seal.json": "5d50127e5eac2791d4699f6cf4094b803bd05c1681a445298bf74a06b892f2c0",
    },
}

# Lot-0 contract bytes the JS cases reference (identical to the JS lot-0 corpus files).
VENDORED_CONTRACTS: dict[str, str] = {
    "contracts/profile-mechanism/1/neutral-base.json": (
        "a23a15d22585e765caeb8ad83bedb76c20bcb5fa1f7bee81ef062f4e97a15ea9"
    ),
    "contracts/profile-mechanism/1/neutral-descriptors.json": (
        "d737e07dc2b397bb02261fb5e7e46b51b7225f58fe82bebaa78cca2e613d62d2"
    ),
    "contracts/profile-mechanism/1/neutral-grid-profile.json": (
        "7247b5cd90c13fea2d42048a8ea6a5f3a36f64db67a771533adf10968c92cccd"
    ),
    "contracts/profile-mechanism/1/neutral-metrics.json": (
        "151d1a1fac1cbcab8ca53f155c3210437f4a2c285f6b68721973d1da6c362ee0"
    ),
    "contracts/profile-mechanism/1/neutral-profile.json": (
        "c1319045f538a9f4ef1f3f7500af4a3e0df059e04c7c42dd7e992477c9199650"
    ),
    "contracts/profile-mechanism/1/neutral-registry.json": (
        "ac4a09989f3fafd9e7695ba18901fac04d08ca4fa869600d5f715a34cf16039f"
    ),
    "contracts/profile-mechanism/1/profile-mechanism-1.schema.json": (
        "c97cfba64560ec0e7098294a5e185187de9d1f2207b272c2f002f576865692da"
    ),
}

# Byte-identical twins (parity sync PS-37): JS case id -> Python case, JS case file SHA-256.
ALIASES: dict[str, dict[str, str]] = {
    "region-010-mixed-heights": {
        "aliasOf": "render.regions.mixed-label-heights",
        "sha256": "71b1467b24883a5734e6666920ce4bbba5cd0c7e65db85c7a648b8c166d0fa6b",
    },
    "ticks-001-half-even": {
        "aliasOf": "render.ticks.half-even",
        "sha256": "e4a191ff2b477df763ca6dd990a7fd8f9fb041bd27b4353e1f00d4335ca600d8",
    },
}


def vendored_pin(path: str) -> str:
    """Return the pinned raw SHA-256 of one vendored file (repository-relative path)."""
    for tree, prefix in TREES.items():
        head = f"{prefix}/{VENDOR}/"
        if path.startswith(head):
            return VENDORED[tree][path[len(head) :]]
    return VENDORED_CONTRACTS[path]


def vendored_bytes(path: str) -> bytes:
    """Return the raw bytes of one vendored file after checking its pinned SHA-256."""
    data = (ROOT / path).read_bytes()
    if b(data) != vendored_pin(path):
        msg = f"{path}: vendored bytes changed"
        raise ValueError(msg)
    return data


def vendored_json(path: str) -> Json:
    """Return the JSON value of one vendored file (pin checked first)."""
    return json.loads(vendored_bytes(path).decode("utf-8"))


def js_path(tree: str, path: str) -> str:
    """Map one JS corpus path (relative to the JS ``tests/fixtures``) to its vendored path."""
    lot4 = "lot4-layout-export/expectations/"
    lot0 = "profile-parity-corpus/profile-mechanism/1/"
    if path.startswith(lot4):
        return f"{TREES[tree]}/{VENDOR}/{path[len(lot4) :]}"
    if path.startswith(lot0):
        return f"contracts/profile-mechanism/1/{path[len(lot0) :]}"
    msg = f"unmapped JS path {path!r}"
    raise ValueError(msg)


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
