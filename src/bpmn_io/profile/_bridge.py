"""Headless native bridge counterpart (DESIGN R3.3 §8.1, Python sync form).

Keeps one immutable descriptor context, one loaded envelope, the active
business profile, guarded undo/redo stacks and change listeners. Document
operations validate revisions and refuse with the closed section-10.1 codes
instead of raising; read-only queries return ``PureResult``. No editor
scheduling, browser handle or network access.
"""

from __future__ import annotations

import copy
import importlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from bpmn_io.profile._c14n import digest
from bpmn_io.profile._envelope import (
    DocumentEnvelope,
    complete_envelope,
    make_imported_di,
    validate_bindings,
    validate_envelope,
)
from bpmn_io.profile._queries import (
    check_field as _query_check_field,
)
from bpmn_io.profile._queries import (
    copy_fragment,
)
from bpmn_io.profile._queries import (
    list_entries as _query_list_entries,
)
from bpmn_io.profile._queries import (
    list_fields as _query_list_fields,
)
from bpmn_io.profile._queries import (
    query_references as _query_references,
)
from bpmn_io.profile._results import (
    PureRefused,
    PureResult,
    Report,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    make_coordinate,
    pure_refused,
    pure_success,
)
from bpmn_io.profile._transaction import ApplyError, StagedResult, run_apply
from bpmn_io.profile._ui import compiled_identity

if TYPE_CHECKING:
    from collections.abc import Callable

    from bpmn_io.profile._compiler import CompiledProfile, DescriptorContext

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
class _HistoryEntry:
    """One undoable batch with its stored normalized states."""

    transaction_id: str
    envelope: DocumentEnvelope
    imported_di: dict[str, object]


def _lot4_view_revision(
    compiled: CompiledProfile | None,
    envelope: DocumentEnvelope,
    imported_di: dict[str, object],
) -> str | None:
    """Attempt the lot-4 section-9.2 view digest (None when unavailable).

    Calls through the lot-4 ``compute_layout`` signature; any missing
    entry point, refusal or unexpected shape falls back to the
    semantic-revision placeholder the caller applies.
    """
    try:
        layout_module = importlib.import_module("bpmn_io.profile._layout")
        compute_layout = layout_module.compute_layout
    except ImportError:
        return None
    try:
        outcome = compute_layout(compiled, envelope, [], imported_di, theme_id="plain")
    except Exception:  # noqa: BLE001 - layout stays out of the guards
        return None
    if getattr(outcome, "status", None) != "ok":
        return None
    payload = getattr(outcome, "payload", None)
    if isinstance(payload, dict) and isinstance(payload.get("viewRevision"), str):
        return str(payload["viewRevision"])
    return None


def _entry_from_wire(entry: dict[str, object], severity: str, classification: str) -> ReportEntry:
    """Convert one wire entry to a ReportEntry, keeping every closed key."""
    source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
    if not isinstance(source, dict) or not isinstance(result, dict):
        message = "report entry carries no coordinates"
        raise TypeError(message)

    def _opt(key: str) -> str | None:
        value = entry.get(key)
        return value if isinstance(value, str) else None

    return ReportEntry(
        code=str(entry.get("code")),
        severity=entry.get("severity", severity),  # type: ignore[arg-type]
        classification=entry.get("classification", classification),  # type: ignore[arg-type]
        stage=str(entry.get("stage")),
        rule_id=str(entry.get("ruleId")),
        message_key=str(entry.get("messageKey")),
        disposition=entry.get("disposition", "observed"),  # type: ignore[arg-type]
        source=make_coordinate(
            str(source.get("domain", "none")),
            source.get("pointer"),
            source.get("targetId"),
            str(source.get("provenance", "unavailable")),
        ),
        result=make_coordinate(
            str(result.get("domain", "none")),
            result.get("pointer"),
            result.get("targetId"),
            str(result.get("provenance", "unavailable")),
        ),
        before_present=bool(entry.get("beforePresent")),
        after_present=bool(entry.get("afterPresent")),
        before=entry.get("before"),
        after=entry.get("after"),
        original_type=_opt("originalType"),
        property=_opt("property"),
        caused_by=_opt("causedBy"),
        page_id=_opt("pageId"),
        occurrence_key=_opt("occurrenceKey"),
        emitted_type=_opt("emittedType"),
        legacy_code=_opt("legacyCode"),
        loss_class=_opt("lossClass"),
    )


def _with_revision(payload: dict[str, object], revision: str) -> PureResult:
    """Inject the committed revision into a read-only query payload."""
    return pure_success({"revision": revision, **payload})


@dataclass
class HeadlessBridge:
    """One in-memory document session over native JSON trees."""

    descriptor_context: DescriptorContext | None = None
    envelope: DocumentEnvelope | None = None
    history: list[_HistoryEntry] = field(default_factory=list)
    imported_di: dict[str, object] = field(default_factory=dict)
    disposed: bool = False
    # lot 5: active business profile, redo stack, epoch, listeners, guard.
    compiled: CompiledProfile | None = None
    redo_history: list[_HistoryEntry] = field(default_factory=list)
    history_epoch: int = 0
    _state: str = "idle"
    _listeners: dict[str, Callable[[dict[str, object]], None]] = field(default_factory=dict)
    _subscription_counter: int = 0

    def set_descriptor_context(self, context: DescriptorContext) -> None:
        """Bind the immutable descriptor context for this session."""
        self.descriptor_context = context

    # -- internal helpers (lot 5) -------------------------------------------

    def _report_success(
        self, operation: str, identity: dict[str, object], base: str, revision: str
    ) -> Report:
        """Build one entry-free success report with the section-3.4 header."""
        return Report(
            operation=operation,
            entries=(),
            source_identity=copy.deepcopy(identity),
            target_identity=copy.deepcopy(identity),
            input_revision=base,
            output_revision=revision,
        )

    def _report_refusal(
        self,
        operation: str,
        identity: dict[str, object] | None,
        base: str | None,
        entries: list[dict[str, object]] | tuple[dict[str, object], ...] = (),
    ) -> Report:
        """Build one refusal report, echoing identity and revision when set."""
        wire_entries: list[ReportEntry] = []
        for entry in entries:
            if isinstance(entry, ReportEntry):
                wire_entries.append(entry)
            elif isinstance(entry, dict):
                wire_entries.append(_entry_from_wire(entry, "error", "integrity"))
        return Report(
            operation=operation,
            entries=tuple(wire_entries),
            source_identity=copy.deepcopy(identity) if identity is not None else None,
            target_identity=None,
            input_revision=base,
            output_revision=None,
        )

    def _echo(self) -> tuple[dict[str, object] | None, str | None]:
        """Return the echoed identity and revision when the rules allow it."""
        if self.disposed or self.envelope is None:
            return None, None
        return dict(self.envelope.profile_identity), self.envelope.semantic_revision

    def _refuse(
        self, operation: str, code: str, entries: list[dict[str, object]] | None = None
    ) -> ResultRefused:
        """Build one refusal with echo and ``diagnostics == report.entries``."""
        identity, base = self._echo()
        report = self._report_refusal(operation, identity, base, tuple(entries or []))
        return ResultRefused(
            operation=operation,
            code=code,
            diagnostics=tuple(entry.to_json() for entry in report.entries),
            report=report,
            profile_identity=identity,
            base_revision=base,
        )

    def _refuse_bare(self, operation: str, code: str) -> ResultRefused:
        """Build one refusal that echoes neither identity nor revision."""
        report = self._report_refusal(operation, None, None)
        return ResultRefused(
            operation=operation,
            code=code,
            diagnostics=(),
            report=report,
        )

    def _current_view(self, envelope: DocumentEnvelope) -> str:
        """Return the current viewRevision (lot-4 digest or the placeholder)."""
        view = _lot4_view_revision(self.compiled, envelope, self.imported_di)
        return view if view is not None else envelope.semantic_revision

    def _presentation(self) -> dict[str, object]:
        """Build the snapshot presentation with the archived DI record."""
        return {
            "layout": {"layoutVersion": "1", "pages": [], "geometry": []},
            "themeId": "plain",
            "overrides": {"semantic": [], "occurrence": []},
            "diStyles": {"native": [], "bioc": []},
            "importedDi": copy.deepcopy(self.imported_di),
            "selection": [],
            "activePageId": "",
        }

    def _snapshot_payload(self, envelope: DocumentEnvelope) -> dict[str, object]:
        """Build one closed Snapshot/1 wire payload of the committed state."""
        return {
            "snapshotVersion": "1",
            "envelope": envelope.to_json(),
            "presentation": self._presentation(),
            "viewRevision": self._current_view(envelope),
        }

    def _emit(self, event: dict[str, object]) -> None:
        """Deliver one change event to every listener in subscription order."""
        for key in sorted(self._listeners.keys()):
            self._listeners[key](copy.deepcopy(event))

    def _check_mutating(self, operation: str) -> ResultRefused | None:
        """Apply the shared guards of every mutating entry (refusal or None)."""
        if self.disposed:
            return self._refuse_bare(operation, "canvas-disposed")
        if self._state != "idle":
            return self._refuse(operation, "transaction-reentrant")
        if self.envelope is None:
            return self._refuse_bare(operation, "document-not-loaded")
        return None

    def _loaded(self, operation: str) -> DocumentEnvelope | ResultRefused:
        """Return the loaded envelope or the guard refusal (mypy narrowing)."""
        refused = self._check_mutating(operation)
        if refused is not None:
            return refused
        if self.envelope is None:  # pragma: no cover - guarded above
            return self._refuse_bare(operation, "document-not-loaded")
        return self.envelope

    # -- document operations -------------------------------------------------

    def set_definitions(
        self,
        envelope: DocumentEnvelope,
        *,
        expected_revision: str | None = None,
        codec: Callable[[bytes], object] | None = None,
        imported_di: dict[str, object] | None = None,
    ) -> ResultSuccess | ResultRefused:
        """Load one envelope, guarding the expected revision.

        A load starts a new history epoch: undo and redo stacks clear
        (erratum E1). The committed tree is always the DI-free semantic
        projection; presentation extracted from the supplied tree is
        preserved separately as the session DI record. An explicit
        ``imported_di`` record overrides the extracted one.
        """
        _ = codec
        if self.disposed:
            return self._refuse_bare("setDefinitions", "canvas-disposed")
        if self._state != "idle":
            return self._refuse("setDefinitions", "transaction-reentrant")
        shape_valid = isinstance(envelope, DocumentEnvelope) and envelope.document_version == "1"
        argued_identity = dict(envelope.profile_identity) if shape_valid else None
        argued_revision = envelope.semantic_revision if shape_valid else None
        code = validate_envelope(envelope.to_json(), committed=False)
        if code is not None:
            return self._refuse_argument("setDefinitions", code, argued_identity, argued_revision)
        if imported_di is not None:
            code = _check_imported_di(imported_di)
            if code is not None:
                return self._refuse_argument(
                    "setDefinitions", code, argued_identity, argued_revision
                )
        if expected_revision is not None and (
            self.envelope is None or self.envelope.semantic_revision != expected_revision
        ):
            return self._refuse_argument(
                "setDefinitions", "operation-error", argued_identity, argued_revision
            )
        committed = complete_envelope(envelope.profile_identity, envelope.tree, envelope.bindings)
        stored_di = (
            copy.deepcopy(imported_di)
            if imported_di is not None
            else make_imported_di(envelope.tree, "")
        )
        self.envelope = committed
        self.imported_di = stored_di
        self.history.clear()
        self.redo_history.clear()
        self.history_epoch += 1
        report = self._report_success(
            "setDefinitions",
            committed.profile_identity,
            committed.semantic_revision,
            committed.semantic_revision,
        )
        return ResultSuccess(
            operation="setDefinitions",
            profile_identity=dict(committed.profile_identity),
            base_revision=committed.semantic_revision,
            revision=committed.semantic_revision,
            report=report,
            payload={
                "envelope": committed.to_json(),
                "semanticRevision": committed.semantic_revision,
                "viewRevision": self._current_view(committed),
            },
        )

    def _refuse_argument(
        self,
        operation: str,
        code: str,
        identity: dict[str, object] | None,
        revision: str | None,
    ) -> ResultRefused:
        """Build one load refusal echoing the shape-valid argument."""
        report = self._report_refusal(operation, identity, revision)
        return ResultRefused(
            operation=operation,
            code=code,
            diagnostics=tuple(entry.to_json() for entry in report.entries),
            report=report,
            profile_identity=identity,
            base_revision=revision,
        )

    def get_definitions(self) -> ResultSuccess | ResultRefused:
        """Return the loaded envelope or a typed refusal when empty."""
        if self.disposed:
            return self._refuse_bare("getDefinitions", "canvas-disposed")
        if self.envelope is None:
            return self._refuse_bare("getDefinitions", "document-not-loaded")
        envelope = self.envelope
        report = self._report_success(
            "getDefinitions",
            envelope.profile_identity,
            envelope.semantic_revision,
            envelope.semantic_revision,
        )
        return ResultSuccess(
            operation="getDefinitions",
            profile_identity=dict(envelope.profile_identity),
            base_revision=envelope.semantic_revision,
            revision=envelope.semantic_revision,
            report=report,
            payload=envelope.to_json(),
        )

    def activate_business_profile(
        self,
        compiled: CompiledProfile,
        explicit_migration_plan: object = None,
    ) -> ResultSuccess | ResultRefused:
        """Activate one compiled business profile on the loaded envelope."""
        loaded = self._loaded("activateBusinessProfile")
        if isinstance(loaded, ResultRefused):
            return loaded
        if explicit_migration_plan is not None:
            return self._refuse("activateBusinessProfile", "operation-error")
        try:
            identity = compiled_identity(compiled)
        except ValueError:
            return self._refuse("activateBusinessProfile", "operation-error")
        if not self._descriptor_pins_match(identity):
            return self._refuse("activateBusinessProfile", "descriptor-mismatch")
        if loaded.profile_identity != identity:
            # design-default: identity mismatch -> operation-error (DESIGN §4.1;
            # the section-3.3 matrix needs runtime/host inputs the bridge owns).
            return self._refuse("activateBusinessProfile", "operation-error")
        self.compiled = compiled
        self.history.clear()
        self.redo_history.clear()
        self.history_epoch += 1
        report = self._report_success(
            "activateBusinessProfile",
            loaded.profile_identity,
            loaded.semantic_revision,
            loaded.semantic_revision,
        )
        return ResultSuccess(
            operation="activateBusinessProfile",
            profile_identity=dict(loaded.profile_identity),
            base_revision=loaded.semantic_revision,
            revision=loaded.semantic_revision,
            report=report,
            payload={
                "envelope": loaded.to_json(),
                "semanticRevision": loaded.semantic_revision,
                "viewRevision": self._current_view(loaded),
                "historyEpoch": self.history_epoch,
            },
        )

    def _descriptor_pins_match(self, identity: dict[str, object]) -> bool:
        """Compare bridge context pins with compiled descriptor pins."""
        packages = self.descriptor_context.packages if self.descriptor_context is not None else []
        context_pins = sorted(
            [
                (str(entry.get("id")), str(entry.get("version")), str(entry.get("sha256")))
                for entry in packages
                if isinstance(entry, dict)
            ],
            key=lambda triple: triple[0].encode("utf-16-be"),
        )
        compiled_descriptors = identity.get("descriptors")
        profile_pins = sorted(
            [
                (str(entry.get("id")), str(entry.get("version")), str(entry.get("sha256")))
                for entry in (
                    compiled_descriptors if isinstance(compiled_descriptors, list) else []
                )
                if isinstance(entry, dict)
            ],
            key=lambda triple: triple[0].encode("utf-16-be"),
        )
        return context_pins == profile_pins

    def apply_commands(  # noqa: PLR0913, PLR0911 - batch inputs and guards are fixed
        self,
        *,
        base_revision: str,
        expected_view_revision: str,
        commands: object,
        transaction_id: str,
        signal: Callable[[], bool] | None = None,
        codec: Callable[[bytes], object] | None = None,
    ) -> ResultSuccess | ResultRefused:
        """Apply one validated command batch atomically (no partial commit)."""
        _ = codec
        loaded = self._loaded("applyCommands")
        if isinstance(loaded, ResultRefused):
            return loaded
        if (
            self.compiled is None
            or not isinstance(commands, list)
            or not isinstance(base_revision, str)
            or not isinstance(expected_view_revision, str)
            or not isinstance(transaction_id, str)
            or (signal is not None and not callable(signal))
        ):
            return self._refuse("applyCommands", "operation-error")
        current_view = self._current_view(loaded)
        self._state = "staging"
        try:
            staged = run_apply(
                compiled=self.compiled,
                identity=loaded.profile_identity,
                tree=loaded.tree,
                bindings=loaded.bindings,
                base_revision=base_revision,
                expected_view_revision=expected_view_revision,
                current_revision=loaded.semantic_revision,
                current_view=current_view,
                commands=commands,
                transaction_id=transaction_id,
                signal=signal,
                descriptor_types=dict(self.descriptor_context.types)
                if self.descriptor_context is not None
                else {},
                is_disposed=lambda: self.disposed,
            )
        except ApplyError as exc:
            self._state = "idle"
            return self._refuse("applyCommands", exc.code, exc.entries)
        except Exception:  # noqa: BLE001 - rollback stays total
            self._state = "idle"
            return self._refuse("applyCommands", "operation-error")
        if staged is None:
            self._state = "idle"
            return self._noop_result(loaded, current_view, transaction_id)
        if staged.tree == loaded.tree and staged.bindings == loaded.bindings:
            self._state = "idle"
            return self._unchanged_result(loaded, current_view, transaction_id, staged)
        return self._commit_result(loaded, transaction_id, staged)

    def _noop_result(
        self, loaded: DocumentEnvelope, current_view: str, transaction_id: str
    ) -> ResultSuccess:
        """Build the empty-batch no-op success (no C, N or lint ran)."""
        report = self._report_success(
            "applyCommands",
            loaded.profile_identity,
            loaded.semantic_revision,
            loaded.semantic_revision,
        )
        return ResultSuccess(
            operation="applyCommands",
            profile_identity=dict(loaded.profile_identity),
            base_revision=loaded.semantic_revision,
            revision=loaded.semantic_revision,
            report=report,
            payload={
                "envelope": loaded.to_json(),
                "semanticRevision": loaded.semantic_revision,
                "viewRevision": current_view,
                "transactionId": transaction_id,
                "changed": False,
            },
        )

    def _unchanged_result(
        self,
        loaded: DocumentEnvelope,
        current_view: str,
        transaction_id: str,
        staged: StagedResult,
    ) -> ResultSuccess:
        """Build the staged-but-equal success with its correction report."""
        report = Report(
            operation="applyCommands",
            entries=tuple(
                entry
                for entry in (
                    _entry_from_wire(item, "info", "repairable") for item in staged.entries
                )
            ),
            raw_standard_findings=tuple(staged.raw),
            id_map=tuple(staged.id_map),
            artifacts=(),
            source_identity=copy.deepcopy(loaded.profile_identity),
            target_identity=copy.deepcopy(loaded.profile_identity),
            input_revision=loaded.semantic_revision,
            output_revision=loaded.semantic_revision,
        )
        return ResultSuccess(
            operation="applyCommands",
            profile_identity=dict(loaded.profile_identity),
            base_revision=loaded.semantic_revision,
            revision=loaded.semantic_revision,
            report=report,
            payload={
                "envelope": loaded.to_json(),
                "semanticRevision": loaded.semantic_revision,
                "viewRevision": current_view,
                "transactionId": transaction_id,
                "changed": False,
            },
        )

    def _commit_result(
        self, loaded: DocumentEnvelope, transaction_id: str, staged: StagedResult
    ) -> ResultSuccess:
        """Commit one staged batch: one history entry and one change event."""
        committed = DocumentEnvelope(
            document_version="1",
            profile_identity=copy.deepcopy(loaded.profile_identity),
            tree=copy.deepcopy(staged.tree),
            bindings=copy.deepcopy(staged.bindings),
            semantic_revision=staged.revision,
        )
        self._state = "applying"
        self.history.append(
            _HistoryEntry(
                transaction_id=transaction_id,
                envelope=loaded,
                imported_di=copy.deepcopy(self.imported_di),
            )
        )
        self.envelope = committed
        self.redo_history.clear()
        report = Report(
            operation="applyCommands",
            entries=tuple(_entry_from_wire(item, "info", "repairable") for item in staged.entries),
            raw_standard_findings=tuple(staged.raw),
            id_map=tuple(staged.id_map),
            artifacts=(),
            source_identity=copy.deepcopy(loaded.profile_identity),
            target_identity=copy.deepcopy(committed.profile_identity),
            input_revision=loaded.semantic_revision,
            output_revision=committed.semantic_revision,
        )
        new_view = self._current_view(committed)
        payload = {
            "envelope": committed.to_json(),
            "semanticRevision": committed.semantic_revision,
            "viewRevision": new_view,
            "transactionId": transaction_id,
            "changed": True,
        }
        result = ResultSuccess(
            operation="applyCommands",
            profile_identity=dict(committed.profile_identity),
            base_revision=loaded.semantic_revision,
            revision=committed.semantic_revision,
            report=report,
            payload=payload,
        )
        event: dict[str, object] = {
            "envelope": committed.to_json(),
            "semanticRevision": committed.semantic_revision,
            "viewRevision": new_view,
            "transactionId": transaction_id,
            "origin": "command",
            "report": report.to_json(),
        }
        self._state = "idle"
        self._emit(event)
        return result

    def get_snapshot(self) -> ResultSuccess | ResultRefused:
        """Return one closed snapshot for the loaded envelope."""
        if self.disposed:
            return self._refuse_bare("getSnapshot", "canvas-disposed")
        if self.envelope is None:
            return self._refuse_bare("getSnapshot", "document-not-loaded")
        envelope = self.envelope
        report = self._report_success(
            "getSnapshot",
            envelope.profile_identity,
            envelope.semantic_revision,
            envelope.semantic_revision,
        )
        return ResultSuccess(
            operation="getSnapshot",
            profile_identity=dict(envelope.profile_identity),
            base_revision=envelope.semantic_revision,
            revision=envelope.semantic_revision,
            report=report,
            payload=self._snapshot_payload(envelope),
        )

    def undo(
        self, *, expected_revision: str, expected_view_revision: str
    ) -> ResultSuccess | ResultRefused:
        """Restore the stored before-state of the newest history entry."""
        loaded = self._loaded("undo")
        if isinstance(loaded, ResultRefused):
            return loaded
        if (
            not isinstance(expected_revision, str)
            or not isinstance(expected_view_revision, str)
            or expected_revision != loaded.semantic_revision
            or expected_view_revision != self._current_view(loaded)
        ):
            return self._refuse("undo", "operation-error")
        if not self.history:
            return self._refuse("undo", "operation-error")
        self._state = "restoring"
        entry = self.history.pop()
        pre_di = copy.deepcopy(self.imported_di)
        restored = DocumentEnvelope(
            document_version="1",
            profile_identity=copy.deepcopy(entry.envelope.profile_identity),
            tree=copy.deepcopy(entry.envelope.tree),
            bindings=copy.deepcopy(entry.envelope.bindings),
            semantic_revision=entry.envelope.semantic_revision,
        )
        self.envelope = restored
        self.imported_di = copy.deepcopy(entry.imported_di)
        self.redo_history.append(
            _HistoryEntry(
                transaction_id=entry.transaction_id,
                envelope=loaded,
                imported_di=pre_di,
            )
        )
        return self._restored_result("undo", expected_revision, restored, entry, "undo")

    def redo(
        self, *, expected_revision: str, expected_view_revision: str
    ) -> ResultSuccess | ResultRefused:
        """Restore the stored after-state of the newest redo entry."""
        loaded = self._loaded("redo")
        if isinstance(loaded, ResultRefused):
            return loaded
        if (
            not isinstance(expected_revision, str)
            or not isinstance(expected_view_revision, str)
            or expected_revision != loaded.semantic_revision
            or expected_view_revision != self._current_view(loaded)
        ):
            return self._refuse("redo", "operation-error")
        if not self.redo_history:
            return self._refuse("redo", "operation-error")
        self._state = "restoring"
        entry = self.redo_history.pop()
        pre_di = copy.deepcopy(self.imported_di)
        restored = DocumentEnvelope(
            document_version="1",
            profile_identity=copy.deepcopy(entry.envelope.profile_identity),
            tree=copy.deepcopy(entry.envelope.tree),
            bindings=copy.deepcopy(entry.envelope.bindings),
            semantic_revision=entry.envelope.semantic_revision,
        )
        self.envelope = restored
        self.imported_di = copy.deepcopy(entry.imported_di)
        self.history.append(
            _HistoryEntry(
                transaction_id=entry.transaction_id,
                envelope=loaded,
                imported_di=pre_di,
            )
        )
        return self._restored_result("redo", expected_revision, restored, entry, "redo")

    def _restored_result(
        self,
        operation: str,
        expected_revision: str,
        restored: DocumentEnvelope,
        entry: _HistoryEntry,
        origin: str,
    ) -> ResultSuccess:
        """Build one undo/redo restoration result with its change event."""
        report = self._report_success(
            operation,
            restored.profile_identity,
            expected_revision,
            restored.semantic_revision,
        )
        new_view = self._current_view(restored)
        payload = {
            "snapshotVersion": "1",
            "envelope": restored.to_json(),
            "presentation": self._presentation(),
            "viewRevision": new_view,
        }
        result = ResultSuccess(
            operation=operation,
            profile_identity=dict(restored.profile_identity),
            base_revision=expected_revision,
            revision=restored.semantic_revision,
            report=report,
            payload=payload,
        )
        event: dict[str, object] = {
            "envelope": restored.to_json(),
            "semanticRevision": restored.semantic_revision,
            "viewRevision": new_view,
            "transactionId": entry.transaction_id,
            "origin": origin,
            "report": report.to_json(),
        }
        self._state = "idle"
        self._emit(event)
        return result

    def dispose(self) -> PureResult:
        """Dispose this session; later calls refuse as disposed (erratum E4)."""
        self.disposed = True
        return pure_success({"disposed": True})

    # -- read-only queries (lot 5, PureResult) --------------------------------

    def _query_envelope(self) -> DocumentEnvelope | PureResult:
        """Return the loaded envelope or the guard refusal (mypy narrowing)."""
        if self.disposed:
            return pure_refused("canvas-disposed")
        if self.envelope is None:
            return pure_refused("document-not-loaded")
        return self.envelope

    def _wrap_query(self, outcome: PureResult, revision: str) -> PureResult:
        """Inject the committed revision into one query outcome."""
        if isinstance(outcome, PureRefused):
            return outcome
        if not isinstance(outcome.payload, dict):
            return pure_refused("operation-error")
        return _with_revision(outcome.payload, revision)

    def list_entries(
        self,
        *,
        base_revision: str,
        surface: str,
        subject: object = None,
        locale: str,
    ) -> PureResult:
        """List the authorized entries of one surface for a subject."""
        envelope = self._query_envelope()
        if not isinstance(envelope, DocumentEnvelope):
            return envelope
        if not isinstance(base_revision, str) or base_revision != envelope.semantic_revision:
            return pure_refused("operation-error")
        if self.compiled is None:
            return pure_refused("operation-error")
        outcome = _query_list_entries(self.compiled, envelope.tree, surface, subject, locale)
        return self._wrap_query(outcome, envelope.semantic_revision)

    def list_fields(self, *, base_revision: str, target_id: str, locale: str) -> PureResult:
        """List the visible fields of the notions recognizing a target."""
        envelope = self._query_envelope()
        if not isinstance(envelope, DocumentEnvelope):
            return envelope
        if not isinstance(base_revision, str) or base_revision != envelope.semantic_revision:
            return pure_refused("operation-error")
        if self.compiled is None:
            return pure_refused("operation-error")
        outcome = _query_list_fields(self.compiled, envelope.tree, target_id, locale)
        return self._wrap_query(outcome, envelope.semantic_revision)

    def check_field(
        self,
        *,
        base_revision: str,
        target_id: str,
        field_id: str,
        value: object = None,
    ) -> PureResult:
        """Validate one submitted field value without committing."""
        envelope = self._query_envelope()
        if not isinstance(envelope, DocumentEnvelope):
            return envelope
        if not isinstance(base_revision, str) or base_revision != envelope.semantic_revision:
            return pure_refused("operation-error")
        if self.compiled is None:
            return pure_refused("operation-error")
        outcome = _query_check_field(self.compiled, envelope.tree, target_id, field_id, value)
        return self._wrap_query(outcome, envelope.semantic_revision)

    def query_references(  # noqa: PLR0913 - reference query inputs are fixed
        self,
        *,
        base_revision: str,
        target_id: str,
        field_id: str,
        query: str,
        offset: int,
        limit: int,
    ) -> PureResult:
        """List reference candidates of one field with paging."""
        envelope = self._query_envelope()
        if not isinstance(envelope, DocumentEnvelope):
            return envelope
        if self.compiled is None:
            return pure_refused("operation-error")
        outcome = _query_references(
            self.compiled,
            envelope.tree,
            envelope.semantic_revision,
            target_id,
            field_id,
            query,
            offset,
            limit,
            base_revision,
        )
        return self._wrap_query(outcome, envelope.semantic_revision)

    def copy(self, *, base_revision: str, element_ids: object) -> PureResult:
        """Copy requested elements into a canonical pre-order fragment."""
        envelope = self._query_envelope()
        if not isinstance(envelope, DocumentEnvelope):
            return envelope
        if not isinstance(base_revision, str) or base_revision != envelope.semantic_revision:
            return pure_refused("operation-error")
        return copy_fragment(self.compiled, envelope.tree, envelope.semantic_revision, element_ids)

    def on_change(self, listener: object) -> PureResult:
        """Subscribe one change listener; returns its subscription ID."""
        if self.disposed:
            return pure_refused("canvas-disposed")
        if not callable(listener):
            return pure_refused("operation-error")
        self._subscription_counter += 1
        subscription_id = f"sub-{self._subscription_counter}"
        self._listeners[subscription_id] = cast("Callable[[dict[str, object]], None]", listener)
        return pure_success({"subscriptionId": subscription_id})

    def unsubscribe(self, subscription_id: str) -> PureResult:
        """Remove one change listener by subscription ID."""
        if self.disposed:
            return pure_refused("canvas-disposed")
        if subscription_id not in self._listeners:
            return pure_refused("operation-error")
        del self._listeners[subscription_id]
        return pure_success({"unsubscribed": True})


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
