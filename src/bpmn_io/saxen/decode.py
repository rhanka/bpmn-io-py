"""Entity decoding transposed from saxen ``lib/decode.js`` (Lot 3, MIT).

Decodes the five reserved names (plus their UPPERCASE variants — mixed case such as
``&Quot;`` stays literal, as upstream) and decimal/hexadecimal character references.
Unknown named references pass through unchanged. Numeric codes go through the
``String.fromCharCode`` modulo (``chr(code % 0x10000)``), matching upstream even
outside the basic multilingual plane.
"""

from __future__ import annotations

import re

__all__ = ["decode_entities"]

#: ``&#123;`` | ``&#x1af;``/``&#X1af;`` | ``&name;`` — all classes ASCII-only, as
#: upstream (the ``i`` flag folds ``&#X`` and hex digits; ``\\w`` is ASCII there).
_ENTITY_PATTERN = re.compile(r"&#([0-9]+);|&#[xX]([0-9a-fA-F]+);|&([A-Za-z0-9_]+);")

_ENTITY_MAPPING = {
    "amp": "&",
    "apos": "'",
    "gt": ">",
    "lt": "<",
    "quot": '"',
    "AMP": "&",
    "APOS": "'",
    "GT": ">",
    "LT": "<",
    "QUOT": '"',
}


def _replace_entities(match: re.Match[str]) -> str:
    """Replace one entity match, falling back to the literal text."""
    decimal, hex_digits, named = match.group(1, 2, 3)
    if named is not None:
        return _ENTITY_MAPPING.get(named, f"&{named};")
    code = int(decimal) if decimal is not None else int(hex_digits, 16)
    return chr(code % 0x10000)


def decode_entities(s: str) -> str:
    """Decode entities in ``s``, returning it unchanged when there is nothing to do."""
    if len(s) > 3 and "&" in s:
        return _ENTITY_PATTERN.sub(_replace_entities, s)
    return s
