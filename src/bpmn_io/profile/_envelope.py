"""Document envelope, support ownership and import projection (§5).

Closed ``DocumentEnvelope/1`` with sorted bindings, semantic revision via the
descriptor-driven projection, support import rules and the codec boundary:
callers may inject a ``codec`` callable, otherwise the wired
``bpmn_io.codec`` default parses the source bytes (document JSON for
``native-json``, the native tree projection for ``bpmn-xml``).
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bpmn_io.profile._c14n import digest, digest_bytes
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "DocumentEnvelope",
    "check_envelope_integrity",
    "check_envelope_shape",
    "complete_envelope",
    "extract_presentation",
    "import_envelope",
    "make_imported_di",
    "project_semantic",
    "sort_bindings",
    "validate_bindings",
    "validate_envelope",
]

#: Value-type namespaces classified as presentation (DESIGN §5 semantic
#: projection): BPMNDI, DI, DC and native color-DI/bioc. A property whose
#: value carries one of these types is presentation, wherever it appears.
_DI_VALUE_PREFIXES: Final[frozenset[str]] = frozenset({"bpmndi", "di", "dc", "bioc"})

#: Bounded projection traversal (DESIGN §2.5 host resource limits).
_MAX_PROJECTION_DEPTH: Final[int] = 4096
_MAX_PROJECTION_NODES: Final[int] = 4000000


@dataclass(frozen=True)
class DocumentEnvelope:
    """One closed ``DocumentEnvelope/1`` value."""

    document_version: str
    profile_identity: dict[str, object]
    tree: dict[str, object]
    bindings: list[dict[str, object]]
    semantic_revision: str

    def to_json(self) -> dict[str, object]:
        """Return the wire representation.

        Every container is deep-copied: mutating the returned document
        never changes the envelope.
        """
        return {
            "documentVersion": self.document_version,
            "profileIdentity": copy.deepcopy(self.profile_identity),
            "tree": copy.deepcopy(self.tree),
            "bindings": copy.deepcopy(self.bindings),
            "semanticRevision": self.semantic_revision,
        }


def sort_bindings(
    bindings: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Sort bindings by owner, role and target in UTF-16 order."""

    def _key(entry: dict[str, object]) -> tuple[bytes, bytes, bytes]:
        return (
            str(entry.get("ownerId", "")).encode("utf-16-be"),
            str(entry.get("role", "")).encode("utf-16-be"),
            str(entry.get("targetId", "")).encode("utf-16-be"),
        )

    return sorted(bindings, key=_key)


def validate_bindings(bindings: object) -> str | None:  # noqa: PLR0911
    """Validate one bindings array; return a refusal code or ``None``."""
    if not isinstance(bindings, list):
        return "profile-schema"
    seen: set[tuple[str, str]] = set()
    for entry in bindings:
        if not isinstance(entry, dict):
            return "profile-schema"
        owner = entry.get("ownerId")
        role = entry.get("role")
        target = entry.get("targetId")
        if not isinstance(owner, str) or not isinstance(role, str):
            return "profile-schema"
        if not isinstance(target, str):
            return "profile-schema"
        if not owner or not role or not target:
            return "profile-schema"
        if set(entry.keys()) != {"ownerId", "role", "targetId"}:
            return "profile-schema"
        if (owner, role) in seen:
            return "support-binding-conflict"
        seen.add((owner, role))
    return None


def _is_presentation_type(type_name: object) -> bool:
    """Return whether a ``$type`` names presentation (DI-family) content."""
    if not isinstance(type_name, str) or ":" not in type_name:
        return False
    return type_name.split(":", 1)[0] in _DI_VALUE_PREFIXES


def _is_presentation_dict(value: object) -> bool:
    """Return whether a value is a dict carrying a presentation ``$type``."""
    return isinstance(value, dict) and _is_presentation_type(value.get("$type"))


def _pending_containers(
    source: list[object], projected: list[object]
) -> list[tuple[object, object]]:
    """Pair kept container items with their fresh projection targets."""
    pairs: list[tuple[object, object]] = []
    kept_iter = iter(projected)
    for entry in source:
        if _is_presentation_dict(entry):
            continue
        try:
            fresh = next(kept_iter)
        except StopIteration:
            break
        if isinstance(entry, (dict, list)) and isinstance(fresh, (dict, list)):
            pairs.append((entry, fresh))
    return pairs


def _filter_list(key: str, value: list[object]) -> tuple[bool, list[object]]:
    """Filter one list value, dropping presentation items (keep, projected).

    The descriptor-qualified ``diagrams`` property is removed when nothing
    but presentation (or nothing at all) remains; any surviving semantic
    item keeps the property alive (partial diagrams).
    """
    kept: list[object] = []
    for entry in value:
        if _is_presentation_dict(entry):
            continue
        if isinstance(entry, dict):
            kept.append({})
        elif isinstance(entry, list):
            keep_nested, kept_nested = _filter_list("", entry)
            if keep_nested:
                kept.append(kept_nested)
        else:
            kept.append(entry)
    if key == "diagrams" and not kept:
        return False, kept
    return True, kept


def project_semantic(tree: object) -> object:
    """Project one native tree to its DI-free semantic form (closed).

    Driven by descriptor roles as value types, never by bare names: a
    property whose value carries a presentation ``$type`` is removed, and so
    is the descriptor-qualified ``diagrams`` property when nothing semantic
    remains. ``$attrs``, ``$type`` and every scalar semantic property
    survive, including names resembling geometry fields. Operates on plain
    JSON trees with an explicit stack (bounded).
    """
    if isinstance(tree, list):
        keep, kept = _filter_list("", tree)
        if not keep:
            return kept
        return _project_containers(tree, kept)
    if not isinstance(tree, dict):
        return tree
    return _project_containers(tree, {})


class _ProjectionCursor:
    """Explicit-stack projection state with shared bounds accounting."""

    def __init__(self) -> None:
        """Start with an empty work stack and node count."""
        self.stack: list[tuple[object, object, int]] = []
        self.seen = 0

    def check_depth(self, depth: int) -> None:
        """Enforce the traversal depth bound with a typed refusal."""
        if depth > _MAX_PROJECTION_DEPTH:
            raise ValueError("resource-limit")  # noqa: EM101

    def check_node(self) -> None:
        """Enforce the visited-node bound with a typed refusal."""
        self.seen += 1
        if self.seen > _MAX_PROJECTION_NODES:
            raise ValueError("resource-limit")  # noqa: EM101

    def queue(self, source: object, target: object, depth: int) -> None:
        """Queue one container pair for filling."""
        self.stack.append((source, target, depth))

    def fill_dict(self, source: dict[str, object], target: dict[str, object], depth: int) -> None:
        """Fill one fresh dict, queuing kept child containers."""
        for key, value in source.items():
            if not isinstance(key, str):
                # ValueError carries the closed refusal code (not a type error).
                raise ValueError("profile-schema")  # noqa: EM101, TRY004
            self.check_node()
            if _is_presentation_dict(value):
                continue
            if isinstance(value, dict):
                slot: dict[str, object] = {}
                target[key] = slot
                self.queue(value, slot, depth + 1)
            elif isinstance(value, list):
                keep, kept = _filter_list(key, value)
                if not keep:
                    continue
                target[key] = kept
                for entry, pending in _pending_containers(value, kept):
                    self.queue(entry, pending, depth + 1)
            else:
                target[key] = value

    def fill_list(self, source: list[object], target: list[object], depth: int) -> None:
        """Fill one fresh list, queuing kept child containers."""
        for value in source:
            self.check_node()
            if _is_presentation_dict(value):
                continue
            if isinstance(value, dict):
                slot_item: dict[str, object] = {}
                target.append(slot_item)
                self.queue(value, slot_item, depth + 1)
            elif isinstance(value, list):
                keep, kept = _filter_list("", value)
                if keep:
                    target.append(kept)
                    for entry, slot in _pending_containers(value, kept):
                        self.queue(entry, slot, depth + 1)
            else:
                target.append(value)


def _project_containers(source: object, target: object) -> object:
    """Fill fresh projection containers iteratively (explicit stack)."""
    cursor = _ProjectionCursor()
    cursor.queue(source, target, 0)
    while cursor.stack:
        current, fresh, depth = cursor.stack.pop()
        cursor.check_depth(depth)
        if isinstance(current, dict) and isinstance(fresh, dict):
            cursor.fill_dict(current, fresh, depth)
        elif isinstance(current, list) and isinstance(fresh, list):
            cursor.fill_list(current, fresh, depth)
        else:
            # ValueError carries the closed refusal code (not a type error).
            raise ValueError("profile-schema")  # noqa: EM101, TRY004
    return target


def _project_dict(node: dict[str, object]) -> dict[str, object]:
    """Project one mapping, dropping presentation members (fresh containers)."""
    if not isinstance(node, dict):
        # ValueError carries the closed refusal code (not a type error).
        raise ValueError("complete-envelope-shape")  # noqa: EM101, TRY004
    return _project_containers(node, {})  # type: ignore[return-value]


class _ExtractionCursor:
    """Explicit-stack extraction state with shared bounds accounting."""

    def __init__(self) -> None:
        """Start with an empty work stack and node count."""
        self.stack: list[tuple[object, int]] = []
        self.seen = 0
        self.found: list[object] = []

    def queue(self, value: object, depth: int) -> None:
        """Queue one child value for visiting."""
        self.seen += 1
        if self.seen > _MAX_PROJECTION_NODES:
            raise ValueError("resource-limit")  # noqa: EM101
        if _is_presentation_dict(value):
            self.found.append(copy.deepcopy(value))
        elif isinstance(value, (dict, list)):
            self.stack.append((value, depth + 1))

    def visit(self, current: object, depth: int) -> None:
        """Visit one container's direct values."""
        if depth > _MAX_PROJECTION_DEPTH:
            raise ValueError("resource-limit")  # noqa: EM101
        if isinstance(current, dict):
            for value in current.values():
                self.queue(value, depth)
        elif isinstance(current, list):
            for value in current:
                self.queue(value, depth)


def extract_presentation(tree: object) -> list[object]:
    """Collect the presentation values a projection drops, in source order.

    Returns deep copies of every DI-typed value in the tree, so the
    extracted diagrams survive independently of the projected tree.
    Iterative with the same explicit bounds as the projection.
    """
    cursor = _ExtractionCursor()
    cursor.stack.append((tree, 0))
    while cursor.stack:
        current, depth = cursor.stack.pop()
        cursor.visit(current, depth)
    return cursor.found


def make_imported_di(tree: object, descriptor_digest: str = "") -> dict[str, object]:
    """Build the separately preserved DI record for one source tree."""
    diagrams = extract_presentation(tree)
    record: dict[str, object] = {
        "descriptorDigest": descriptor_digest,
        "diagrams": diagrams,
    }
    record["sha256"] = digest({"descriptorDigest": descriptor_digest, "diagrams": diagrams})
    return record


def _semantic_revision(
    tree: object, profile_identity: dict[str, object], bindings: list[dict[str, object]]
) -> str:
    """Compute ``semanticRevision`` per §3.1 (acceptance-context revision)."""
    return digest(
        {
            "tree": project_semantic(tree),
            "profileIdentity": profile_identity,
            "bindings": sort_bindings(bindings),
        }
    )


#: Closed profile-identity pin record (DESIGN §5.1, envelope identity).
_IDENTITY_KEYS: Final[tuple[str, ...]] = (
    "mechanismVersion",
    "schemaVersion",
    "profile",
    "version",
    "sha256",
    "base",
    "descriptors",
)

_HEX64_RE: Final[str] = "^[0-9a-f]{64}$"


def _check_identity_values(profile_identity: dict[str, object]) -> str | None:
    """Validate the pinned identity values (refusal or None, DESIGN §5.1)."""
    if profile_identity.get("mechanismVersion") != "1":
        return "profile-schema"
    if profile_identity.get("schemaVersion") != "1.0.0":
        return "profile-schema"
    if re.fullmatch(_HEX64_RE, str(profile_identity.get("sha256"))) is None:
        return "profile-schema"
    return None


def _check_identity_shape(profile_identity: object) -> str | None:
    """Validate the closed identity record (refusal or None, DESIGN §5.1)."""
    if not isinstance(profile_identity, dict):
        return "profile-schema"
    if set(profile_identity.keys()) != set(_IDENTITY_KEYS):
        return "profile-schema"
    for key in ("mechanismVersion", "schemaVersion", "profile", "version", "sha256"):
        if not isinstance(profile_identity.get(key), str):
            return "profile-schema"
    if not isinstance(profile_identity.get("base"), dict):
        return "profile-schema"
    if not isinstance(profile_identity.get("descriptors"), list):
        return "profile-schema"
    return _check_identity_values(profile_identity)


def _check_tree_shape(tree: object) -> str | None:
    """Validate the closed committed-tree shape (refusal or None)."""
    if not isinstance(tree, dict):
        return "profile-schema"
    if not isinstance(tree.get("$type"), str):
        return "profile-schema"
    return None


#: Closed envelope members (DESIGN §5.1).
_CLOSED_ENVELOPE_KEYS: Final[frozenset[str]] = frozenset(
    {"documentVersion", "profileIdentity", "tree", "bindings", "semanticRevision"}
)

#: Closed profile-identity pin record members (DESIGN §5.1).
_CLOSED_PIN_KEYS: Final[frozenset[str]] = frozenset({"id", "version", "sha256"})


def _check_pin(pin: object) -> str | None:
    """Validate one closed ``{id, version, sha256}`` pin (refusal or None)."""
    if not isinstance(pin, dict) or set(pin.keys()) != _CLOSED_PIN_KEYS:
        return "profile-schema"
    for key in ("id", "version", "sha256"):
        if not isinstance(pin.get(key), str):
            return "profile-schema"
    return None


def _check_identity_full(  # noqa: PLR0911 - one return per pin failure
    profile_identity: object,
) -> str | None:
    """Validate the closed §5.1 identity record with pins (refusal or None)."""
    if not isinstance(profile_identity, dict):
        return "profile-schema"
    if set(profile_identity.keys()) != set(_IDENTITY_KEYS):
        return "profile-schema"
    for key in ("mechanismVersion", "schemaVersion", "profile", "version", "sha256"):
        if not isinstance(profile_identity.get(key), str):
            return "profile-schema"
    code = _check_identity_values(profile_identity)
    if code is not None:
        return code
    if _check_pin(profile_identity.get("base")) is not None:
        return "profile-schema"
    descriptors = profile_identity.get("descriptors")
    if not isinstance(descriptors, list) or not descriptors:
        return "profile-schema"
    for entry in descriptors:
        if _check_pin(entry) is not None:
            return "profile-schema"
    return None


def check_envelope_shape(  # noqa: PLR0911 - one return per shape failure
    envelope: object,
) -> str | None:
    """Validate the envelope shape needed to read version, identity and revision.

    Checks the closed envelope members, the unknown ``documentVersion``
    (``document-version-unsupported``), the closed §5.1 identity record
    with pins, the committed-tree object with ``$type`` and the string
    revision; anything else refuses ``profile-schema``. Bindings content
    and revision integrity belong to :func:`check_envelope_integrity`.
    """
    if not isinstance(envelope, dict):
        return "profile-schema"
    if set(envelope.keys()) != _CLOSED_ENVELOPE_KEYS:
        return "profile-schema"
    if envelope.get("documentVersion") != "1":
        return "document-version-unsupported"
    if _check_identity_full(envelope.get("profileIdentity")) is not None:
        return "profile-schema"
    if _check_tree_shape(envelope.get("tree")) is not None:
        return "profile-schema"
    if not isinstance(envelope.get("semanticRevision"), str):
        return "profile-schema"
    return None


def _collect_ids(tree: object) -> set[str]:
    """Collect every string element id of one JSON tree (bounded, iterative)."""
    found: set[str] = set()
    stack: list[tuple[object, int]] = [(tree, 0)]
    seen = 0
    while stack:
        current, depth = stack.pop()
        seen += 1
        if seen > _MAX_PROJECTION_NODES or depth > _MAX_PROJECTION_DEPTH:
            break
        if isinstance(current, dict):
            element_id = current.get("id")
            if isinstance(element_id, str):
                found.add(element_id)
            stack.extend((value, depth + 1) for value in current.values())
        elif isinstance(current, list):
            stack.extend((value, depth + 1) for value in current)
    return found


def _check_bindings_integrity(bindings: list[object], known_ids: set[str]) -> str | None:
    """Check binding ownership and target uniqueness (refusal or None)."""
    seen_targets: set[str] = set()
    for entry in bindings:
        if not isinstance(entry, dict):
            return "profile-schema"
        owner = entry.get("ownerId")
        target = entry.get("targetId")
        if not isinstance(owner, str) or not isinstance(target, str):
            return "profile-schema"
        if owner not in known_ids or target not in known_ids:
            return "support-binding-conflict"
        if target in seen_targets:
            return "support-binding-conflict"
        seen_targets.add(target)
    return None


def check_envelope_integrity(  # noqa: PLR0911 - one return per integrity failure
    envelope: object,
) -> str | None:
    """Validate envelope integrity after compatibility (refusal or None).

    Checks binding record shape (``profile-schema``), owner+role
    uniqueness, duplicate records, every binding ``ownerId``/``targetId``
    naming an element and no ``targetId`` bound twice (else
    ``support-binding-conflict``), then the committed semantic projection
    and revision (else ``profile-schema``).
    """
    if not isinstance(envelope, dict):
        return "profile-schema"
    bindings = envelope.get("bindings")
    tree = envelope.get("tree")
    profile_identity = envelope.get("profileIdentity")
    code = validate_bindings(bindings)
    if code is not None:
        return code
    if (
        not isinstance(bindings, list)
        or not isinstance(tree, dict)
        or not isinstance(profile_identity, dict)
    ):
        return "profile-schema"
    known_ids = _collect_ids(tree)
    code = _check_bindings_integrity(bindings, known_ids)
    if code is not None:
        return code
    try:
        projected = _project_dict(tree)
    except ValueError:
        return "profile-schema"
    if projected != tree:
        return "profile-schema"
    want = _semantic_revision(tree, profile_identity, bindings)
    if envelope.get("semanticRevision") != want:
        return "profile-schema"
    return None


def validate_envelope(  # noqa: C901, PLR0911
    envelope: object,
    *,
    committed: bool = True,
) -> str | None:
    """Validate one envelope value; return a refusal code or ``None``.

    Checks the closed envelope keys, the pinned identity record, the
    committed-tree shape, the closed bindings and the projection-based
    revision. With ``committed`` (default) the tree must already be its own
    semantic projection: a diagrams-bearing candidate is not a committable
    tree. The bridge commit path passes ``committed=False`` because it
    extracts DI and projects before storing.
    """
    if not isinstance(envelope, dict):
        return "profile-schema"
    if set(envelope.keys()) != {
        "documentVersion",
        "profileIdentity",
        "tree",
        "bindings",
        "semanticRevision",
    }:
        return "profile-schema"
    if envelope.get("documentVersion") != "1":
        return "document-version-unsupported"
    profile_identity = envelope.get("profileIdentity")
    bindings = envelope.get("bindings")
    tree = envelope.get("tree")
    code = _check_identity_shape(profile_identity)
    if code is not None:
        return code
    code = _check_tree_shape(tree)
    if code is not None:
        return code
    if not isinstance(tree, dict) or not isinstance(profile_identity, dict):
        return "profile-schema"
    code = validate_bindings(bindings)
    if code is not None:
        return code
    if not isinstance(bindings, list):
        return "profile-schema"
    if committed and _project_dict(tree) != tree:
        return "profile-schema"
    want = _semantic_revision(tree, profile_identity, bindings)
    if envelope.get("semanticRevision") != want:
        return "profile-schema"
    return None


def complete_envelope(
    profile_identity: dict[str, object],
    tree: dict[str, object],
    bindings: list[dict[str, object]] | None = None,
) -> DocumentEnvelope:
    """Build one envelope with sorted bindings and computed revision.

    The committed tree is the DI-free semantic projection; inputs are
    deep-copied so later caller mutations cannot change the envelope.
    """
    owned_identity = copy.deepcopy(profile_identity)
    owned_tree = copy.deepcopy(tree)
    ordered = sort_bindings(copy.deepcopy(list(bindings or [])))
    projected = _project_dict(owned_tree)
    revision = _semantic_revision(projected, owned_identity, ordered)
    return DocumentEnvelope(
        document_version="1",
        profile_identity=owned_identity,
        tree=projected,
        bindings=ordered,
        semantic_revision=revision,
    )


def _default_codec(source_format: str) -> Callable[[bytes], object]:
    """Return the wired ``bpmn_io.codec`` document decoder for one format.

    ``bpmn-xml`` parses through the codec lane (parse then project to the
    document JSON of the native tree, DESIGN §5/§8.1); any other format reads
    raw document JSON bytes. Failures raise and stay typed at the boundary.
    """

    def _decode_xml(raw: bytes) -> object:
        from bpmn_io.codec import parse_xml, project  # noqa: PLC0415 - wired lane, lazy

        parsed = parse_xml(raw)
        if not parsed.ok or parsed.value is None:
            msg = "bpmn-xml source did not parse"
            raise ValueError(msg)
        projected = project(parsed.value)
        if not projected.ok or not isinstance(projected.value, dict):
            msg = "bpmn-xml source did not project"
            raise ValueError(msg)
        return projected.value

    def _decode_json(raw: bytes) -> object:
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as err:
            msg = f"document JSON did not parse: {err}"
            raise ValueError(msg) from err

    if source_format == "bpmn-xml":
        return _decode_xml
    return _decode_json


def import_envelope(
    source: object,
    profile_identity: dict[str, object],
    *,
    codec: Callable[[bytes], object] | None = None,
    source_format: str = "native-json",
) -> PureResult:
    """Import one source into an envelope (projection + bindings).

    ``source`` is either an already materialized native JSON tree or raw
    bytes carrying a document JSON value. When raw bytes must be parsed, an
    injected ``codec`` callable wins; otherwise the wired ``bpmn_io.codec``
    default decodes them (document JSON for ``native-json``, parse then
    project for ``bpmn-xml``). Unparseable sources refuse with
    ``document-not-loaded``. ``source_format`` is ``native-json`` or
    ``bpmn-xml`` and selects the initial-import ``baseRevision`` formula for
    callers.
    """
    _ = source_format
    decode = codec if codec is not None else _default_codec(source_format)
    tree: object = {}
    if isinstance(source, dict):
        tree = source
    elif isinstance(source, (bytes, bytearray)):
        try:
            tree = decode(bytes(source))
        except Exception:  # noqa: BLE001 - codec failures stay typed
            return PureRefused(code="document-not-loaded")
        if not isinstance(tree, dict):
            return PureRefused(code="document-not-loaded")
    else:
        return PureRefused(code="document-not-loaded")
    try:
        text = json.dumps(tree)
        _ = text
    except (TypeError, ValueError):
        return PureRefused(code="profile-schema")
    envelope = complete_envelope(profile_identity, tree, [])
    return PureSuccess(payload=envelope)


def initial_base_revision(
    source_format: str, source_tree: object = None, source_bytes: bytes | None = None
) -> str:
    """Compute the initial-import ``baseRevision`` per §3.1."""
    if source_format == "native-json":
        if source_tree is None:
            return digest({"domain": "profile-import/1", "format": source_format})
        return (
            digest({"domain": "profile-import/1", "format": source_format})
            if source_tree is None
            else digest(
                {
                    "domain": "profile-import/1",
                    "format": source_format,
                    "sourceDigest": digest(source_tree),
                }
            )
        )
    raw = source_bytes or b""
    return digest(
        {
            "domain": "profile-import/1",
            "format": source_format,
            "sourceDigest": digest_bytes(raw),
        }
    )
