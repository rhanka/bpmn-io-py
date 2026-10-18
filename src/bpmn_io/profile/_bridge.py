"""Headless native bridge counterpart (DESIGN R3.3 §8.1, Python sync form).

Keeps one immutable descriptor context, one loaded envelope and explicit
revision guards. Getters are synchronous immutable reads; loading and command
application validate revisions and refuse with the closed §10.1 codes instead
of raising. No editor scheduling, browser handle or network access.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bpmn_io.profile._c14n import digest
from bpmn_io.profile._envelope import (
    DocumentEnvelope,
    complete_envelope,
    make_imported_di,
    validate_bindings,
    validate_envelope,
)
from bpmn_io.profile._results import Report, ResultRefused, ResultSuccess

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.profile._compiler import DescriptorContext

__all__ = ["HeadlessBridge", "create_bridge"]


def _check_imported_di(record: object) -> str | None:
    """Validate one caller-supplied DI record with its digest (refusal or None)."""
    if not isinstance(record, dict):
        return "snapshot-schema"
    if (
        set(record.keys()) != {"descriptorDigest", "diagrams", "sha256"}
        or not isinstance(record.get("descriptorDigest"), str)
        or not isinstance(record.get("diagrams"), list)
        or not isinstance(record.get("sha256"), str)
    ):
        return "snapshot-schema"
    want = digest({"descriptorDigest": record["descriptorDigest"], "diagrams": record["diagrams"]})
    if record["sha256"] != want:
        return "snapshot-schema"
    return None


@dataclass
class HeadlessBridge:
    """One in-memory document session over native JSON trees."""

    descriptor_context: DescriptorContext | None = None
    envelope: DocumentEnvelope | None = None
    history: list[tuple[DocumentEnvelope, dict[str, object]]] = field(default_factory=list)
    imported_di: dict[str, object] = field(default_factory=dict)
    disposed: bool = False

    def set_descriptor_context(self, context: DescriptorContext) -> None:
        """Bind the immutable descriptor context for this session."""
        self.descriptor_context = context

    def set_definitions(
        self,
        envelope: DocumentEnvelope,
        *,
        expected_revision: str | None = None,
        codec: Callable[[bytes], object] | None = None,
        imported_di: dict[str, object] | None = None,
    ) -> ResultSuccess | ResultRefused:
        """Load one envelope, guarding the expected revision.

        The committed tree is always the DI-free semantic projection;
        presentation extracted from the supplied tree is preserved
        separately as the session DI record (never silently lost). An
        explicit ``imported_di`` record overrides the extracted one.
        """
        _ = codec
        report = Report(operation="setDefinitions", entries=())
        if self.disposed:
            return ResultRefused(
                operation="setDefinitions",
                code="canvas-disposed",
                diagnostics=(),
                report=report,
            )
        code = validate_envelope(envelope.to_json(), committed=False)
        if code is not None:
            return ResultRefused(
                operation="setDefinitions",
                code=code,
                diagnostics=(),
                report=report,
                profile_identity=dict(envelope.profile_identity),
            )
        if imported_di is not None:
            code = _check_imported_di(imported_di)
            if code is not None:
                return ResultRefused(
                    operation="setDefinitions",
                    code=code,
                    diagnostics=(),
                    report=report,
                    profile_identity=dict(envelope.profile_identity),
                )
        if expected_revision is not None and (
            self.envelope is None or self.envelope.semantic_revision != expected_revision
        ):
            return ResultRefused(
                operation="setDefinitions",
                code="operation-error",
                diagnostics=(),
                report=report,
                profile_identity=dict(envelope.profile_identity),
            )
        committed = complete_envelope(envelope.profile_identity, envelope.tree, envelope.bindings)
        stored_di = (
            copy.deepcopy(imported_di)
            if imported_di is not None
            else make_imported_di(envelope.tree, "")
        )
        if self.envelope is not None:
            self.history.append((self.envelope, self.imported_di))
        self.envelope = committed
        self.imported_di = stored_di
        return ResultSuccess(
            operation="setDefinitions",
            profile_identity=dict(committed.profile_identity),
            base_revision=committed.semantic_revision,
            revision=committed.semantic_revision,
            report=report,
            payload={
                "envelope": committed.to_json(),
                "semanticRevision": committed.semantic_revision,
                "viewRevision": committed.semantic_revision,
            },
        )

    def get_definitions(self) -> ResultSuccess | ResultRefused:
        """Return the loaded envelope or a typed refusal when empty."""
        report = Report(operation="getDefinitions", entries=())
        if self.disposed:
            return ResultRefused(
                operation="getDefinitions",
                code="canvas-disposed",
                diagnostics=(),
                report=report,
            )
        if self.envelope is None:
            return ResultRefused(
                operation="getDefinitions",
                code="document-not-loaded",
                diagnostics=(),
                report=report,
            )
        envelope = self.envelope
        return ResultSuccess(
            operation="getDefinitions",
            profile_identity=dict(envelope.profile_identity),
            base_revision=envelope.semantic_revision,
            revision=envelope.semantic_revision,
            report=report,
            payload=envelope.to_json(),
        )

    def apply_commands(
        self,
        *,
        base_revision: str,
        commands: object,
        codec: Callable[[bytes], object] | None = None,
    ) -> ResultSuccess | ResultRefused:
        """Apply one validated command batch atomically (no partial commit)."""
        _ = codec
        report = Report(operation="applyCommands", entries=())
        if self.disposed:
            return ResultRefused(
                operation="applyCommands",
                code="canvas-disposed",
                diagnostics=(),
                report=report,
            )
        if self.envelope is None:
            return ResultRefused(
                operation="applyCommands",
                code="document-not-loaded",
                diagnostics=(),
                report=report,
            )
        current = self.envelope
        if current.semantic_revision != base_revision:
            return ResultRefused(
                operation="applyCommands",
                code="operation-error",
                diagnostics=(),
                report=report,
                profile_identity=dict(current.profile_identity),
                base_revision=current.semantic_revision,
            )
        if not isinstance(commands, list):
            return ResultRefused(
                operation="applyCommands",
                code="operation-error",
                diagnostics=(),
                report=report,
                profile_identity=dict(current.profile_identity),
                base_revision=current.semantic_revision,
            )
        # Headless commands carry explicit tree patches; an empty batch is a
        # no-op that echoes the current revision without history growth.
        if not commands:
            return ResultSuccess(
                operation="applyCommands",
                profile_identity=dict(current.profile_identity),
                base_revision=current.semantic_revision,
                revision=current.semantic_revision,
                report=report,
                payload={
                    "envelope": current.to_json(),
                    "semanticRevision": current.semantic_revision,
                    "changed": False,
                },
            )
        # Non-empty batches without a wired codec stay refused: applying raw
        # patches would bypass descriptor validation owned by later lots.
        return ResultRefused(
            operation="applyCommands",
            code="operation-error",
            diagnostics=(),
            report=report,
            profile_identity=dict(current.profile_identity),
            base_revision=current.semantic_revision,
        )

    def get_snapshot(self) -> ResultSuccess | ResultRefused:
        """Return one closed snapshot for the loaded envelope."""
        report = Report(operation="getSnapshot", entries=())
        if self.disposed:
            return ResultRefused(
                operation="getSnapshot",
                code="canvas-disposed",
                diagnostics=(),
                report=report,
            )
        if self.envelope is None:
            return ResultRefused(
                operation="getSnapshot",
                code="document-not-loaded",
                diagnostics=(),
                report=report,
            )
        envelope = self.envelope
        snapshot: dict[str, object] = {
            "snapshotVersion": "1",
            "envelope": envelope.to_json(),
            "presentation": {
                "layout": {"layoutVersion": "1", "pages": [], "geometry": []},
                "themeId": "plain",
                "overrides": {"semantic": [], "occurrence": []},
                "diStyles": {"native": [], "bioc": []},
                "importedDi": copy.deepcopy(self.imported_di),
                "selection": [],
                "activePageId": "",
            },
            "viewRevision": envelope.semantic_revision,
        }
        return ResultSuccess(
            operation="getSnapshot",
            profile_identity=dict(envelope.profile_identity),
            base_revision=envelope.semantic_revision,
            revision=envelope.semantic_revision,
            report=report,
            payload=snapshot,
        )

    def undo(self) -> ResultSuccess | ResultRefused:
        """Restore the previous envelope revision when available."""
        report = Report(operation="undo", entries=())
        if self.disposed:
            return ResultRefused(
                operation="undo",
                code="canvas-disposed",
                diagnostics=(),
                report=report,
            )
        if not self.history:
            return ResultRefused(
                operation="undo",
                code="operation-error",
                diagnostics=(),
                report=report,
            )
        envelope, stored_di = self.history.pop()
        self.envelope = envelope
        self.imported_di = stored_di
        return ResultSuccess(
            operation="undo",
            profile_identity=dict(envelope.profile_identity),
            base_revision=envelope.semantic_revision,
            revision=envelope.semantic_revision,
            report=report,
            payload={"envelope": envelope.to_json()},
        )

    def dispose(self) -> None:
        """Dispose this session; later calls refuse as disposed."""
        self.disposed = True


def create_bridge(
    context: DescriptorContext | None = None,
) -> HeadlessBridge:
    """Create one headless bridge, optionally bound to ``context``."""
    bridge = HeadlessBridge()
    if context is not None:
        bridge.set_descriptor_context(context)
    return bridge


def rebuild_envelope_for_test(
    profile_identity: dict[str, object],
    tree: dict[str, object],
    bindings: list[dict[str, object]] | None = None,
) -> DocumentEnvelope:
    """Rebuild one envelope in tests (sorted bindings, fresh revision)."""
    ordered = list(bindings or [])
    code = validate_bindings(ordered)
    if code is not None:
        message = f"invalid test bindings: {code}"
        raise ValueError(message)
    return complete_envelope(profile_identity, tree, ordered)
