"""Document envelope, support ownership and import projection (§5).

Closed ``DocumentEnvelope/1`` with sorted bindings, semantic revision via the
descriptor-driven projection, support import rules and the codec boundary:
callers may inject a ``codec`` callable, otherwise the wired
``bpmn_io.codec`` default parses the source bytes (document JSON for
``native-json``, the native tree projection for ``bpmn-xml``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bpmn_io.profile._c14n import digest, digest_bytes
from bpmn_io.profile._results import PureRefused, PureResult, PureSuccess

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "DocumentEnvelope",
    "complete_envelope",
    "import_envelope",
    "project_semantic",
    "sort_bindings",
    "validate_bindings",
    "validate_envelope",
]

#: Presentation roles excluded from the semantic projection (descriptor roles).
_PRESENTATION_SUFFIXES = ("Di", "DI", "diagrams", "di", "bounds", "waypoint")


@dataclass(frozen=True)
class DocumentEnvelope:
    """One closed ``DocumentEnvelope/1`` value."""

    document_version: str
    profile_identity: dict[str, object]
    tree: dict[str, object]
    bindings: list[dict[str, object]]
    semantic_revision: str

    def to_json(self) -> dict[str, object]:
        """Return the wire representation."""
        return {
            "documentVersion": self.document_version,
            "profileIdentity": self.profile_identity,
            "tree": self.tree,
            "bindings": list(self.bindings),
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
        if set(entry.keys()) != {"ownerId", "role", "targetId"}:
            return "profile-schema"
        if (owner, role) in seen:
            return "support-binding-conflict"
        seen.add((owner, role))
    return None


def project_semantic(tree: object) -> object:
    """Project one native tree to its DI-free semantic form (closed).

    Removes ``diagrams`` and presentation properties while preserving all
    admitted semantic extension values, IDs, names and reference arrays.
    Operates on plain JSON trees with an explicit stack (bounded).
    """
    if isinstance(tree, list):
        return [project_semantic(entry) for entry in tree]
    if not isinstance(tree, dict):
        return tree
    return _project_dict(tree)


def _project_dict(node: dict[str, object]) -> dict[str, object]:
    """Project one mapping, dropping presentation members."""
    out: dict[str, object] = {}
    for key, value in node.items():
        if key == "diagrams":
            continue
        if (
            key.endswith(_PRESENTATION_SUFFIXES)
            and key not in ("id", "name")
            and key in ("bounds", "waypoint", "di", "diagrams")
        ):
            continue
        out[key] = project_semantic(value)
    return out


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


def validate_envelope(  # noqa: PLR0911
    envelope: object,
) -> str | None:
    """Validate one envelope value; return a refusal code or ``None``."""
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
    if not isinstance(profile_identity, dict) or not isinstance(tree, dict):
        return "profile-schema"
    code = validate_bindings(bindings)
    if code is not None:
        return code
    if not isinstance(bindings, list):
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
    """Build one envelope with sorted bindings and computed revision."""
    ordered = sort_bindings(list(bindings or []))
    revision = _semantic_revision(tree, profile_identity, ordered)
    return DocumentEnvelope(
        document_version="1",
        profile_identity=dict(profile_identity),
        tree=dict(tree),
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
