# F7 serialization through the unchanged literal writer, with O1 validation.
"""Serialize native trees to XML (F7) with complete O1/O2 diagnostics.

Every typed and generic string is validated before encoding (lone
surrogates, NUL, forbidden controls, U+FFFE/U+FFFF refuse with
``invalid-xml-character``); the bytes then come from the unchanged
literal writer. First-pass native deltas are frozen per vector, never
normalized away here.
"""

from __future__ import annotations

from typing import Final

from bpmn_io.codec._model import (
    CodecResult,
    Diagnostic,
    NativeElement,
    escape_pointer,
    resolve_limits,
    utf16_len,
)
from bpmn_io.codec.json import _is_generic, _is_native_element
from bpmn_io.codec.xml_boundary import element_target

__all__ = ["is_valid_xml_string", "serialize_xml"]

#: Detail strings stay bounded even for hostile payloads.
_MAX_DETAIL: Final = 4096


def is_valid_xml_string(text: str) -> bool:
    """Return whether ``text`` is encodable (O1 gate).

    Allowed: TAB/LF/CR, ``U+0020..U+007E``, ``U+00A0..U+D7FF``,
    ``U+E000..U+FFFD`` and ``U+10000..U+10FFFF``. Refused: lone
    surrogates, NUL, the remaining C0 controls, DEL, the C1 controls
    ``U+0080..U+009F`` and ``U+FFFE``/``U+FFFF``. The C1/DEL refusal is
    stricter than the XML 1.0 grammar; it is the frozen contract rule.
    """
    for char in text:
        code = ord(char)
        if code in (0x9, 0xA, 0xD):
            continue
        if 0x20 <= code <= 0x7E:
            continue
        if 0xA0 <= code <= 0xD7FF:
            continue
        if 0xE000 <= code <= 0xFFFD:
            continue
        if 0x10000 <= code <= 0x10FFFF:
            continue
        return False
    return True


def _check_o1_string(
    text: str, what: str, path: str | None, target: str | None, out: list[Diagnostic]
) -> None:
    """Append an ``invalid-xml-character`` diagnostic unless ``text`` is clean."""
    if not is_valid_xml_string(text):
        out.append(
            Diagnostic(
                code="invalid-xml-character",
                path=path,
                target=target,
                detail=f"{what} carries characters invalid in XML 1.0"[:_MAX_DETAIL],
            )
        )


class _O1Walk:
    """Bounded pre-encoding string validation (explicit stack)."""

    def __init__(self, limits: dict[str, int]) -> None:
        """Create the walk for ``limits``."""
        self.limits = limits
        self.diagnostics: list[Diagnostic] = []
        self.nodes = 0
        self.seen: set[int] = set()

    def _check_limit_string(self, text: str, what: str, path: str | None) -> None:
        """Enforce the UTF-16 string limit on one serialized string."""
        if utf16_len(text) > self.limits["xml-attr-value-utf16"]:
            self.diagnostics.append(
                Diagnostic(
                    code="xml-attribute-length-limit",
                    path=path,
                    target=None,
                    detail=f"{what} exceeds the UTF-16 string limit",
                )
            )

    def run(self, root: NativeElement) -> None:
        """Validate every string of the tree reachable for serialization."""
        if not _is_native_element(root):
            self.diagnostics.append(
                Diagnostic(
                    code="descriptor-mismatch",
                    path=None,
                    target=None,
                    detail="serialize root is not a native element",
                )
            )
            return
        stack: list[tuple[NativeElement, str]] = [(root, "")]
        while stack:
            element, path = stack.pop()
            if id(element) in self.seen:
                continue
            self.seen.add(id(element))
            if not self._enter(path):
                return
            target = element_target(element)
            prefix = path + "/" if path else "/"
            if _is_generic(element):
                self._check_generic(element, prefix, target, stack)
            else:
                self._check_typed(element, prefix, target, stack)

    def _enter(self, path: str) -> bool:
        """Count one node against element and depth limits; False on trip."""
        self.nodes += 1
        if self.nodes > self.limits["xml-elements"]:
            self.diagnostics.append(
                Diagnostic(
                    code="xml-element-count-limit",
                    path=path or None,
                    target=None,
                    detail=f"node count exceeds {self.limits['xml-elements']}",
                )
            )
            return False
        depth = path.count("/") + 1 if path else 1
        if depth > self.limits["xml-depth"]:
            self.diagnostics.append(
                Diagnostic(
                    code="xml-depth-limit",
                    path=path or None,
                    target=None,
                    detail=f"depth exceeds {self.limits['xml-depth']}",
                )
            )
            return False
        return True

    def _check_generic(
        self,
        element: NativeElement,
        prefix: str,
        target: str | None,
        stack: list[tuple[NativeElement, str]],
    ) -> None:
        """Validate one generic element's member names and strings."""
        for key, value in vars(element).items():
            if key in ("type_", "descriptor_", "model_", "parent_", "attrs_"):
                continue
            where = prefix + escape_pointer(key)
            self._check_limit_string(key, "generic member name", where)
            _check_o1_string(key, "generic member name", where, target, self.diagnostics)
            if isinstance(value, str):
                self._check_limit_string(value, "generic string", where)
                _check_o1_string(value, f"<{key}>", where, target, self.diagnostics)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if _is_native_element(item):
                        stack.append((item, where + "/" + str(index)))

    def _check_typed(
        self,
        element: NativeElement,
        prefix: str,
        target: str | None,
        stack: list[tuple[NativeElement, str]],
    ) -> None:
        """Validate one typed element's values and foreign attributes."""
        raw = vars(element)
        for key, value in raw.items():
            if key in ("type_", "attrs_", "parent_", "model_", "descriptor_"):
                continue
            where = prefix + escape_pointer(key)
            self._check_value(key, value, where, target, stack)
        self._check_foreign_attrs(raw.get("attrs_", {}), prefix, target)

    def _check_value(
        self,
        key: str,
        value: object,
        where: str,
        target: str | None,
        stack: list[tuple[NativeElement, str]],
    ) -> None:
        """Validate one property value, queueing contained children."""
        if isinstance(value, str):
            self._check_limit_string(value, "property value", where)
            _check_o1_string(value, f"<{key}>", where, target, self.diagnostics)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self._check_item(key, item, where + "/" + str(index), target, stack)
        elif _is_native_element(value):
            stack.append((value, where))

    def _check_item(
        self,
        key: str,
        item: object,
        where: str,
        target: str | None,
        stack: list[tuple[NativeElement, str]],
    ) -> None:
        """Validate one collection entry, queueing contained children."""
        if isinstance(item, str):
            self._check_limit_string(item, "property value", where)
            _check_o1_string(item, f"<{key}>", where, target, self.diagnostics)
        elif _is_native_element(item):
            stack.append((item, where))

    def _check_foreign_attrs(self, attrs: object, prefix: str, target: str | None) -> None:
        """Validate one typed element's foreign attribute names and values."""
        if not isinstance(attrs, dict):
            return
        for key, value in attrs.items():
            where = prefix + "$attrs/" + escape_pointer(str(key))
            if isinstance(key, str):
                self._check_limit_string(key, "foreign attribute name", where)
                _check_o1_string(key, "foreign attribute name", where, target, self.diagnostics)
            if isinstance(value, str):
                self._check_limit_string(value, "foreign attribute value", where)
                _check_o1_string(value, "foreign attribute value", where, target, self.diagnostics)


def serialize_xml(
    root: NativeElement,
    *,
    format: bool = False,  # noqa: A002 - public writer option name
    preamble: bool = True,
) -> CodecResult:
    """Serialize a native tree to XML through the unchanged literal writer.

    O1 string validation runs before encoding; every diagnostic carries
    its complete ``(code, path, target, detail)`` tuple (O2). Native
    writer notices map to ``moddle-warning`` (known shape) or
    ``moddle-unmapped-diagnostic`` (fail-closed).
    """
    resolved = resolve_limits(None)
    walk = _O1Walk(resolved)
    walk.run(root)
    if walk.diagnostics:
        return CodecResult(ok=False, value=None, diagnostics=tuple(walk.diagnostics))
    from bpmn_io.moddle_xml.write import to_xml  # noqa: PLC0415

    try:
        result = to_xml(root, format=bool(format), preamble=bool(preamble))
    except Exception as err:  # noqa: BLE001 - writer failures surface as diagnostics
        return CodecResult(
            ok=False,
            value=None,
            diagnostics=(
                Diagnostic(
                    code="xml-invalid",
                    path=None,
                    target=None,
                    detail=f"writer failed: {err}"[:_MAX_DETAIL],
                ),
            ),
        )
    diagnostics: list[Diagnostic] = []
    for notice in result.warnings:
        code = (
            "moddle-warning"
            if "missing namespace information" in notice
            else "moddle-unmapped-diagnostic"
        )
        diagnostics.append(
            Diagnostic(code=code, path=None, target=None, detail=notice[:_MAX_DETAIL])
        )
    return CodecResult(ok=True, value=result.xml, diagnostics=tuple(diagnostics))
