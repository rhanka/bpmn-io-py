"""Standalone derivation helper for the lot-5 command expectations.

Stdlib only. It imports nothing from the library under test and never runs a
command, a recipe, C or N: it only recomputes the arithmetic that the sealed
expectation files pin, so a reviewer can re-derive every value by hand:

- ``profile-c14n/2`` canonical bytes and ``H(x)`` (DESIGN R3.3 §3.1);
- ``stable-id/1`` identifiers (DESIGN R3.3 §3.2);
- RFC 6902 compositions of the vendored contract files used by the fixture
  files (``fixture-*.json``);
- ``semanticRevision = H({tree, profileIdentity, bindings})`` of every
  envelope-shaped record found in an expectation file (DESIGN R3.3 §3.1, §5.1).

Usage (from the repository root)::

    python tests/profile_commands/expected/derive_helper.py check
    python tests/profile_commands/expected/derive_helper.py id OWNER SLOT KEY
    python tests/profile_commands/expected/derive_helper.py digest FILE [POINTER]
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent

ENVELOPE_KEYS = frozenset(
    {"documentVersion", "profileIdentity", "tree", "bindings", "semanticRevision"}
)
_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}
_SURROGATE_LOW = 0xD800
_SURROGATE_HIGH = 0xDFFF
_CONTROL_LIMIT = 0x20


class DerivationError(ValueError):
    """A value outside the subset this helper canonicalizes."""


def _jcs_string(text: str) -> str:
    parts = ['"']
    for char in text:
        code = ord(char)
        if char in _ESCAPES:
            parts.append(_ESCAPES[char])
        elif code < _CONTROL_LIMIT:
            parts.append(f"\\u{code:04x}")
        elif _SURROGATE_LOW <= code <= _SURROGATE_HIGH:
            msg = "lone surrogate"
            raise DerivationError(msg)
        else:
            parts.append(char)
    parts.append('"')
    return "".join(parts)


def _jcs_number(value: float) -> str:
    if isinstance(value, int):
        return str(value)
    if value.is_integer():
        return str(int(value))
    msg = "fractional numbers are outside the helper subset"
    raise DerivationError(msg)


_LITERALS = {"null": None, "true": True, "false": False}


def _jcs_container(value: object) -> str:
    if isinstance(value, list):
        return "[" + ",".join(jcs(entry) for entry in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return "{" + ",".join(_jcs_string(key) + ":" + jcs(value[key]) for key in keys) + "}"
    msg = f"unsupported JSON value {type(value).__name__}"
    raise DerivationError(msg)


def jcs(value: object) -> str:
    """Return the profile-c14n/2 (RFC 8785) text of ``value``.

    Object keys sort by UTF-16 code units (UTF-16BE byte order), arrays keep
    their order, strings use ECMAScript JSON escaping without normalization.
    """
    for text, literal in _LITERALS.items():
        if value is literal:
            return text
    if isinstance(value, (int, float)):
        return _jcs_number(value)
    if isinstance(value, str):
        return _jcs_string(value)
    return _jcs_container(value)


def digest(value: object) -> str:
    """Return ``H(x)``: lowercase SHA-256 of the UTF-8 profile-c14n/2 bytes."""
    return hashlib.sha256(jcs(value).encode("utf-8")).hexdigest()


def stable_id(owner_id: str, slot: str, key: str) -> str:
    """Return the stable-id/1 identifier for ``(ownerId, slot, stableKey)``."""
    return "g_" + digest(["profile-mechanism/1", owner_id, slot, key])


def paste_key(key: str, source_id: str) -> str:
    """Return the paste stableKey ``JCS([key, sourceId])`` (lot-5 binding)."""
    return jcs([key, source_id])


def _tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        msg = f"invalid JSON pointer {pointer!r}"
        raise DerivationError(msg)
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def _step(node: object, token: str) -> object:
    if isinstance(node, list):
        return node[int(token)]
    if isinstance(node, dict):
        return node[token]
    msg = f"pointer token {token!r} below a scalar"
    raise DerivationError(msg)


def resolve(document: object, pointer: str) -> object:
    """Resolve one RFC 6901 pointer inside ``document``."""
    node = document
    for token in _tokens(pointer):
        node = _step(node, token)
    return node


def _parent(document: object, pointer: str) -> tuple[object, str]:
    tokens = _tokens(pointer)
    if not tokens:
        msg = "patch target must not be the document root"
        raise DerivationError(msg)
    node = document
    for token in tokens[:-1]:
        node = _step(node, token)
    return node, tokens[-1]


def _patch_add(document: object, pointer: str, value: object) -> None:
    parent, last = _parent(document, pointer)
    if isinstance(parent, list):
        index = len(parent) if last == "-" else int(last)
        parent.insert(index, copy.deepcopy(value))
    elif isinstance(parent, dict):
        parent[last] = copy.deepcopy(value)
    else:
        msg = f"cannot add below {pointer!r}"
        raise DerivationError(msg)


def _patch_replace(document: object, pointer: str, value: object) -> None:
    parent, last = _parent(document, pointer)
    if isinstance(parent, list):
        parent[int(last)] = copy.deepcopy(value)
    elif isinstance(parent, dict) and last in parent:
        parent[last] = copy.deepcopy(value)
    else:
        msg = f"cannot replace missing {pointer!r}"
        raise DerivationError(msg)


def _patch_remove(document: object, pointer: str) -> None:
    parent, last = _parent(document, pointer)
    if isinstance(parent, list):
        del parent[int(last)]
    elif isinstance(parent, dict) and last in parent:
        del parent[last]
    else:
        msg = f"cannot remove missing {pointer!r}"
        raise DerivationError(msg)


def apply_patch(document: object, operations: list[dict[str, object]]) -> object:
    """Apply an RFC 6902 subset (add, replace, remove, test) to a deep copy."""
    result = copy.deepcopy(document)
    for operation in operations:
        op = operation["op"]
        pointer = str(operation["path"])
        if op == "add":
            _patch_add(result, pointer, operation["value"])
        elif op == "replace":
            _patch_replace(result, pointer, operation["value"])
        elif op == "remove":
            _patch_remove(result, pointer)
        elif op == "test":
            if jcs(resolve(result, pointer)) != jcs(operation["value"]):
                msg = f"patch test failed at {pointer!r}"
                raise DerivationError(msg)
        else:
            msg = f"unsupported patch op {op!r}"
            raise DerivationError(msg)
    return result


def load_json(path: Path) -> object:
    """Read one UTF-8 JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = "expected a JSON object"
        raise DerivationError(msg)
    return value


def compose_source(source: dict[str, object]) -> object:
    """Compose ``{"file", "pointer"?, "delta"}`` against a vendored file."""
    document = load_json(ROOT / str(source["file"]))
    pointer = source.get("pointer")
    if isinstance(pointer, str):
        document = resolve(document, pointer)
    delta = source.get("delta", [])
    if not isinstance(delta, list):
        msg = "delta must be an array"
        raise DerivationError(msg)
    return apply_patch(document, delta)


def fixture(name: str) -> dict[str, object]:
    """Load one fixture expectation file by name."""
    return _as_dict(load_json(HERE / name))


def composed_fixture_profile(name: str) -> dict[str, object]:
    """Compose the profile described by one ``fixture-profile-*.json`` file."""
    entry = fixture(name)
    return _as_dict(compose_source(_as_dict(_as_dict(entry["input"])["source"])))


def case_profile(case: dict[str, object]) -> dict[str, object] | None:
    """Compose the profile of one case (fixture profile plus case delta)."""
    case_input = _as_dict(case["input"])
    profile_ref = case_input.get("profile")
    if not isinstance(profile_ref, dict):
        return None
    profile = composed_fixture_profile(str(profile_ref["fixture"]))
    delta = profile_ref.get("delta", [])
    if not isinstance(delta, list):
        msg = "case profile delta must be an array"
        raise DerivationError(msg)
    return _as_dict(apply_patch(profile, delta))


def profile_identity(profile: dict[str, object]) -> dict[str, object]:
    """Return the DocumentEnvelope/1 profileIdentity record (DESIGN §5.1)."""
    return {
        "mechanismVersion": profile["mechanismVersion"],
        "schemaVersion": profile["schemaVersion"],
        "profile": profile["profile"],
        "version": profile["version"],
        "sha256": digest(profile),
        "base": profile["base"],
        "descriptors": profile["descriptors"],
    }


def sort_bindings(bindings: list[dict[str, object]]) -> list[dict[str, object]]:
    """Sort bindings by (ownerId, role, targetId) in UTF-16 order."""

    def _key(entry: dict[str, object]) -> tuple[bytes, bytes, bytes]:
        return (
            str(entry["ownerId"]).encode("utf-16-be"),
            str(entry["role"]).encode("utf-16-be"),
            str(entry["targetId"]).encode("utf-16-be"),
        )

    return sorted(bindings, key=_key)


def semantic_revision(
    tree: object, identity: dict[str, object], bindings: list[dict[str, object]]
) -> str:
    """Return ``H({tree, profileIdentity, bindings})`` for a DI-free tree."""
    return digest({"tree": tree, "profileIdentity": identity, "bindings": sort_bindings(bindings)})


def iter_envelopes(node: object) -> Iterator[dict[str, object]]:
    """Yield every envelope-shaped record below ``node`` (explicit stack)."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if set(current) == ENVELOPE_KEYS:
                yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _check_envelope(envelope: dict[str, object], identity: dict[str, object] | None) -> list[str]:
    problems: list[str] = []
    found = _as_dict(envelope["profileIdentity"])
    bindings = envelope["bindings"]
    if not isinstance(bindings, list):
        return ["envelope bindings are not an array"]
    if bindings != sort_bindings(bindings):
        problems.append("envelope bindings are not sorted")
    want = semantic_revision(envelope["tree"], found, bindings)
    if envelope["semanticRevision"] != want:
        problems.append(f"semanticRevision {envelope['semanticRevision']} != {want}")
    if identity is not None and digest(found) != digest(identity):
        problems.append("envelope profileIdentity differs from the case profile")
    return problems


def _check_ids(derived: dict[str, object]) -> list[str]:
    problems: list[str] = []
    for entry in derived.get("ids", []) if isinstance(derived.get("ids"), list) else []:
        record = _as_dict(entry)
        want = stable_id(str(record["ownerId"]), str(record["slot"]), str(record["key"]))
        if record["id"] != want:
            problems.append(f"stable id {record['id']} != {want}")
    return problems


def _check_load(case: dict[str, object], identity: dict[str, object] | None) -> list[str]:
    derived = case.get("derived")
    case_input = _as_dict(case["input"])
    document = case_input.get("document")
    if not isinstance(derived, dict) or not isinstance(document, dict) or identity is None:
        return []
    want = derived.get("loadRevision")
    if want is None:
        return []
    bindings = document.get("bindings", [])
    if not isinstance(bindings, list):
        return ["document bindings are not an array"]
    found = semantic_revision(document["tree"], identity, bindings)
    return [] if found == want else [f"loadRevision {want} != {found}"]


def check_case(case: dict[str, object]) -> list[str]:
    """Return the derivation problems of one non-fixture expectation file."""
    profile = case_profile(case)
    identity = profile_identity(profile) if profile is not None else None
    problems: list[str] = []
    derived = case.get("derived")
    if isinstance(derived, dict):
        problems.extend(_check_ids(derived))
        want_identity = derived.get("identity")
        if (
            want_identity is not None
            and identity is not None
            and digest(want_identity) != digest(identity)
        ):
            problems.append("derived identity differs from the composed profile")
    problems.extend(_check_load(case, identity))
    for envelope in iter_envelopes(case.get("expected")):
        problems.extend(_check_envelope(envelope, identity))
    for envelope in iter_envelopes(case.get("input")):
        problems.extend(_check_envelope(envelope, identity))
    return problems


def _check_document_fixture(entry: dict[str, object]) -> list[str]:
    composed = compose_source(_as_dict(_as_dict(entry["input"])["source"]))
    expected = _as_dict(entry["expected"])
    problems: list[str] = []
    if jcs(composed) != jcs(expected["document"]):
        problems.append("composed document differs from expected.document")
    pin = _as_dict(expected["pin"])
    if pin["sha256"] != digest(expected["document"]):
        problems.append("pin sha256 differs from H(document)")
    return problems


def _check_profile_fixture(entry: dict[str, object]) -> list[str]:
    profile = _as_dict(compose_source(_as_dict(_as_dict(entry["input"])["source"])))
    expected = _as_dict(entry["expected"])
    problems: list[str] = []
    if expected["profileSha256"] != digest(profile):
        problems.append(f"profileSha256 {expected['profileSha256']} != {digest(profile)}")
    if digest(expected["identity"]) != digest(profile_identity(profile)):
        problems.append("identity differs from the composed profile")
    base_pin = _as_dict(fixture("fixture-base.json")["expected"])["pin"]
    descriptor_pin = _as_dict(fixture("fixture-descriptors.json")["expected"])["pin"]
    if digest(profile["base"]) != digest(base_pin):
        problems.append("profile base pin differs from fixture-base.json")
    if digest(profile["descriptors"]) != digest([descriptor_pin]):
        problems.append("profile descriptor pins differ from fixture-descriptors.json")
    return problems


def check_file(path: Path) -> list[str]:
    """Return the derivation problems of one expectation file."""
    entry = _as_dict(load_json(path))
    name = path.name
    if name in ("fixture-descriptors.json", "fixture-base.json"):
        return _check_document_fixture(entry)
    if name.startswith("fixture-profile-"):
        return _check_profile_fixture(entry)
    return check_case(entry)


def check_all() -> list[str]:
    """Recompute every derived value of every expectation file."""
    problems: list[str] = []
    for path in sorted(HERE.glob("*.json")):
        problems.extend(f"{path.name}: {problem}" for problem in check_file(path))
    return problems


def main(argv: list[str]) -> int:
    """Run the command line (``check``, ``id`` or ``digest``)."""
    if argv[:1] == ["check"]:
        problems = check_all()
        for problem in problems:
            sys.stderr.write(problem + "\n")
        sys.stdout.write("ok\n" if not problems else f"{len(problems)} problem(s)\n")
        return 1 if problems else 0
    if len(argv) == 4 and argv[0] == "id":
        sys.stdout.write(stable_id(argv[1], argv[2], argv[3]) + "\n")
        return 0
    if len(argv) in (2, 3) and argv[0] == "digest":
        value = load_json(Path(argv[1]))
        if len(argv) == 3:
            value = resolve(value, argv[2])
        sys.stdout.write(digest(value) + "\n")
        return 0
    sys.stderr.write(__doc__ or "")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
