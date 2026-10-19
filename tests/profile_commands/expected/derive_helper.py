"""Standalone derivation helper for the lot-5 command expectations.

Stdlib only. It imports nothing from the library under test and never runs a
command, a recipe, C, N or a lint rule: it only recomputes the arithmetic and
the bookkeeping that the sealed expectation files pin, so a reviewer can
re-derive every value by hand:

- ``profile-c14n/2`` canonical bytes and ``H(x)`` (DESIGN R3.3 §3.1);
- ``stable-id/1`` identifiers (DESIGN R3.3 §3.2);
- RFC 6902 compositions of the vendored contract files used by the fixture
  files (``fixture-*.json``) and the committed byte artifacts under
  ``artifacts/`` (exactly the profile-c14n/2 bytes of each composition);
- ``semanticRevision = H({tree, profileIdentity, bindings})`` of every
  envelope-shaped record found in an expectation file (DESIGN R3.3 §3.1, §5.1);
- the closed Result/1 and Report/2 bookkeeping of every sealed result
  (header members, ``diagnostics == report.entries`` on refusal, the
  ``profile-report/2`` entry order of DESIGN R3.3 §10.1) and the archived
  ``importedDi`` digests (DESIGN R3.3 §8.1.1);
- the ``profile-parity-corpus/1`` projection of every case under ``parity/``
  (a transcription of the harness values, DESIGN R3.3 §14.3);
- the raw SHA-256 of every JS file vendored under ``vendor/js/`` (``VENDORED``:
  the pins of the owning JS seals, block-B parity sync), the value members of
  every vendored harness record re-derived from its vendored JS case
  (``vendored_record``) and the arithmetic of the vendored values (envelope
  revisions, Result/1 and Report/2 bookkeeping, archived importedDi digests).

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
    from collections.abc import Callable, Iterator

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


def read_artifact(path: str) -> bytes:
    """Return the raw bytes of one committed artifact (path relative to this directory)."""
    return (HERE / path).read_bytes()


def raw_digest(data: bytes) -> str:
    """Return ``B(bytes)``: lowercase SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _check_profile_artifact(
    case: dict[str, object], profile: dict[str, object] | None
) -> list[str]:
    profile_ref = _as_dict(case["input"]).get("profile")
    if not isinstance(profile_ref, dict) or profile is None:
        return []
    artifact = profile_ref.get("artifact")
    if not isinstance(artifact, str):
        return ["input.profile.artifact is missing"]
    if read_artifact(artifact) != jcs(profile).encode("utf-8"):
        return [f"{artifact} is not the profile-c14n/2 bytes of the composed profile"]
    return []


_STAGES = (
    "load",
    "import",
    "complete",
    "pre-normalize",
    "normalize",
    "post-normalize",
    "layout",
    "post-layout",
    "release",
    "render",
    "export",
)


def _u16(text: object) -> bytes:
    return str(text).encode("utf-16-be")


def _nullable(value: object) -> tuple[int, bytes]:
    return (0, b"") if value is None else (1, _u16(value))


def _optional(entry: dict[str, object], key: str) -> tuple[int, bytes]:
    if key not in entry:
        return (0, b"")
    value = entry[key]
    return (1, _u16(value if isinstance(value, str) else jcs(value)))


def _present(entry: dict[str, object], flag: str, key: str) -> tuple[int, bytes]:
    return (1, _u16(jcs(entry[key]))) if entry.get(flag) else (0, b"")


def entry_order_key(entry: dict[str, object]) -> tuple[object, ...]:
    """Return the profile-report/2 sort key (DESIGN R3.3 §10.1 L751 plus tie-breaks).

    Stage rank, ruleId, source domain, source pointer and targetId (null
    first), code, pageId and occurrenceKey (absent first), canonical before and
    after (absent first), then result domain, pointer and targetId, then
    property (absent first); UTF-16 code-unit order throughout.
    """
    source = _as_dict(entry["source"])
    result = _as_dict(entry["result"])
    return (
        _STAGES.index(str(entry["stage"])),
        _u16(entry["ruleId"]),
        _u16(source["domain"]),
        _nullable(source["pointer"]),
        _nullable(source["targetId"]),
        _u16(entry["code"]),
        _optional(entry, "pageId"),
        _optional(entry, "occurrenceKey"),
        _present(entry, "beforePresent", "before"),
        _present(entry, "afterPresent", "after"),
        _u16(result["domain"]),
        _nullable(result["pointer"]),
        _nullable(result["targetId"]),
        _optional(entry, "property"),
    )


_SUCCESS_KEYS = frozenset(
    {"status", "operation", "profileIdentity", "baseRevision", "revision", "report", "payload"}
)
_REFUSAL_KEYS = frozenset(
    {"status", "operation", "profileIdentity", "baseRevision", "code", "diagnostics", "report"}
)
_REPORT_KEYS = frozenset(
    {
        "reportVersion",
        "operation",
        "sourceIdentity",
        "targetIdentity",
        "inputRevision",
        "outputRevision",
        "entries",
        "rawStandardFindings",
        "idMap",
        "artifacts",
    }
)


def _check_report_entries(entries: object) -> list[str]:
    if not isinstance(entries, list):
        return ["report entries are not an array"]
    keys = [entry_order_key(_as_dict(entry)) for entry in entries]
    if keys != sorted(keys):
        return ["report entries are not in profile-report/2 order"]
    return []


def _check_success(result: dict[str, object], report: dict[str, object]) -> list[str]:
    problems: list[str] = []
    if set(result) != _SUCCESS_KEYS:
        problems.append("success result is not the closed Result/1 success record")
    identity = result.get("profileIdentity")
    if report.get("sourceIdentity") != identity or report.get("targetIdentity") != identity:
        problems.append("success report identities differ from profileIdentity")
    if report.get("inputRevision") != result.get("baseRevision"):
        problems.append("report inputRevision differs from baseRevision")
    if report.get("outputRevision") != result.get("revision"):
        problems.append("report outputRevision differs from revision")
    return problems


def _check_refusal(result: dict[str, object], report: dict[str, object]) -> list[str]:
    problems: list[str] = []
    if not set(result) <= _REFUSAL_KEYS or not {"status", "operation", "code"} <= set(result):
        problems.append("refusal is not the closed Result/1 refusal record")
    if ("profileIdentity" in result) != ("baseRevision" in result):
        problems.append("refusal echoes only one of profileIdentity and baseRevision")
    if report.get("sourceIdentity") != result.get("profileIdentity"):
        problems.append("refusal report sourceIdentity differs from the echo")
    if report.get("inputRevision") != result.get("baseRevision"):
        problems.append("refusal report inputRevision differs from the echo")
    if "targetIdentity" in report or "outputRevision" in report:
        problems.append("refusal report carries targetIdentity or outputRevision")
    if jcs(result.get("diagnostics")) != jcs(report.get("entries")):
        problems.append("refusal diagnostics differ from report.entries")
    return problems


def check_result(result: dict[str, object]) -> list[str]:
    """Check the closed union bookkeeping of one sealed Result/1 template."""
    report = result.get("report")
    if not isinstance(report, dict):
        return ["Result/1 template without report"]
    problems: list[str] = []
    if not set(report) <= _REPORT_KEYS or report.get("reportVersion") != "2":
        problems.append("report is not a closed Report/2 record")
    if report.get("operation") != result.get("operation"):
        problems.append("report operation differs from the result operation")
    problems.extend(_check_report_entries(report.get("entries")))
    if result.get("status") == "ok":
        problems.extend(_check_success(result, report))
    else:
        problems.extend(_check_refusal(result, report))
    return problems


def iter_results(node: object) -> Iterator[dict[str, object]]:
    """Yield every Result/1-shaped template below ``node`` (explicit stack)."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if "operation" in current and current.get("status") in ("ok", "refused"):
                yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def check_imported_di(record: dict[str, object], descriptor_pins: object) -> list[str]:
    """Check one archived importedDi record (DESIGN R3.3 §8.1.1, lot-4 descriptorDigest)."""
    problems: list[str] = []
    if not isinstance(descriptor_pins, list):
        return ["descriptor pins are not an array"]
    pins = sorted(descriptor_pins, key=lambda pin: _u16(_as_dict(pin)["id"]))
    if record.get("descriptorDigest") != digest(pins):
        problems.append("importedDi descriptorDigest differs from H(sorted descriptor pins)")
    payload = {
        "descriptorDigest": record.get("descriptorDigest"),
        "diagrams": record.get("diagrams"),
    }
    if record.get("sha256") != digest(payload):
        problems.append("importedDi sha256 differs from H({descriptorDigest, diagrams})")
    return problems


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
    compiled_identity = _as_dict(case["expected"]).get("compiledIdentity")
    if compiled_identity is not None and (
        identity is None or digest(compiled_identity) != digest(identity)
    ):
        problems.append("expected.compiledIdentity differs from the composed profile identity")
    problems.extend(_check_load(case, identity))
    problems.extend(_check_profile_artifact(case, profile))
    for envelope in iter_envelopes(case.get("expected")):
        problems.extend(_check_envelope(envelope, identity))
    for envelope in iter_envelopes(case.get("input")):
        problems.extend(_check_envelope(envelope, identity))
    for result in iter_results(case.get("expected")):
        problems.extend(check_result(result))
    document = _as_dict(case["input"]).get("document")
    if isinstance(document, dict) and "importedDi" in document and profile is not None:
        problems.extend(check_imported_di(_as_dict(document["importedDi"]), profile["descriptors"]))
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
    data = read_artifact(str(expected["artifact"]))
    if data != jcs(expected["document"]).encode("utf-8") or raw_digest(data) != pin["sha256"]:
        problems.append("committed package bytes differ from the pinned profile-c14n/2 bytes")
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
    if read_artifact(str(expected["artifact"])) != jcs(profile).encode("utf-8"):
        problems.append("committed profile bytes differ from the composed profile")
    return problems


# ----------------------------------------------------------- parity projection
PARITY_PREFIX = "lot5-py-"
PATH_BASE = "tests/profile_commands/expected/"
DESCRIPTOR_ARTIFACT = "artifacts/neutral-descriptors.lot5.json"
BASE_ARTIFACT = "artifacts/neutral-base.lot5.json"
ACTIONS = {
    "apply_commands": "applyCommands",
    "undo": "undo",
    "redo": "redo",
    "get_snapshot": "getSnapshot",
    "get_definitions": "getDefinitions",
    "dispose": "dispose",
    "activate": "activateBusinessProfile",
    "set_definitions": "setDefinitions",
    "list_entries": "listEntries",
    "list_fields": "listFields",
    "check_field": "checkField",
    "query_references": "queryReferences",
    "copy": "copy",
    "localize": "localize",
    "on_change": "onChange",
    "events": "events",
}
COMPARATORS = [
    {
        "id": "lot5-py/step-outcomes",
        "kind": "parity",
        "note": (
            "One headless bridge per case: create it with the descriptors artifact (or "
            "the bridge input), load the envelope input (with importedDi when given) and "
            "activate the compiled profileArtifact, each result matching the setup "
            "outcomes; then run the sequence steps in order. Every actual result equals "
            "its outcome template under profile-c14n/2 after each {$unsealed} marker is "
            "replaced by the actual member it marks (the member must exist); equal/differ "
            "compare a pointer with a saved result; signal results match per action. "
            "Placeholders {$current} and {$saved} are resolved before the request runs "
            "(SPEC_PROFILE_COMMANDS_PY.md section 8)."
        ),
    },
    {
        "id": "lot5-py/compile-outcome",
        "kind": "parity",
        "note": (
            "loadProfile then compileProfile on the profileArtifact bytes with the base "
            "and descriptors artifacts: the first refusal as {status, code, diagnostics}, "
            "or the success {status: ok, payload, diagnostics} whose payload (the compiled "
            "profile, no wire shape) is the {$unsealed: compiled-profile} member."
        ),
    },
    {
        "id": "lot5-py/compiled-identity",
        "kind": "parity",
        "note": (
            "The profileIdentity record (DESIGN R3.3 §5.1) carried by the compiled profile "
            "of a compile success, exact under profile-c14n/2."
        ),
    },
    {
        "id": "profile-c14n/2",
        "kind": "mechanism",
        "note": "RFC 8785 JCS bytes, UTF-16 key order (DESIGN R3.3 §3.1).",
    },
    {
        "id": "stable-id/1",
        "kind": "mechanism",
        "note": "Allocated IDs recompute (DESIGN R3.3 §3.2).",
    },
]


def _outcome_status(result: object) -> str:
    record = _as_dict(result)
    if record.get("status") == "refused":
        return f"refused:{record['code']}"
    return "ok"


def _parity_operation(case_input: dict[str, object], expected: dict[str, object]) -> str:
    if "compile" in expected:
        return "compileProfile"
    actions = sorted(
        {ACTIONS[str(_as_dict(entry)["op"])] for entry in _as_list(case_input["steps"])}
    )
    return actions[0] if len(actions) == 1 else "sequence"


def _parity_inputs(
    case: dict[str, object], read: Callable[[str], bytes]
) -> list[dict[str, object]]:
    case_input = _as_dict(case["input"])
    inputs: list[dict[str, object]] = [
        {
            "role": "descriptors",
            "path": DESCRIPTOR_ARTIFACT,
            "sha256": raw_digest(read(DESCRIPTOR_ARTIFACT)),
        },
        {"role": "base", "path": BASE_ARTIFACT, "sha256": raw_digest(read(BASE_ARTIFACT))},
    ]
    if "bridge" in case_input:
        inputs.append({"role": "bridge", "json": case_input["bridge"]})
    document = case_input.get("document")
    if isinstance(document, dict):
        identity = profile_identity(_as_dict(case_profile(case)))
        bindings = sort_bindings(list(_as_list(document.get("bindings", []))))
        envelope = {
            "documentVersion": "1",
            "profileIdentity": identity,
            "tree": document["tree"],
            "bindings": bindings,
            "semanticRevision": semantic_revision(document["tree"], identity, bindings),
        }
        inputs.append({"role": "envelope", "json": envelope})
        if "importedDi" in document:
            inputs.append({"role": "importedDi", "json": document["importedDi"]})
    return inputs


def _parity_sequence(steps: object) -> dict[str, object]:
    sequence = []
    for index, entry in enumerate(_as_list(steps)):
        item = _as_dict(entry)
        step: dict[str, object] = {"step": index + 1, "action": ACTIONS[str(item["op"])]}
        if "args" in item:
            step["request"] = item["args"]
        if "save" in item:
            step["save"] = item["save"]
        sequence.append(step)
    return {"role": "sequence", "json": {"sequenceVersion": "1", "steps": sequence}}


def _parity_expected(case: dict[str, object], record: dict[str, object]) -> None:
    expected = _as_dict(case["expected"])
    if "compile" in expected:
        artifacts = [{"role": "compile-outcome", "json": expected["compile"]}]
        comparators = ["lot5-py/compile-outcome"]
        if "compiledIdentity" in expected:
            artifacts.append({"role": "compiled-identity", "json": expected["compiledIdentity"]})
            comparators.append("lot5-py/compiled-identity")
        record["expectedArtifacts"] = artifacts
        record["expectedStatus"] = _outcome_status(expected["compile"])
        record["comparatorIds"] = [*comparators, "profile-c14n/2"]
        return
    outcomes: list[dict[str, object]] = []
    if "setup" in expected:
        outcomes.append({"role": "setup-outcomes", "json": expected["setup"]})
    outcomes.append({"role": "step-outcomes", "json": expected["steps"]})
    record["expectedArtifacts"] = outcomes
    expected_steps = _as_list(expected["steps"])
    single = _as_dict(_as_dict(expected_steps[0])["result"]) if len(expected_steps) == 1 else {}
    record["expectedStatus"] = _outcome_status(single) if "status" in single else "ok"
    comparators = ["lot5-py/step-outcomes", "profile-c14n/2"]
    derived = case.get("derived")
    if isinstance(derived, dict) and derived.get("ids"):
        comparators.append("stable-id/1")
    record["comparatorIds"] = comparators


def parity_record(
    case: dict[str, object], artifacts: dict[str, bytes] | None = None
) -> dict[str, object]:
    """Project one harness case to a profile-parity-corpus/1 record (pure transcription)."""

    def read(path: str) -> bytes:
        return artifacts[path] if artifacts is not None else read_artifact(path)

    case_input = _as_dict(case["input"])
    expected = _as_dict(case["expected"])
    artifact = str(_as_dict(case_input["profile"])["artifact"])
    record: dict[str, object] = {
        "caseId": PARITY_PREFIX + str(case["case"]),
        "operation": _parity_operation(case_input, expected),
        "phase": None,
        "profileArtifact": {"path": artifact, "sha256": raw_digest(read(artifact))},
        "inputArtifacts": _parity_inputs(case, read),
    }
    if "compile" not in expected:
        record["commandArtifact"] = _parity_sequence(case_input["steps"])
    _parity_expected(case, record)
    return record


def parity_text(record: dict[str, object]) -> str:
    """Return the committed text of one parity record (sorted keys, compact, ASCII, LF)."""
    return json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"


def parity_manifest(files: dict[str, str], vendored: list[dict[str, object]]) -> dict[str, object]:
    """Return the parity manifest (parity files, referenced artifacts, vendored cases)."""
    return {
        "comparators": COMPARATORS,
        "corpusVersion": "lot5-py-1",
        "files": dict(sorted(files.items(), key=lambda item: _u16(item[0]))),
        "format": "profile-parity-corpus/1",
        "notes": [
            "pathBase is the directory every path below is relative to.",
            (
                "Each parity case is a transcription of the harness case of the same name "
                "(lot5-py- prefix removed); derive_helper.py check re-derives it byte for byte."
            ),
            (
                "Profile and package artifacts are the exact profile-c14n/2 bytes of their "
                "compositions, so raw SHA-256 equals H(document)."
            ),
            (
                "vendored lists the JS cases vendored by the block-B parity sync (source: the "
                "JS repository path; sha256: the pin of the owning JS seal); their harness "
                "records and raw files live under pathBase, and they are not re-published "
                "under parity/ because the owning JS seal publishes their corpus records."
            ),
        ],
        "pathBase": PATH_BASE,
        "vendored": vendored,
    }


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        msg = "expected a JSON array"
        raise DerivationError(msg)
    return value


def expected_parity() -> dict[str, str]:
    """Return the expected text of every parity file, keyed by path."""
    texts: dict[str, str] = {}
    for path in sorted(HERE.glob("*.json")):
        if path.name.startswith("fixture-"):
            continue
        case = _as_dict(load_json(path))
        if is_vendored(case):
            continue
        record = parity_record(case)
        texts[f"parity/{record['caseId']}.json"] = parity_text(record)
    return texts


def check_parity() -> list[str]:
    """Re-derive every parity file and the parity manifest."""
    problems: list[str] = []
    texts = expected_parity()
    parity_dir = HERE / "parity"
    found = {
        f"parity/{path.name}" for path in parity_dir.glob("*.json") if path.name != "manifest.json"
    }
    if found != set(texts):
        problems.append("parity directory does not hold exactly one record per harness case")
    files: dict[str, str] = {}
    for rel, text in texts.items():
        target = HERE / rel
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            problems.append(f"{rel} differs from the projection of its harness case")
        files[rel] = raw_digest(text.encode("utf-8"))
    for path in sorted((HERE / "artifacts").rglob("*.json")):
        files[path.relative_to(HERE).as_posix()] = raw_digest(path.read_bytes())
    manifest = parity_dir / "manifest.json"
    derived = parity_manifest(files, vendored_parity_list())
    want = json.dumps(derived, indent=2, ensure_ascii=True) + "\n"
    if not manifest.is_file() or manifest.read_text(encoding="utf-8") != want:
        problems.append("parity/manifest.json differs from the derived manifest")
    return problems


# ------------------------------------------------------------ vendored JS files
#: Raw SHA-256 of every vendored JS file (block-B parity sync, harmonization §3),
#: keyed by its path relative to this directory. ``vendor/js/`` mirrors the JS
#: ``tests/fixtures/`` directory and holds the files unchanged; each digest is the
#: pin of the owning JS seal: the lot-5 ``manifest.json`` ``files`` for the lot-5
#: cases and fixtures, the lot-3 ``manifest.json`` ``files`` for the lot-3 case,
#: the lot-3 ``seal.json`` ``files`` for its profile, descriptor and base packages
#: and the lot-3 ``seal.json`` ``inputs`` for the lot-0 metrics asset.
VENDORED: dict[str, str] = {
    "vendor/js/lot3-cn/expectations/cases/l3-tx-incremental-draft.json": (
        "b6d947ff17000c1af7d6faeffe7e886cae8bb6fa2b2b92e3f39c4683200243ea"
    ),
    "vendor/js/lot3-cn/expectations/profile/neutral-cn-base.json": (
        "92ed7564f70e2ab45c0b042f1621d37b0c9ffb2e24466ed9d35a75a275fd281a"
    ),
    "vendor/js/lot3-cn/expectations/profile/neutral-cn-descriptors.json": (
        "de6bd1eee25c76da263e67e1302be70fa5cb045a18721254a1bd08c29c67b7b3"
    ),
    "vendor/js/lot3-cn/expectations/profile/neutral-cn.json": (
        "f94d4589a850bdf664612bc10e61be88efc6bae7d1f8e25f6b70b919f5096c32"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-001-flow-programmatic.json": (
        "dd5864416b925b15045c79f6ba0d48aab5e5202f8442309e7dd328b4b58685b3"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-003-reference-link-programmatic.json": (
        "96963a3100a81fdb0f80b2e428a11c1cddaee306919658329ea5fa8711bcf533"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-005-item-input.json": (
        "298667fdbec3a35823559a4b44dc398497a8ef700aa30b6f8d2f1ea50bff130d"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-006-item-output.json": (
        "1e5db209072fd8f21f6338a24d34dd8ca8991fab56be5042e1dbf83ad6109a67"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-007-annotation-link.json": (
        "cf1df507a3847c36873b6dbdc152c1e6a417afe9a5530520e7948360edaecd08"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-008-reference-to-call.json": (
        "6f73ddb86e835e766a7a30708d10fecc671bfcd064f702fc633d1e13cd0a91ee"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-009-ineligible-target-noop.json": (
        "9a2445f2b6de63f9cffe7989bb98d3b14941079b3c00800a06f13a61614dcf98"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-011-flow-from-end.json": (
        "00b21d9e092c2997234f26787b660e82cc5224f755abdb5cd8595ccf37cf4a04"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-001-append-task-programmatic.json": (
        "80e6e61bbaf17f52bc689dfda2533a6c4d248754bd985fdd785dff1d3c47c8c8"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-003-append-end.json": (
        "f1131b32416e4a0a2dcdb22f292b2298e94424c9c8dae55919d73f5f07ab0af7"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-004-aid-attach.json": (
        "77d3ee7f8311072b46548fe0ddd39c1100367a06ba9728ab60144c0c3def9499"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-005-append-on-end.json": (
        "185e43b868cf2b941e2b347d1312d631c14ee6861f0c8f82418b6f247ce78f4e"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-006-call-unlink.json": (
        "2994158698029f05ffec9457a1b2e6a69fbe5fc0550573d75b5d105fcf6db4a9"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-007-call-unlink-noop.json": (
        "a9852a52a7e36dcb03c7868a5145d843c35a40fe80c4f6b3901f49a3cf0070e7"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-001-reference-with-links.json": (
        "00cf63d41d6125045518609cf1cf9996e2104bce33939320ad11b3f78ab2d5b2"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-002-unconnected-task.json": (
        "048a9dff905c786528c129b9137b171a5659e672ef9aff3e8384ed3654bb6cda"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-003-outgoing-only.json": (
        "c7a9c140280c9fb83ea8e6b265ef675ebfca197006a72f1a3e7472fa8fe0407f"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-004-incoming-refused.json": (
        "86a76fdeb16cb2dedcabe865378f51b14bf18193d2e24e3232c539715d877ae0"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-005-flow.json": (
        "e78b8f307a66961db53b1ca400656d4b8dc838a897266e0c4f0f6fb14d6ee593"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-008-multi-atomic.json": (
        "6f1e69ada6ec27ee59628eaa052064590ca0938396b3df9ada2efe4b4d92db19"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-009-annotation-with-link.json": (
        "a265c607df82bc42bc6e4e46b00e7c5e7610efc8b30f3ee1471d0546f3abe51a"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-010-process-disabled.json": (
        "dd38d350fd56c727d6fdfcbd018e17bc1cb91040820d3635f8822db66cefd4a1"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-011-last-element-keeps-empty-array.json": (
        "96a7587563eee3c7111612025536d9484fb7596e35bdcacc7962272569d7b584"
    ),
    "vendor/js/lot5-ui/expectations/cases/demo-001-acceptance-script.json": (
        "1dd0ebe06eb1149129434330f8b60ff90558430d8ed1ddf4fa9dcbd3c1992cb8"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-001-state-task.json": (
        "9f17745a75d8fbcaea2789274c174c507d273302ff2c7fdb2d72c86370388112"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-002-state-task-fr.json": (
        "305d6777833a9b1a5058280ee4dc17440f66c878c9290db0a1979edece30a6b7"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-003-state-aid.json": (
        "758f70e62bb310aa0e83fa93a9b40d982453e9f5464d69574331a47e6b849c77"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-004-state-aid-no-space.json": (
        "d2e1ad12ca293825fcfde55bb1f0c5fb0d53898c48ecb0330dfc556e774842f6"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-005-state-note-leading-space.json": (
        "7c6f223107a64cb6f555d4412a7c4e595bf7ec05477bf0ec55447c0fa8f8fa3f"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-006-state-process.json": (
        "3123fbe37e1de316a8895aca70cfadfff63884b9be598579dd9ef164ad02a2f9"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-007-state-call.json": (
        "6259bba7b9459f9235e27371ce926731a6bd3ddbb0648a5de95dc68d77cfc4eb"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-008-state-user-task.json": (
        "d4ffe6ea5c060d5bb93df24c0cc277e08fd847719d63c82056122ae2f8ed714c"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-009-edit-task-name.json": (
        "acb521d710d4a06ed57a84d61c44a81ff65cca9143fd0b0b79d998544a007d24"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-010-edit-situations-crlf.json": (
        "b82af8ad6aacb89d4e03011294ed7d3e187da308fafc4e471af9f47a83a0e87d"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-011-edit-empty-name.json": (
        "133b801223ce84e4972831d83846dcef4e100a44145841e0eefc7de5c594c112"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-012-edit-aid-body.json": (
        "6171dc8aa245170629080dcc0bdc1ea244b97871d2187a884fd0b03a43e02c1f"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-013-edit-aid-body-typed-marker.json": (
        "0879e2d115cf1583a64fac1b8779a090a64c8a87186caa126519ac22eecc3847"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-014-edit-aid-no-space-keeps-evidence.json": (
        "2ca27256a8f8263fba2f3c6ed576ec207f1b2cd79e7c1784e844870e73f1ed53"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-015-edit-call-target-keeps-evidence.json": (
        "15fca3a746d89d33a9db408958bfa7fba239a7f9e5787606566205df7a7eb497"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-016-edit-process-kind.json": (
        "2c16cbedf58c6812494fa70ea9063b7a7e52181ef45de239eb73f21b277bca8b"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-017-edit-reference-override.json": (
        "d83b1a7d07cd056f3eedb0c2ea336966fe52f8d7a5cc7f3b6be9cd75475ea343"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-018-edit-store-title.json": (
        "5487f58de0362873327dc00be1a2bc1e7ce81293606b118ea2b937d22f16c2a9"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-019-edit-no-op.json": (
        "fdc449859941f68869e4d24804cae860d2bf9d899c809dbeb29a29598be96698"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-020-edit-call-target-wrong-type.json": (
        "abd56455d9b3846cfaeea45aa6686ace00ce9458cd189f6fee7afde39d70e6ba"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-021-edit-call-target-dangling.json": (
        "853db461d15d01ce387dd6ac6947fa2f434d3a76a0829b4d1cb82348f23bb1c1"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-022-edit-enum-not-a-choice.json": (
        "774327c51d14aa70f57e9180be12106e860d9c8670fb6ee884cec374e8c3a209"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-023-edit-readonly.json": (
        "380b8b2710ba24f900514a7494444c318c9d5d05378087fc0bbf40a5904c610d"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-024-edit-number-no-coercion.json": (
        "764c09607c401485fffe3747fb16ab62f7486d0583fad54bd4e196d5b12898b3"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-027-candidates-all.json": (
        "6d2daab6fd9ca11afb8229929894763a9206ac086057f5075c614f59029f8480"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-028-candidates-case.json": (
        "3483392ebf2a352643e8b4e1a50b071d720b7949cc643d43293f0e1fe645d2b2"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-029-candidates-case-miss.json": (
        "c5041d027d2c9528c024e160f87199f1120472352cb0a65d14b1ec6e1e1eae4d"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-030-candidates-normalization.json": (
        "ee876ef9f21ad502d7323b9cb39c9158399110c55ce0600e740b71a91c8b92b4"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-031-candidates-paging.json": (
        "3be21d70761d29d19736a841d7c4f5d21df2daee35e6049c76e206b8fadc613e"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-032-candidates-astral.json": (
        "acff0b27b2b71a794e76e68f0acc45b387447dd48d5d4f4f841ba93c256f8a73"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-033-candidates-unknown-field.json": (
        "5678981a30c8c4304d44db96284989b85f410c34519f43c59e3cb27da2ee1b56"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-034-state-call-locked.json": (
        "8c86d526df296ddf23b877b08f88caa89345635cdf6fcf86186a818d8cad8d12"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-035-state-call-hidden.json": (
        "53c64564b4ebf5c2ca34e244144ce21fd15e707ba5b31b5e92cbe43368bbb1d9"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-036-state-choice-upper.json": (
        "821a6fd2e41cc2a0077764f0ccbb5ec8bbf9fd542b18f210807c6ad97df544a8"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-037-state-aid-link-anchor.json": (
        "19b5de70861e0b0b16e7cf6610b21814dcc051011447a15d9e19b2196be959b4"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-038-state-no-fields.json": (
        "b2d0a48dcfbd25264083070221d8c83c542d42ea878b228438d778d6bd7b77ff"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-039-check-enum.json": (
        "5893b34b459dc395d613535398f19fd3eefcaa9b8d531a5e79e6f1af64537ccf"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-040-check-reference.json": (
        "24a763fefcf96eb866d6bb4b0f6fd52665a7b19187c5c6cf797ea87e6af009a4"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-041-check-text.json": (
        "8f91804ba3664f86c4ebe4dce9ebb2049d74cbb9e0d2a73abfd44769597bfe13"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-042-check-denied.json": (
        "5be1f15b88b9eeb15dec2a7f41d6582b9ab73d982c5084b4d02e3773ee3241a3"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-043-check-unknown-field.json": (
        "14956e1bc482674f73d2a9f1cd9dfb020e7e7266747e69aa2f03bf8216e78ca6"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-044-check-unknown-target.json": (
        "4e6cc4052b4c7f35058fb0d557019055721fb8c0d91fcd76c973e89afd366207"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-045-check-stale-revision.json": (
        "5a011a6826d1ede10071a233f46aad1991385cacbf424561325dc07a2776a386"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-046-edit-locked-target.json": (
        "4442de7a178bdff1e6d75a72394817f5af891b1878a54db0e45d1213a0f2fe02"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-047-edit-hidden-target.json": (
        "4ca554dfd14c73cb62c519b91eb8ca79b5cbbe534af1a54f7dd672ad7e8e4092"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-048-edit-unknown-field.json": (
        "96dc066431a2f05dfa9f14d6b0ffcfceb9cca74840a364777a4149fbd5efb740"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-049-edit-unknown-target.json": (
        "320cd4aa79a50f5a59c587677337262daa86e1a89d0b11c17d53db7eab328b59"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-050-edit-value-omitted.json": (
        "c39dbf8580836f4ae5146c29a0c880cdf527918143218245a131053e64e99ed1"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-051-edit-boolean-no-coercion.json": (
        "d92024eb3ae796b4706f80d56a00bf4218199224a2077dbc80b8dcd0a3b55890"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-052-edit-aid-link-anchor.json": (
        "bf0ac6809d4557f4bc4e648a3dc7c8e5008881708f41f7aa1055b9c7bdbebcd2"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-053-edit-aid-link-other-process.json": (
        "fc26e864f394c092e87aa81590b53bd849f1ae59b94b2da570e2471f629ef09d"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-054-candidates-anchor-ownership.json": (
        "0ef238684c9fd03b234993eaebe5822806d7b6752a6b97fac888b79a779b42e3"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-055-candidates-locked-field.json": (
        "28cc76e8616324970634c2e29bd0c9ba985c3cb8110ce5890cdf8271c11696ee"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-056-candidates-hidden-field.json": (
        "2ab59bb550989942d701d4f61bf4a0246b345e8ec4252b1897f198572d552497"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-057-candidates-not-reference.json": (
        "c4a607290df0cc9612faefd02d539a39761c19cccdee4b89202c38e7e7233086"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-058-candidates-negative-offset.json": (
        "f6c9f5cac447205a657c0428c2d1d2f5d9fd05e0a7bf3435c3b7a9e0181ac805"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-059-candidates-fractional-limit.json": (
        "1cecc4ea21e16aee0b3abb0d8d2f94f6316dd176812a33de277a4e303256d8f3"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-060-candidates-boolean-limit.json": (
        "168b117d1ab3ea528a63807d7d5044757a1219b34119aeb450b0995d5e1bf046"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-061-candidates-unknown-target.json": (
        "4b7d15683086c750eac04c58f39c49a2f89908ae89739daac8970cf0d9a184b1"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-062-candidates-stale-revision.json": (
        "9d52c86aee6f437e8d76cbcb06e50c1168927be1357892b3865dbb167654a650"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-063-commit-time-invalidation.json": (
        "84e8c69095b9fef9e4f0d69473d843c0aee17636f0fa7b1f5d24bce16b5d8a61"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-001-refusal-leaves-no-entry.json": (
        "6becf3ccadbfb6ad45cf4242b8910271614d5facaf1b22e946ffe266206e5184"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-002-noop-leaves-no-entry.json": (
        "0fcc2d8be33859ec1461cc905d145a785b9af08c763df599bcc468224483a7cb"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-003-entry-point-chain.json": (
        "7e8e142cbbaaf8644af3dcd58863d40360a1e287bb264209c9e2bb9f0a26ce4f"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-004-insertion-key-reuse.json": (
        "f93a9e6206ed8589534e8e93c42e071ab11c683998c289119b5397247c00f9b2"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-005-paste-key-reuse.json": (
        "aa1d367ba2194f3a8979f58a6934d978b525ea80c791f4c0c9de2fb51f908c29"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-012-empty-batch-noop.json": (
        "260953d18de76782682602e30edc08f0f4ddf44647f5493fe93cc2f0a4f3fabf"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-001-task-programmatic.json": (
        "6738690c90d3826b99c86a8a5f162eccff57f21329780a3bf3d249fa76a36a79"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-003-user-task.json": (
        "b9566091e5ff7dda6d824f9b8220a34b592e051101a88ae307cd93d24eb36adb"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-004-start.json": (
        "11b27f1f35a9199e9042f1f7504a9d2e57c201257ebd38036f187073d7988fab"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-005-end.json": (
        "c8a3982dd61ffa28d04db9731cbbf0699b04a416cb6a8e101486609ff2212ec8"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-006-gateway.json": (
        "39ad45eb3d3bb0c9c66f97b5a3a5ed967678e936642c983c7e2461fc6c43a27b"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-007-call.json": (
        "eeaafc4354029d9aff9f1eca1f767bd5c8c8d779287561f0964369d9370e2da7"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-008-reference.json": (
        "1ec16ccbb7f69f0a3033e1c9a71bd11ef4133f266bca6774ff82c5bbd6c538ff"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-009-item.json": (
        "446259b4ab482d1bf8530bef983b8396211d52136b9a4861bf200d218ee34bf6"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-010-aid.json": (
        "aae650344442d14fe5c7440d1abedca378e86980515ce3ac18e7461c2d021245"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-013-input-set-b-programmatic.json": (
        "91915a7f39b4b524b8d50707cd65229cee45b2c14dd1eb11413cd842b5b5a2b2"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-015-input-missing-target.json": (
        "e02ac9543b125c7c3141e615587fa77d753b96ac1c7d013905e78cc6624524e3"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-016-disabled-owner.json": (
        "c1bf9dc2b012fb07a3274ee228f666d8e948235a13fe44a483966ec0747f368c"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-017-unknown-entry.json": (
        "6f00c33d8fdd867052bee34b9de4cf788b2eb7b4f9021f787e676ca5b93ab022"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-018-final-only-report.json": (
        "01215759d5aea4713dc858dfe2d5a1ab50cec366fd5a7ff7c8a7d6b6e91d68f7"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-019-contrast-theme-same-tree.json": (
        "d167c08295941d533b0674d92e64d17b052ea1f889900d57f0998bfea9a200a9"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-020-upstream-command-mapped.json": (
        "5879430315459cbf7764d6dfe360c950a21fcd5662611dcb34df54d75aa87865"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-021-unlisted-upstream.json": (
        "9fa971e89c4ab84d408b253ee8fe015fe0b195512e8cf92e62efd6821ecef7ad"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-022-bare-recipe-command.json": (
        "01afcd7521b1e9fc4eaa3abad393d9570fcdfbce66b0d75cc7bdf21ba8989d6e"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-023-unknown-member.json": (
        "d371b8216f549a0190a6599bfe5ae48a09c303307cc2a5ff98d5f16a1a8eccca"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-024-extra-source.json": (
        "6a784f59f9dd947a60ca42b19c1805b73d8de21f5832fb56988897363e9307bc"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-025-non-string-handle.json": (
        "0fbe0cff7ea9afa1989244203a6173d989d4ec74f1704f6b60e2a216508303d3"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-026-dangling-handle.json": (
        "cbb68bf0fa435257d0b53f3760fe0337e586903faa70eb5b5ca8ea258ce07c51"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-027-null-value.json": (
        "77f6b8e933ec8bb9c63b4dff7bfa25f1f507b3e700d1f16625b49fee65a57def"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-028-number-value.json": (
        "62870ed768e85bd930b32b7910f4e4e3d34cae08aae4e1b0878fea9643c924a8"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-029-input-loose-two-sets.json": (
        "b4d4ad083b52c46e09c74b7c185584fc55242e26f9f41689ac18914f42df390e"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-030-cancelled-before-call.json": (
        "bdcfab2c49d2e17410744f5aeaa9a13466ee976db411b99cfd749be723392e7e"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-001-copy-task.json": (
        "e9d46e7a0e172a32d61d97d59911432d7d8aa37e51ead21b99d5ca55dc5b9815"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-002-copy-group.json": (
        "fc4cf78fd9db32628be8eed4d6c43c5f177503e2a87dbb3a63b124947172ecdd"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-003-paste-task.json": (
        "5454e14c6c6728f5b77062f0027d1a06c5130426ceba5423df8152353e46d04f"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-005-paste-group.json": (
        "3bc16e6081b883e3062b7be0955c4ef197366c40b681f85bdda441ced413e951"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-006-paste-reference-shared-store.json": (
        "19dfd637ea1a049139968c91bc69a4c603d2425290ad33df64b7a65104b296d1"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-007-paste-cross-document-dangling.json": (
        "6b0d0a34719b3fb244ee16317445e4d364a82076432d367923fa0f0eadab617b"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-008-paste-batch-one-pass.json": (
        "5781c51fe5ea63a0244885cf421ed9e0eb17bb5888db027b31365bc73f93ede1"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-009-paste-into-task.json": (
        "63691e5e54f8c035fc5651e54c33318948e2378a7dde7d92ebc12127f510f3a2"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-011-copy-stale-revision.json": (
        "d415bf4d03ec949c03730355fafee64dc6a554f86cf28bea1ee5d4334281a62b"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-012-copy-unknown-id.json": (
        "1fcf9bee5b1810a079618ebf7649340d0b80f1a8363cd386c8cec4e04ee2cd48"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-013-copy-definitions-root.json": (
        "520070c364f817ea6bce5c705aa0bd5ba1f4d4441bf64c5fe1b83d956519b077"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-014-paste-then-edit-same-batch.json": (
        "53bf07764d0d7b36f2403242c174658cd797d9e9a835034d33a436c3e7b468eb"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-015-paste-call-keeps-evidence.json": (
        "6ace02b5cc413f4321d6bdd142923cac21659578a4387ae16c41602c98d6c3e3"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-001-task-to-user-programmatic.json": (
        "91fabf745f369bb5d70f24905d39c7e55ea048829e065a2a9499559871a511fd"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-003-user-to-task.json": (
        "57fd2a7bce8a17bd5066087b29b4f6ff482c93f20bf3248bc470286074370fbb"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-004-exact-type-refusal.json": (
        "f376709c9f22fb33391befd91e54824ec1a45614e4a51c44e855beab09a67bdf"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-005-reference-to-item.json": (
        "2e81c4660d0e7b58bcad4fcaaf806be7ac1d2f5e7d06205be4fab7d76c2c783d"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-006-reference-to-item-linked.json": (
        "59069af8052437fc8ae80f44a131fef46583c704f68b6b37e0b37f896fdfe90f"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-007-referenced-task-refused.json": (
        "3d9f0a97cb2fc1ee32c881c9bd7fd6e890f7740053b6678d3ff585d508650d20"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-008-note-to-aid-same-type.json": (
        "3bca7a7f1075346a5c48e0ac4e01a2aed43c2030abdd0dbf9fe7bb6782456f12"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-001-palette-plain-en.json": (
        "96228d4c9c4ef7cf5962d54e718a7183f51103d805a7d8f45157f19f8f5c10dd"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-002-palette-contrast-en.json": (
        "6b3d6ca1499d1d8ac53186d9bfd355cb2ae6a523e67253db71bbacf6b243813e"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-003-palette-locale-fr.json": (
        "a09e152c9b8e0bbf3faa99297e7d30f31bb9e1a7d6517930327c7c6163ed857f"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-004-palette-locale-fr-ca.json": (
        "f3725cf004c0f5e9dbabbf4f7fe3e26623bc3df9e1f4b9623458117f330df653"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-005-element-task.json": (
        "193937f03507e08465508e55d46ee4376b85a54b6188fb19bd6c605afa2765c5"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-006-element-user-task.json": (
        "0878d4bc4577513237975d8ddedab83ab798599d2281addf5283960566211e7a"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-007-element-end.json": (
        "d75ea5043ffe66b6a6b4bbb786b27d14ab50e03cc25b4b5bfb1312e7563c8011"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-008-element-reference.json": (
        "3ee1774dcf9c4d4d7afd900c76faca72d4db95c9954090eebdccd56d9be41f0a"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-009-element-annotation.json": (
        "b30d6bfecb3d7ed9348575997167ce7e1d67da6b1822a770eb6831462fe17a55"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-010-element-call.json": (
        "28aa3f222515ee90011756dfcae71fad538c38af62ad435a089061cc14ba6f08"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-013-compile-duplicate-upstream.json": (
        "08c547b9695f40cb3333a9abe4777aefe5ae7e0320e1a38b8c7c5dfd22413a7a"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-014-compile-missing-fallback-text.json": (
        "4289a5b90b172d088d028e771df6796ebc882c8c80f526ec91d8bcad6b3093ea"
    ),
    "vendor/js/lot5-ui/expectations/cases/twin-001-assignable-rule-user-task.json": (
        "aca34a665c61aacbb56a531cd8b98ba3ebdb8cb5ce80140c7fffd1cd2c8f8965"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/basic-contrast.snapshot.json": (
        "91026102f157d488a16814867e020dc9b9b4b18418a38476a2d1c1db73f1fb7d"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/basic-review-page.snapshot.json": (
        "7de0cde9d18f1144e982b5d43225604dded01d3192e4e5237af3d5a799cdab07"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/basic.snapshot.json": (
        "4e4ed9a303081351a3bd3fda885c5f3754505f1cc16aa69fa9b16e98b8040f37"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/demo.snapshot.json": (
        "eb262211e4b71e472ec273c99902d532db26fe12cc68b39e47802611c02be80e"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/foreign.snapshot.json": (
        "e38bbe03c04daff214ab79f623cc08f3191d5115d8b545df1dba31d3fdfd64e9"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/ui-neutral-base.json": (
        "eabe8ae63be94d2ecfd8873651d9aa24089b438726b048be72f9f4e00be9adbb"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/ui-neutral-descriptors.json": (
        "59f956064d24508d071e0a2f4cddb91a6f764bbb82b751234def3e63ffde4032"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/ui-neutral-metrics.json": (
        "e7fe51553eb92430f1230637456d4aaddaf98bf17e42da99fe237520cfb0f98d"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/ui-neutral-profile.json": (
        "fa85d93dd8c7eb1a042e861a0c3b42c3cf1bc98913a5339569cb2590834db108"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/ui-neutral-registry.json": (
        "1dc918ec35fd0c60a78006a9c4bacfe3fc32b32c6b2e796810e7256f27139406"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/variants/duplicate-upstream.profile.json": (
        "b229d51d19cc706564b7daecfe544ba46823c18a3e1313d5b128a4fb228d8546"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/variants/missing-fallback-text.profile.json": (
        "70dbe64ea8ce311b1f5463f413649d7863e8963823814bf2830afbda5748dcb3"
    ),
    "vendor/js/profile-parity-corpus/profile-mechanism/1/neutral-metrics.json": (
        "151d1a1fac1cbcab8ca53f155c3210437f4a2c285f6b68721973d1da6c362ee0"
    ),
}


def vendored_bytes(path: str) -> bytes:
    """Return the raw bytes of one vendored file after checking its pinned digest."""
    data = read_artifact(path)
    if raw_digest(data) != VENDORED[path]:
        msg = f"{path} differs from the pin of its owning JS seal"
        raise DerivationError(msg)
    return data


def check_vendored() -> list[str]:
    """Check that ``vendor/`` holds exactly the pinned files, byte for byte."""
    problems: list[str] = []
    found = {
        path.relative_to(HERE).as_posix() for path in (HERE / "vendor").rglob("*") if path.is_file()
    }
    if found != set(VENDORED):
        problems.append("vendor/ does not hold exactly the VENDORED files")
    problems.extend(
        f"{path} differs from the pin of its owning JS seal"
        for path in sorted(found & set(VENDORED))
        if raw_digest(read_artifact(path)) != VENDORED[path]
    )
    return problems


# ------------------------------------------------------------ vendored JS cases
VENDOR_JS = "vendor/js/"
JS_FIXTURES = "tests/fixtures/"
#: The owning JS corpora: vendored prefix of their case files, ``pathBase`` of the
#: paths inside their records (relative to this directory), SHA-256 of their
#: ``seal.json`` (named by every derivation).
VENDORED_CORPORA = (
    {
        "cases": "vendor/js/lot5-ui/expectations/cases/",
        "pathBase": "vendor/js/lot5-ui/expectations/",
        "seal": "0353affc89e60853fa6dac9e99bb1aea40fed7fc9670311dee15964ccb755813",
    },
    {
        "cases": "vendor/js/lot3-cn/expectations/cases/",
        "pathBase": "vendor/js/",
        "seal": "6b807ee2c219f614d0f434cb8568c8d15acc0cc425a11bfdaa5cf027d86e8b06",
    },
)
#: JS operations renamed in the harness record (multi-step scripts are sequences).
VENDORED_OPERATIONS = {"canvas.sequence": "sequence", "transaction-script": "sequence"}
IMPORTED_DI_KEYS = frozenset({"descriptorDigest", "diagrams", "sha256"})


def is_vendored(entry: dict[str, object]) -> bool:
    """Tell whether a harness record is a vendored JS case (``profile.vendored``)."""
    profile = entry.get("profile")
    return isinstance(profile, dict) and "vendored" in profile


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _vendored_corpus(case_path: str) -> dict[str, str]:
    for corpus in VENDORED_CORPORA:
        if case_path.startswith(corpus["cases"]):
            return corpus
    msg = f"{case_path} is not a vendored case file"
    raise DerivationError(msg)


def _artifact_json(source: dict[str, object], role: str) -> object:
    for artifact in _as_list(source["expectedArtifacts"]):
        record = _as_dict(artifact)
        if record["role"] == role:
            return record["json"]
    return None


def _vendored_expected(source: dict[str, object]) -> object:
    twin = _artifact_json(source, "twin")
    if twin is not None:
        return twin
    trace = _artifact_json(source, "trace")
    if trace is not None:
        return {"trace": trace, "unsealed": _artifact_json(source, "unsealed")}
    return _artifact_json(source, "result")


def _vendored_command(source: dict[str, object], expected: object) -> object:
    """Return the command artifact; a sequence keeps only the steps the twin replays.

    A gesture step becomes the headless ``applyCommands`` request carrying the
    command record the JS seal seals as staged by that step and the step's sealed
    ``baseRevision``; ``"@current"`` stays the JS placeholder of the current
    ``viewRevision``.
    """
    command = source.get("commandArtifact")
    if not isinstance(command, dict) or not isinstance(expected, dict) or "steps" not in expected:
        return command
    script = _as_dict(command["json"])
    twin = {int(_as_dict(step)["step"]): _as_dict(step) for step in _as_list(expected["steps"])}
    observed = _as_list(_artifact_json(source, "sequence") or [])
    steps: list[object] = []
    for entry in _as_list(script["steps"]):
        step = _as_dict(entry)
        number = int(str(step["step"]))
        if number not in twin:
            continue
        if step.get("action") == "gesture":
            staged = _as_dict(_as_dict(observed[number - 1])["staged"])
            request = {
                "baseRevision": _as_dict(twin[number]["result"])["baseRevision"],
                "commands": staged["commands"],
                "expectedViewRevision": "@current",
                "transactionId": staged["transactionId"],
            }
            step = {"action": "applyCommands", "request": request, "step": number}
        steps.append(step)
    return {"json": {**script, "steps": steps}, "role": command["role"]}


def vendored_record(case_path: str) -> dict[str, object]:
    """Derive the value members of the harness record of one vendored JS case."""
    corpus = _vendored_corpus(case_path)
    source = _as_dict(json.loads(vendored_bytes(case_path)))
    base = corpus["pathBase"]
    expected = _vendored_expected(source)
    case_input: dict[str, object] = {
        "source": {"vendored": case_path, "sha256": VENDORED[case_path]},
        "pathBase": base,
        "inputArtifacts": source["inputArtifacts"],
    }
    command = _vendored_command(source, expected)
    if command is not None:
        case_input["commandArtifact"] = command
    operation = str(source["operation"])
    profile = _as_dict(source["profileArtifact"])
    return {
        "case": source["caseId"],
        "author": "spec-seal",
        "operation": VENDORED_OPERATIONS.get(operation, operation),
        "profile": {"vendored": base + str(profile["path"]), "sha256": profile["sha256"]},
        "input": case_input,
        "expected": expected,
    }


def iter_imported_di(node: object) -> Iterator[dict[str, object]]:
    """Yield every archived importedDi record below ``node`` (explicit stack)."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if set(current) == IMPORTED_DI_KEYS:
                yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _vendored_paths(node: object, base: str) -> list[str]:
    """Problems of the pinned and plain fixture paths inside vendored input artifacts."""
    problems: list[str] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            path, pin = current.get("path"), current.get("sha256")
            if isinstance(path, str) and isinstance(pin, str) and VENDORED.get(base + path) != pin:
                problems.append(f"{path} is not vendored with its pinned digest")
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str) and current.startswith("fixtures/"):
            if base + current not in VENDORED:
                problems.append(f"{current} is not vendored")
    return problems


def _check_vendored_values(record: dict[str, object], profile_path: str) -> list[str]:
    """Recompute the arithmetic of the vendored values (revisions, bookkeeping, DI)."""
    problems: list[str] = []
    case_input = _as_dict(record["input"])
    base = str(case_input["pathBase"])
    documents = [record["expected"], case_input["inputArtifacts"]]
    for artifact in _as_list(case_input["inputArtifacts"]):
        path = _as_dict(artifact).get("path")
        if isinstance(path, str) and base + path in VENDORED:
            documents.append(load_json(HERE / (base + path)))
    pins = _as_dict(load_json(HERE / profile_path))["descriptors"]
    for document in documents:
        for envelope in iter_envelopes(document):
            problems.extend(_check_envelope(envelope, None))
        for imported in iter_imported_di(document):
            problems.extend(check_imported_di(imported, pins))
    for result in iter_results(record["expected"]):
        if isinstance(result.get("report"), dict):
            problems.extend(check_result(result))
    return problems


def check_vendored_record(entry: dict[str, object]) -> list[str]:
    """Return the problems of one vendored harness record.

    Every value member must equal its derivation from the vendored JS case, the
    derivation text must name the owning seal and case file digests, every
    referenced file must be vendored with its pin, and the arithmetic of the
    vendored values (envelope revisions, closed Result/1 and Report/2
    bookkeeping, archived importedDi digests) must recompute.
    """
    source = _as_dict(_as_dict(entry["input"])["source"])
    case_path = str(source["vendored"])
    if case_path not in VENDORED:
        return [f"{case_path} is not a VENDORED file"]
    want = vendored_record(case_path)
    problems = [
        f"{key} differs from its derivation from the vendored JS case"
        for key, value in want.items()
        if _canonical(entry.get(key)) != _canonical(value)
    ]
    if problems:
        return problems
    derivation = str(entry["derivation"])
    seal = _vendored_corpus(case_path)["seal"]
    if seal not in derivation or VENDORED[case_path] not in derivation:
        problems.append("derivation does not name the owning seal and case file digests")
    profile = _as_dict(want["profile"])
    profile_path = str(profile["vendored"])
    if VENDORED.get(profile_path) != profile["sha256"]:
        return [*problems, f"{profile_path} is not vendored with the profileArtifact digest"]
    case_input = _as_dict(want["input"])
    problems.extend(_vendored_paths(case_input["inputArtifacts"], str(case_input["pathBase"])))
    problems.extend(_check_vendored_values(want, profile_path))
    return problems


def vendored_parity_list() -> list[dict[str, object]]:
    """Return the parity-manifest ``vendored`` list, one entry per vendored harness case."""
    entries: list[dict[str, object]] = []
    for path in sorted(HERE.glob("*.json")):
        entry = _as_dict(load_json(path))
        if not is_vendored(entry):
            continue
        case_path = str(_as_dict(_as_dict(entry["input"])["source"])["vendored"])
        entries.append(
            {
                "caseId": entry["case"],
                "source": JS_FIXTURES + case_path.removeprefix(VENDOR_JS),
                "sha256": VENDORED[case_path],
            }
        )
    return sorted(entries, key=lambda item: _u16(item["caseId"]))


def check_file(path: Path) -> list[str]:
    """Return the derivation problems of one expectation file."""
    entry = _as_dict(load_json(path))
    name = path.name
    if name in ("fixture-descriptors.json", "fixture-base.json"):
        return _check_document_fixture(entry)
    if name.startswith("fixture-profile-"):
        return _check_profile_fixture(entry)
    if is_vendored(entry):
        return check_vendored_record(entry)
    return check_case(entry)


def check_all() -> list[str]:
    """Recompute every derived value of every expectation file and the parity tree."""
    problems: list[str] = []
    for path in sorted(HERE.glob("*.json")):
        problems.extend(f"{path.name}: {problem}" for problem in check_file(path))
    problems.extend(check_parity())
    problems.extend(check_vendored())
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
