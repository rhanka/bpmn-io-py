# DESIGN R3.3 §6.4 outcome table: adapter refusal and finding codes.
"""Adapter error types for the profile lint bridge.

Each error maps to one unified entry (``ruleId`` ``adapter``,
classification ``integrity``, severity ``error``). Errors raised from the
configuration transform abort the operation (the unified entry carries
disposition ``refused``); evaluation-time failures surface as observed
``lint-rule-error`` entries instead.
"""

from __future__ import annotations

__all__ = [
    "ADAPTER_RULE_ID",
    "ConfigCycleError",
    "ConfigIncompleteError",
    "ConfigUnknownError",
    "ProfileDataError",
    "ProfileLintError",
    "RuleUnknownError",
]

#: Unified ``ruleId`` of every adapter-origin entry (DESIGN R3.3 §6.4 table).
ADAPTER_RULE_ID = "adapter"


class ProfileLintError(Exception):
    """Base error of the profile lint bridge (one unified entry)."""

    code = "lint-rule-error"

    def __init__(self, message: str, *, detail: object = None) -> None:
        """Create the error with a human ``message`` and JSON ``detail``."""
        super().__init__(message)
        self.detail = detail


class ConfigUnknownError(ProfileLintError):
    """An ``extends`` target resolved to nothing (None or thrown lookup)."""

    code = "lint-config-unknown"

    def __init__(self, name: str, *, kind: str = "config") -> None:
        """Create the error for the unknown ``name`` of the given ``kind``."""
        super().__init__(f"unknown {kind} <{name}>", detail={"name": name, "kind": kind})
        self.name = name
        self.kind = kind


class RuleUnknownError(ProfileLintError):
    """A configured rule resolved to nothing (None or thrown lookup)."""

    code = "lint-rule-unknown"

    def __init__(self, name: str) -> None:
        """Create the error for the unknown rule ``name``."""
        super().__init__(f"unknown rule <{name}>", detail={"name": name})
        self.name = name


class ConfigCycleError(ProfileLintError):
    """An ``extends`` chain revisited an active entry (cycle refused)."""

    code = "lint-config-cycle"

    def __init__(self, cycle: list[str]) -> None:
        """Create the error with the active-stack ``cycle`` (written order)."""
        super().__init__(f"extends cycle: {' -> '.join(cycle)}", detail={"cycle": list(cycle)})
        self.cycle = list(cycle)


class ConfigIncompleteError(ProfileLintError):
    """The flattened table cannot satisfy a current-stage rule or coverage."""

    code = "lint-config-incomplete"

    def __init__(self, message: str, *, detail: object = None) -> None:
        """Create the error with a human ``message`` and JSON ``detail``."""
        super().__init__(message, detail=detail)


class ProfileDataError(ProfileLintError):
    """Profile authoring data violates the closed lint-consumed shapes."""

    code = "profile-schema"
