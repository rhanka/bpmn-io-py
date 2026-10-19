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
  (a transcription of the harness values, DESIGN R3.3 §14.3).

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


def parity_manifest(files: dict[str, str]) -> dict[str, object]:
    """Return the parity manifest (sha256 of every parity file and referenced artifact)."""
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
        ],
        "pathBase": PATH_BASE,
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
        record = parity_record(_as_dict(load_json(path)))
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
    want = json.dumps(parity_manifest(files), indent=2, ensure_ascii=True) + "\n"
    if not manifest.is_file() or manifest.read_text(encoding="utf-8") != want:
        problems.append("parity/manifest.json differs from the derived manifest")
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
    """Recompute every derived value of every expectation file and the parity tree."""
    problems: list[str] = []
    for path in sorted(HERE.glob("*.json")):
        problems.extend(f"{path.name}: {problem}" for problem in check_file(path))
    problems.extend(check_parity())
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
