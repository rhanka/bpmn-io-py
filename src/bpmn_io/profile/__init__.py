"""Neutral profile mechanism (DESIGN R3.3, binding signatures).

Implements profile loading, compilation and evaluation over the native
moddle tree, canonical bytes, identities, compatibility, envelopes, results,
the headless native bridge and the lint bridge over the literal port.
"""

from __future__ import annotations

from bpmn_io.profile._bridge import HeadlessBridge, create_bridge
from bpmn_io.profile._c14n import digest, digest_bytes, jcs, jcs_bytes

# Lot 3 (recipes, C, supports, import adapters): one contiguous block.
from bpmn_io.profile._cn_apply import apply_plan
from bpmn_io.profile._cn_complete import complete
from bpmn_io.profile._cn_context import Authority, create_read_context
from bpmn_io.profile._cn_gates import GATES
from bpmn_io.profile._cn_normalize import sort_placements
from bpmn_io.profile._cn_plan import plan_recipe
from bpmn_io.profile._compat import check_compatibility
from bpmn_io.profile._compiler import (
    CompiledProfile,
    DescriptorContext,
    RegistrySet,
    compile_profile,
    create_descriptor_context,
)
from bpmn_io.profile._envelope import (
    DocumentEnvelope,
    complete_envelope,
    extract_presentation,
    import_envelope,
    make_imported_di,
    project_semantic,
    sort_bindings,
    validate_bindings,
    validate_envelope,
)
from bpmn_io.profile._evaluate import (
    ElementHandle,
    ReadContext,
    evaluate_predicate,
    select,
)
from bpmn_io.profile._inventory import (
    INVENTORY_HASHES,
    scan_paths_for_hashes,
    scan_text_for_hashes,
)
from bpmn_io.profile._lexical import LexicalError, LexicalOk, check_lexical
from bpmn_io.profile._lint import lint
from bpmn_io.profile._loader import ValidatedProfile, load_profile
from bpmn_io.profile._results import (
    STAGE_ORDER,
    Coordinate,
    PureRefused,
    PureResult,
    PureSuccess,
    Report,
    ReportEntry,
    ResultRefused,
    ResultSuccess,
    escape_pointer,
    make_coordinate,
    make_report,
    pure_refused,
    pure_success,
    result_refused,
    result_success,
    sort_id_map,
    sort_report_entries,
    worst_capability,
)
from bpmn_io.profile._schema import (
    CLOSED_KEYWORDS,
    PATTERN_INVENTORY,
    SchemaRefusal,
    validate,
)
from bpmn_io.profile._stable_id import STABLE_ID_PREFIX, allocate_stable_id
from bpmn_io.profile._unicode_case import (
    UNICODE_VERSION_PIN,
    apply_case,
    lower_full,
    upper_full,
)

__all__ = [  # noqa: RUF022 - lots append contiguous per-lot blocks
    "CLOSED_KEYWORDS",
    "INVENTORY_HASHES",
    "PATTERN_INVENTORY",
    "STABLE_ID_PREFIX",
    "STAGE_ORDER",
    "UNICODE_VERSION_PIN",
    "CompiledProfile",
    "Coordinate",
    "DescriptorContext",
    "DocumentEnvelope",
    "ElementHandle",
    "HeadlessBridge",
    "LexicalError",
    "LexicalOk",
    "PureRefused",
    "PureResult",
    "PureSuccess",
    "ReadContext",
    "RegistrySet",
    "Report",
    "ReportEntry",
    "ResultRefused",
    "ResultSuccess",
    "SchemaRefusal",
    "ValidatedProfile",
    "allocate_stable_id",
    "apply_case",
    "check_compatibility",
    "check_lexical",
    "compile_profile",
    "complete_envelope",
    "create_bridge",
    "create_descriptor_context",
    "digest",
    "digest_bytes",
    "escape_pointer",
    "evaluate_predicate",
    "extract_presentation",
    "import_envelope",
    "jcs",
    "jcs_bytes",
    "lint",
    "load_profile",
    "lower_full",
    "make_coordinate",
    "make_imported_di",
    "make_report",
    "project_semantic",
    "pure_refused",
    "pure_success",
    "result_refused",
    "result_success",
    "scan_paths_for_hashes",
    "scan_text_for_hashes",
    "select",
    "sort_bindings",
    "sort_id_map",
    "sort_report_entries",
    "upper_full",
    "validate",
    "validate_bindings",
    "validate_envelope",
    "worst_capability",
    # Lot 3 (recipes, C, supports, import adapters): one contiguous block.
    "Authority",
    "GATES",
    "apply_plan",
    "complete",
    "create_read_context",
    "plan_recipe",
    "sort_placements",
]
