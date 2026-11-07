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
        "810f461261879b3381e99fa04d428d96399bbda6543caaeea3aede0d55536035"
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
        "5fd81a3a0e04057b524e7f892a49b507f1ec4c4ea92f73085e55b9defad6102f"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-003-reference-link-programmatic.json": (
        "6880746b874365019a434e3739f9f95cb16ba4ab33f38d5c8850ec1b1389d4ae"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-005-item-input.json": (
        "9fd03593f6d3721dce60ec97c2b165737ca08fb31b31e454e9ae5b08008d8016"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-006-item-output.json": (
        "c1d89ff679251113e0701783a1427d08775f3e4be4f387fc1854a9f476598812"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-007-annotation-link.json": (
        "37ff61a340c90bea969e81339eae69dc451364252c35b74eb91b49f73605463d"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-008-reference-to-call.json": (
        "9015c48bd418f7f23bc83b4b6284143c5e75b135652d731fa0494253ab9518bd"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-009-ineligible-target-noop.json": (
        "7d4f8228708896dc009d64f07c7c8b7b553c903d01f1a3544618b0ebde62676c"
    ),
    "vendor/js/lot5-ui/expectations/cases/connect-011-flow-from-end.json": (
        "0472f6346c9b28e64ac86183ac1b59ba8e41044b7b2c3ace4bd494ea5c45cea9"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-001-append-task-programmatic.json": (
        "8291849834ad7b124d3a4edb3b485ad323068a7a38362d07f35726298266a796"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-003-append-end.json": (
        "dd7e805b5af3ccf0d6adbd13140699844acc81d2a50741c6b445c4f885822b8b"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-004-aid-attach.json": (
        "d437a331c04001b388c8a783acc6f24e130ab2317e101fd239bf2fe385b63b60"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-005-append-on-end.json": (
        "ca2bb9e69d467c3f5e03ae9b0aabc2ac1254c37a418fd25d2a56706c4f88933b"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-006-call-unlink.json": (
        "90265242b4c394d6db6eb3525f8c7c7e45594f86c5aaaf65908ca9148d6b58a4"
    ),
    "vendor/js/lot5-ui/expectations/cases/context-007-call-unlink-noop.json": (
        "f97c74ee78fd40c51c7e2e3d339c7d8c78ccbb1dac4f1a6fa52033e9404a5d8c"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-001-reference-with-links.json": (
        "82c66b7fd896fb3e96a65a8f59b1c44eb3bc76b4b20127e1071095639cf16335"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-002-unconnected-task.json": (
        "8cab34dad4c1df39fcdfa6bf7e9fe0cc785ab5895d8bd7d1f0fa09399d09c92d"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-003-outgoing-only.json": (
        "f43472802a24268a0dfbc06ae124cc395068b4bde85efd66e3ef04cb46985bf7"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-004-incoming-refused.json": (
        "c78a6f22945b9745c46dd1a66ee7924bc2ee2f5c476c8ef11a2b50f5a516d78b"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-005-flow.json": (
        "673ca1f81bb48552e1d5fa6e8361abb5a49449a981dd5bc3e80a0cb8e2775761"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-008-multi-atomic.json": (
        "68c61eef7284939c8c6a0ebc2ae892ea14b19f2c217b2194a277d8836cbf0d3a"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-009-annotation-with-link.json": (
        "5d509d17b3504b7bb713965960624ae61b786306e831fb70031c7ba53fde8128"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-010-process-disabled.json": (
        "3b64c5c707a1d61d7a9885a60d3ada51051b568fe9e5bcd9c0252254f2b79ac9"
    ),
    "vendor/js/lot5-ui/expectations/cases/delete-011-last-element-keeps-empty-array.json": (
        "56332d8375eab36804ceed126baffdb69c7ad4e13254d61382822dcb881cc02b"
    ),
    "vendor/js/lot5-ui/expectations/cases/demo-001-acceptance-script.json": (
        "3714bbc5eca060ca354904e2e43ed56c68da73cec333518f984d2061c78e4d1b"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-001-state-task.json": (
        "d1d219cd54ad30bf5ba653e2eee95e18e07db94d143ef6bb6ced16e82109e340"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-002-state-task-fr.json": (
        "530d40bacc93d65726b43115c4402589dbe549a3acca21028895d4df49d90bdc"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-003-state-aid.json": (
        "9d056d47884eca0d0bbbd057751a2b9e7a96d207ab12a98062576db56fa4b574"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-004-state-aid-no-space.json": (
        "2367b74d2da79741f202ef96281b29d696acb70406b6672e19396fa2ea560d4c"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-005-state-note-leading-space.json": (
        "6845fea0e6999141506f758c13e7fbdfca0bc9a8b0567a139c7bc46f440228ef"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-006-state-process.json": (
        "8b48ae85611899ed5b8830b033ddbc64417684143867a231b620047c126d7922"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-007-state-call.json": (
        "c20f854cdd1c7f7fb8add1b4d47ae06ca981f8450818d8295639f0d8133f59b3"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-008-state-user-task.json": (
        "913c77e3e5eaaa63d9d4e8c05d1778d2533b88cbeb73a2b8528ce4cfcbcae48e"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-009-edit-task-name.json": (
        "b8d8a25ed0faee1ca735d2093fa0b7a8de1401f6e002eeb6dd8281ec0af02d0a"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-010-edit-situations-crlf.json": (
        "12ea47663e0def5de2189b4bec9600295e28c7bf4ce68778f27cc8cbd3dbf6cc"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-011-edit-empty-name.json": (
        "fa7c1acce7cb9354ff9b63329b8016d019444cb19185a55e517550c34cebb8c9"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-012-edit-aid-body.json": (
        "8dd953ab94907f13d68457b03e4d787be7ed8d9d9d16a08e44ce1e930d0ad8ad"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-013-edit-aid-body-typed-marker.json": (
        "39f48621748d02bc1ce4709fc0a555e308e45c0310d5df7972dde591ee6b9814"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-014-edit-aid-no-space-keeps-evidence.json": (
        "719aca614d0871d303c24e80fb25df25075ec6eec5d005b8f82468c51138958c"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-015-edit-call-target-keeps-evidence.json": (
        "74c32a2b4d3f7d6a5e9bab4744f23b2b51580c1319fb6f6f84da2ddf78dbd26b"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-016-edit-process-kind.json": (
        "425d7d76dc2a9a5adc0fc3ad58626cd4794351171b32801f2ae30ee5d44760dc"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-017-edit-reference-override.json": (
        "31889065115833620580a11da404dc8bc4272ffed19baf02a8d8e3e67940a8db"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-018-edit-store-title.json": (
        "ab64809a4b3f0e4b2e9ce6914a26866417d5b679ff3bfe801bbe6c39b71b0e22"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-019-edit-no-op.json": (
        "930d76b6fadfeeb740aba94cf7f4db9f57da9ba6385d164f9b71a717e65cd191"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-020-edit-call-target-wrong-type.json": (
        "c246926df0d1d2ad615323e64c952f1789347c2a4c37c515b2836baf19ef2391"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-021-edit-call-target-dangling.json": (
        "8547d71923cc1d6a59385c706b85f90cf2122155fb8b755c623df187d4c6128f"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-022-edit-enum-not-a-choice.json": (
        "0ea6e6383ab175c1e0a2ba6a108f2b63e6fc8046d765a0f649ec5196e997b732"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-023-edit-readonly.json": (
        "6dde1cc0a96344d231a7d0b5dfc5d1c843d88e98c2f625af74fddcdea8b11900"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-024-edit-number-no-coercion.json": (
        "8c58b06cffda9756d92bd058f7b6b18f60758ac2f0929f695310a4065dc0f569"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-027-candidates-all.json": (
        "ee785f914f8508392eef6d76699622443282fb83aa6009c3bbc75a75b5f5ac4a"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-028-candidates-case.json": (
        "e8b31bbad873111f96fae9dd8bce17201b573cf36d8ce2c9f1a1d588d078e026"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-029-candidates-case-miss.json": (
        "5c85559b9c4c4d4e03bb8e7a16e1e972f08fbd8eec79158efd5296e2c48f563d"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-030-candidates-normalization.json": (
        "656e2b5c88fe5115474401c1646d7d4c2d754ca17f4235610694eec5d24106a6"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-031-candidates-paging.json": (
        "3eb01d8fa6d6e1f6755218430a279cf7947a70b93d603b80a53165f87b39065b"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-032-candidates-astral.json": (
        "0704c90b2254e9dd67db2474cc8e6e5db2e37482fc5bcb6069a26414d8e16673"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-033-candidates-unknown-field.json": (
        "869b95b8fad3ec34798dc0a7d933b5443d74f33bdb63ba37879dba7dfe8fe678"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-034-state-call-locked.json": (
        "3699a807ca99c2a82485ba36b06e788c093197927fa7ee5e8c382dd88ae381e2"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-035-state-call-hidden.json": (
        "6e2b0c4f7cf2a4ffe31222c3bf8aa4b4fed2199377e2f460a6f45e40a0106a30"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-036-state-choice-upper.json": (
        "2dfafe5c3a0d27b342374d4a4261ede60e6e199dc238325039b3357b7054b251"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-037-state-aid-link-anchor.json": (
        "654e9cfbbf03e6c695067d11739bd037ce9f9341d65a571133bc9df347a98eed"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-038-state-no-fields.json": (
        "a06121a66abb7a1c16e69ab3cf1f68152391cd882a569b5e6a9a40679d512417"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-039-check-enum.json": (
        "e023ed5f5eed5c1c8d8da047c420bd9571d493f73cb4a6e430070ca23b980acc"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-040-check-reference.json": (
        "298bf7af1923765b6a388eb4f2c71d3e2440698678fbbd935a2cd2c29d15748b"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-041-check-text.json": (
        "7f87fd396b008abd3aafca75045ba498dee25aa103d1422a507a31c3dc5744c5"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-042-check-denied.json": (
        "b2434443c5ecc372528481286b3d2996677febf11b863bc10a10773044455afb"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-043-check-unknown-field.json": (
        "4f3cce3125763f4bd9709a9943272f551c3036382184175ccadaf854da025877"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-044-check-unknown-target.json": (
        "90a0a53a9ce1781e9a7e31f0d5b3ee5abccff8220177a771cec589d94a7e55f3"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-045-check-stale-revision.json": (
        "da4f353bc15b8ebb6b3fbb5c13f786c3be7c94d169b568aa4abef67228c873d4"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-046-edit-locked-target.json": (
        "d1cb3b31f6c50a3afd88576669c3373b6fd5299fffd14febcb506a52d9372260"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-047-edit-hidden-target.json": (
        "b9f427ec0626d454b48fd492b87d6d0d6130843e8a0b27a266a186527c647e25"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-048-edit-unknown-field.json": (
        "79db41d84502a4f6f23dbd84c640801872cb4c6d9742339c444db76efb27a516"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-049-edit-unknown-target.json": (
        "6d28a650543666984d3fc85860277cbb80fccc19feb871ae58469b6c596cad80"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-050-edit-value-omitted.json": (
        "83a1c6d7a1c3ccf85afe2406ef07a5472a1f1381cb2b813d500b6b5f6322b4e0"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-051-edit-boolean-no-coercion.json": (
        "94b551a3bf8a278222eee1f7746705f60ae5b4e83d74ceb2d7c67631fa1fdcf8"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-052-edit-aid-link-anchor.json": (
        "8cc1f8b32d7654a6c24bdcd94de18a8cdf7b6c9f014db4289bb3ee9f4e3bd20b"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-053-edit-aid-link-other-process.json": (
        "1dda5fed6eec550d55751b1e8a3cd145d744bfa70c13c97ddb509218cea43a60"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-054-candidates-anchor-ownership.json": (
        "96801b8ee7915e5f419f8b855d97be5e6806b0c656478bc2ce304102215071b3"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-055-candidates-locked-field.json": (
        "943835d4252c537233b610ff7a9d72ddd36b1ae82757993011088c2dca67d849"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-056-candidates-hidden-field.json": (
        "7b27c465716cb3e19faf6fe0e8820bc14ed13a281a456c613b0309240388dcba"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-057-candidates-not-reference.json": (
        "54def51803646743d9fb66252994f7839b420e8b126fea81757904632710e8a5"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-058-candidates-negative-offset.json": (
        "737d230890456a6080bf3ea631e4676c61c6f17c16b2d6a23ddbf89bbe0c45ce"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-059-candidates-fractional-limit.json": (
        "fc9ed6e02b6a68dcf436af2561dbecf36e748cfcddc4f1d0466ba437cf37eb3e"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-060-candidates-boolean-limit.json": (
        "81d87bf541251b5eac473dacf30b924e15810422c680053fe52b6a1fafd2aaff"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-061-candidates-unknown-target.json": (
        "7f065d31098151ed312db25c80901e8159412bce0cfb388b8d835d540872c543"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-062-candidates-stale-revision.json": (
        "fb9b8e991c8932dff045bfc59bb8402dbe0cbff226b519394ff37ad0bffc39cd"
    ),
    "vendor/js/lot5-ui/expectations/cases/fields-063-commit-time-invalidation.json": (
        "d7c1decd5ea1d6156a92c81f9be4dfcebebbd3609886a61b50c623969c01dae3"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-001-refusal-leaves-no-entry.json": (
        "d5854b8ae0588812824989b0b71bec9403be2fbb90ffff0336f65f48e44bafdc"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-002-noop-leaves-no-entry.json": (
        "6b0e256f06b4d7bb30b97fb81458aa53b746bddcb5527ed2541de068d1bbe721"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-003-entry-point-chain.json": (
        "89e36d6e321a4d504adfd3ab0f1c5d9d7319e20a0936b2621526b26843601020"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-004-insertion-key-reuse.json": (
        "af94cd462e963aa9d0c745afec502fd89df7676cb5d4c915e54a60ba4f612e49"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-005-paste-key-reuse.json": (
        "27c9db2b73d32410756b51dd5e70910896acb37e89953af1e93aa9314b9731ed"
    ),
    "vendor/js/lot5-ui/expectations/cases/history-012-empty-batch-noop.json": (
        "862f2fde2d4fb439a1b49d7dfdd55a15eef4dd45cf6307e14b32202e6e242551"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-001-task-programmatic.json": (
        "818eb5f3dab87c3b9bf8f1d51f55f55ce5fc0fe7120415730951a8ef5edca19e"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-003-user-task.json": (
        "9416687b32edaf26c7a401068ea34b0fa593b082c98e9c18316298f1e58483bb"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-004-start.json": (
        "8886f636f3faea8a0fc197a24eab200dd33beb05c83e49577d7c2b4f0c907a09"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-005-end.json": (
        "73fc8fb2367f0dea4b22d59b8fe9951373f5057ce84799ebb25e68f8084ed293"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-006-gateway.json": (
        "3e987a59965e3aab17c67c117719569f3084bd811e8a88a29fa42cf1e62c51e9"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-007-call.json": (
        "636d6d8fc5b94c4c88c8cff236c6138cd64e8ea51d91be86797f83c6561937fd"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-008-reference.json": (
        "42d9487c248ad7d9bd965f345131d848fbb52d539a37f7921e0d13078d99dfdf"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-009-item.json": (
        "e44cb5a56968ef87695a5d422d6b76859c8aa6dc6ec4938e493c3a2f5c295836"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-010-aid.json": (
        "702baf427abf2b452e1e9164ffa55ece1bf03e978f9ec3b8595570cae94dc56c"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-013-input-set-b-programmatic.json": (
        "79e11e65b6b58d727660fc750cecfc8b679768908ca2f5c4ad8e0f5cfd1bc088"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-015-input-missing-target.json": (
        "c2ec239ba2b1199b2fd720490f9dc0e910b19291d0e043b6061529ad2de22689"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-016-disabled-owner.json": (
        "0b6b822815f95847236adb170a68bc5db014a03e4083543cf44b94f47cc42018"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-017-unknown-entry.json": (
        "a5e68554c6e7f6c88b12d74ed8a79592d46b2b5f39ddfb5336cbb8a7af91595a"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-018-final-only-report.json": (
        "87675ce5ec0c93c22b2e9491222f5438d11313217625be5a173ac81745b1e2cf"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-019-contrast-theme-same-tree.json": (
        "3c181794f8cb97cc7d2b551cf72f1eae3964e63b6a4e2e8f67762da409e65b2c"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-020-upstream-command-mapped.json": (
        "196e3fba362c2e044d0031ddd74be5b2bca2cc19e6661136256c52695c69a0ad"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-021-unlisted-upstream.json": (
        "edc4fe2767ec99dd9cb43b27ee3731f9e3bd507960d254c907d244d1b3bf6b62"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-022-bare-recipe-command.json": (
        "de4adcfa965198e32be39f628ee823129d2c0d400492ae12ae84e9699ef2301a"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-023-unknown-member.json": (
        "b1ed7bd67ad435917a96f0cd8c71a170bffc4bd79a354e74de5b2a956cad72cb"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-024-extra-source.json": (
        "6c419ac0acddb794905f85701ee6d7a3ae99c3b081f5a32ce0310de077b0be71"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-025-non-string-handle.json": (
        "964b51ca5e9a1858d336d4ea2794d8701dc5bf146518a033746028f1404752fe"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-026-dangling-handle.json": (
        "cb838d95ccb8cbc7a3d601c057786cc423ced67c5f9e0c0d0fda738ba9131667"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-027-null-value.json": (
        "fc503ecc603652e8cf91fcc08e0259352dfea009c5e246bf1f0b593a0edf7d95"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-028-number-value.json": (
        "9625dc866b39b73e6665d419608f5b07c9dab3220f88abddce87db5988f365dd"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-029-input-loose-two-sets.json": (
        "c17e993bcf0757e81324315a71e375bbc06da0deefc870201cdb5a505577a809"
    ),
    "vendor/js/lot5-ui/expectations/cases/palette-030-cancelled-before-call.json": (
        "d086858fd3d15f63b98ef8b72173f936e9f58f973eb47f3bdbb2470d7190448e"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-001-copy-task.json": (
        "1d2dd0ea8b2df664aa0851bf5ad94bdda52327d73b1a863ebabe311c133932b5"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-002-copy-group.json": (
        "3d98e102a4ac512027972e23cbac654735838383c624e60bcb1a23174beef102"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-003-paste-task.json": (
        "b5128f80d721783f49093669956a3fe82dfbedec898c95b172203112e427dcf8"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-005-paste-group.json": (
        "3b32b8e4180f893bdd932c9b3c5d3bd60dc36e0a565e40b898379a1695fb8e0a"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-006-paste-reference-shared-store.json": (
        "4b48657d9343a515abbf2c893abe1a539ac5566df609214f305b1e13f1b36519"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-007-paste-cross-document-dangling.json": (
        "322c78413ff8dacabced5ea4c174da19b6e59c394fe4c692128766712e3a0c35"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-008-paste-batch-one-pass.json": (
        "dbbb178a38d08edaeb54cc8a869a4bff334e10033f7260f5a9f2b7a75d09e29a"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-009-paste-into-task.json": (
        "eb9a2ebb0d8f60377a78e8cf2ba514ff6a40d91a963d253b5c5b150c21413c08"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-011-copy-stale-revision.json": (
        "719b017e4816548a5f809bfd61cfaee033002615ce8e6a4d09b838a74ace8617"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-012-copy-unknown-id.json": (
        "b7b59814d8cf809f967f89c5f1e10f60df02ed6e2350e1b0c817eb3ee0e0d384"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-013-copy-definitions-root.json": (
        "b8c4127c8f5dfbb26b3022a71487f0ed7a57acb3fc5c419f9a13010e23581e79"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-014-paste-then-edit-same-batch.json": (
        "ac729cd5c3260334d6b870617f82bde5591d9ed8ec49da6ed6fbc23c8d8858a1"
    ),
    "vendor/js/lot5-ui/expectations/cases/paste-015-paste-call-keeps-evidence.json": (
        "ccac7e23893f73952f2c09a90924d769bad8722c35b698b3cf0d3516ca37d31d"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-001-task-to-user-programmatic.json": (
        "ccc00c979b4d5b5733b0cf3c353216d04ee275f6b7d9bab83352d41103c536cb"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-003-user-to-task.json": (
        "87eebb4ba93b5419353ad0b21153ed37edab1c48b1f502b48bc4472266acc990"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-004-exact-type-refusal.json": (
        "3a3bcb066b22369e8a29d5d9dad461c5766970d87cbb09344bcfc397d493cc47"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-005-reference-to-item.json": (
        "12057439a5ac9590810177de83786d74dcc7f5016b841f355b3b55a3ffc5bef2"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-006-reference-to-item-linked.json": (
        "6e234d86e306d8d76d2c5305909a8bc81d56d79f3f4be4abc92716a504fc8232"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-007-referenced-task-refused.json": (
        "101d7aff99b31367ff5ca60ecad3b7f911fe774e9bf92de5e0a29a795835107c"
    ),
    "vendor/js/lot5-ui/expectations/cases/replace-008-note-to-aid-same-type.json": (
        "3ab21921663682c471873e710d52d52282464bf232a6b10e4d7b18e6426fa521"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-001-palette-plain-en.json": (
        "40a6b2c3f564758bf48e50de3270c460c96af5f614cd6fc39b455918160cb46e"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-002-palette-contrast-en.json": (
        "db0abe5e09317c8bae4b4014d7dbc30ca8c60d14b897e18faa93d0236d48b782"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-003-palette-locale-fr.json": (
        "7a1cc2f638e83096a90e0ede15ecaa36028d78c62da8eff6f2124ffc96006483"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-004-palette-locale-fr-ca.json": (
        "4f2fbdec6b0eb304b0c3705792fe35162d244bdc6490cf6e8e12a787a6081825"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-005-element-task.json": (
        "3166a9deb880e811f4560eda78a37a61527b759e2184f20bc6194e5108aa8386"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-006-element-user-task.json": (
        "5ba81da3307e691fdb9f9d629884d91e33387b9522885f3d583e7d2751d8a4b4"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-007-element-end.json": (
        "eff68450a1e28f1a21f8758fbb35d1331b48a4f6ccac69e75db4d0d490132542"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-008-element-reference.json": (
        "e93612e6ee02bfb1f44feedfa7d23189f8320c391c59af4ee4a7f8137ecd1119"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-009-element-annotation.json": (
        "19c094c3dcd980276ae21d90eb88cbdbf72c9ddb02a982e462c6957ebf952dd5"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-010-element-call.json": (
        "83b3c7cd64fbe508f9f48ea1a18ccc4b3a621a1e3223b807091e1989c6ea7dbc"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-013-compile-duplicate-upstream.json": (
        "c8446f358e98075e25c649408cb1b3c109a97189d701dea23de22a6761408456"
    ),
    "vendor/js/lot5-ui/expectations/cases/surfaces-014-compile-missing-fallback-text.json": (
        "c7b8c11fa4ee6c9b8efd78a6109477151f1cd63fac089483ca5f9be0de40f0d3"
    ),
    "vendor/js/lot5-ui/expectations/cases/twin-001-assignable-rule-user-task.json": (
        "84b34bd799290342a8ca6c3e39e48f7847f5d35a97574cbd5fec360041814678"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/basic-contrast.snapshot.json": (
        "3e1f2f052e6896840c941a7689f6ca4263b772de866a70afdf4b1ebb7882d90f"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/basic-review-page.snapshot.json": (
        "b6bc1dca51ab1b4bd8a06178a8c7016bf2ae38784f4c8fe37c223d82271f8dd9"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/basic.snapshot.json": (
        "e72fb51afb484918ca2c3aef4eff2a84502cbbd3c6e7aafd1a2f9baa8c8e7ce9"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/demo.snapshot.json": (
        "6010c128428ede2bb011f32da535c89237816d51beb6058b205a18a9fd4e1111"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/documents/foreign.snapshot.json": (
        "f2e87a42bb91bb4a11065985fb004dca3c7efdb15b36afb9e4e94d527739abac"
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
        "c495634b669e817af02545b040b1d767bb0ea098b4924a6247b984b53b6787a1"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/ui-neutral-registry.json": (
        "1dc918ec35fd0c60a78006a9c4bacfe3fc32b32c6b2e796810e7256f27139406"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/variants/duplicate-upstream.profile.json": (
        "7cbc0ecd30bfa22dc081b9d19fa2cfe89f7266b96a8822af9f84a6e3da01d20f"
    ),
    "vendor/js/lot5-ui/expectations/fixtures/variants/missing-fallback-text.profile.json": (
        "e89fd44d3433e337ce3660c61c44eeca2ee23a86915f75df6433180be33d62a5"
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
        "seal": "1e32756cf2f533568c59abcd90007e1da26d788db90816725ab18b586c7576e4",
    },
    {
        "cases": "vendor/js/lot3-cn/expectations/cases/",
        "pathBase": "vendor/js/",
        "seal": "7bd2d206277c123ad027481a42969f013cd91ddc4a2bfaab0e529fbc7120cb3c",
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
