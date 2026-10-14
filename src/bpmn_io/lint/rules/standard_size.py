# Transposed from bpmn-io/bpmnlint@de71146 rules/standard-size.js (MIT).
"""Rule: elements must have a standard (default) size."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from bpmn_io._bpmnlint_utils import is_
from bpmn_io._js import UNDEFINED, number_to_string
from bpmn_io.lint.rules.helper import annotate_rule, prop

if TYPE_CHECKING:
    from bpmn_io.lint.test_rule import Reporter
    from bpmn_io.moddle.base import ModdleElement

__all__ = ["factory"]

#: Default element sizes (kept in sync with bpmn-js ``ElementSizeUtil`` upstream).
DEFAULT_SIZES: dict[str, dict[str, float]] = {
    "bpmn:Task": {"width": 100, "height": 80},
    "bpmn:CallActivity": {"width": 100, "height": 80},
    "bpmn:SubProcess": {"width": 100, "height": 80},  # collapsed
    "bpmn:Gateway": {"width": 50, "height": 50},
    "bpmn:Event": {"width": 36, "height": 36},
    "bpmn:DataObjectReference": {"width": 36, "height": 50},
    "bpmn:DataStoreReference": {"width": 50, "height": 50},
    "bpmn:Participant": {"width": 60, "height": 60},  # collapsed breadth (empty pool)
}

#: Element types resolved through the generic size lookup, most specific first.
CHECKED_TYPES = [
    "bpmn:SubProcess",
    "bpmn:CallActivity",
    "bpmn:Task",
    "bpmn:Gateway",
    "bpmn:Event",
    "bpmn:DataObjectReference",
    "bpmn:DataStoreReference",
]


def factory(config: object = None) -> dict[str, Any]:
    """Create the ``standard-size`` rule (upstream rule factory)."""
    sizes: dict[str, Any] = {
        **DEFAULT_SIZES,
        **(config if isinstance(config, dict) else {}),
    }

    def check(node: ModdleElement, reporter: Reporter) -> None:
        # check each shape as we traverse the DI
        if not is_(node, "bpmndi:BPMNShape"):
            return

        element = prop(node, "bpmnElement")
        bounds = prop(node, "bounds")

        # only check shapes with a linked element and proper bounds
        if not element or not _is_valid_bounds(bounds):
            return

        expected = _get_expected_size(element, node, sizes)

        # ignore elements without an expected size or with a malformed config
        if not expected or not isinstance(expected, dict):
            return

        width_mismatch = _is_number(expected.get("width")) and bounds.get("width") != expected.get(
            "width"
        )
        height_mismatch = _is_number(expected.get("height")) and bounds.get(
            "height"
        ) != expected.get(
            "height",
        )

        if not width_mismatch and not height_mismatch:
            return

        reporter.report(element.get("id"), _get_message(expected))

    return annotate_rule("standard-size", {"check": check})


def _get_expected_size(
    element: ModdleElement,
    di: ModdleElement,
    sizes: dict[str, Any],
) -> dict[str, Any] | None:
    # Participant elements (pools) have their own size rule.
    if is_(element, "bpmn:Participant"):
        return _participant_expected_size(element, di, sizes)

    # lanes follow their content
    if is_(element, "bpmn:Lane"):
        return None

    # expanded sub-processes follow their content
    if is_(element, "bpmn:SubProcess") and _is_expanded(di):
        return None

    checked_type = None
    for type_name in CHECKED_TYPES:
        if is_(element, type_name):
            checked_type = type_name
            break

    if not checked_type:
        return None

    expected = sizes.get(checked_type)
    if isinstance(expected, dict):
        return expected
    return expected


def _get_message(expected: dict[str, Any]) -> str:
    if not _is_number(expected.get("height")):
        return f"Element has a non-standard width; expected width of {_num(expected.get('width'))}"

    if not _is_number(expected.get("width")):
        return (
            f"Element has a non-standard height; expected height of {_num(expected.get('height'))}"
        )

    return (
        f"Element has a non-standard size; "
        f"expected {_num(expected.get('width'))}x{_num(expected.get('height'))}"
    )


def _num(value: object) -> str:
    """JS number interpolation (``100`` not ``100.0``)."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return number_to_string(float(value))
    return str(value)


def _is_expanded(di: ModdleElement) -> bool:
    return bool(di) and bool(prop(di, "isExpanded"))


def _is_horizontal(di: ModdleElement) -> bool:
    if not di:
        return True
    value = prop(di, "isHorizontal")
    return value is None or value is UNDEFINED or value is True


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_valid_bounds(bounds: object) -> bool:
    if not bounds:
        return False
    if not is_(bounds, "dc:Bounds"):
        return False
    bounds_element = cast("ModdleElement", bounds)
    return _is_number(bounds_element.get("width")) and _is_number(bounds_element.get("height"))


def _participant_expected_size(
    element: ModdleElement,
    di: ModdleElement,
    sizes: dict[str, Any],
) -> dict[str, Any] | None:
    """Return the expected size for a participant (pool), or ``None``."""
    # A pool with content follows its content.
    if prop(element, "processRef"):
        return None

    horizontal = _is_horizontal(di)

    # Empty pools are only checked for their fixed dimension.
    participant_size = sizes.get("bpmn:Participant") or {}
    if not isinstance(participant_size, dict):
        return None
    value = participant_size.get("height") if horizontal else participant_size.get("width")

    # Ignore missing or malformed configuration.
    if not _is_number(value):
        return None

    return {"height": value} if horizontal else {"width": value}
