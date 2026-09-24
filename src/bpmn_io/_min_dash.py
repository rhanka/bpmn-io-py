"""Literal transposition of the min-dash helpers used downstream (Lot 2).

Covers exactly the helpers imported by the ported libraries (moddle, moddle-xml,
bpmn-moddle, bpmn-auto-layout); see ``docs/naming.md`` § min-dash for the inventory.
Sources: ``tests/upstream/min-dash/lib/{collection,fn,lang,object}.js`` (v5.1.0, MIT).

Semantics follow ``bpmn_io._js``: Python ``None`` is JS ``null`` and the ``UNDEFINED``
singleton is JS ``undefined`` (so ``find`` misses, ``for_each`` completions and ``get``
misses surface as ``UNDEFINED``). ``dict``/``list`` stand in for plain JS objects and
arrays (tuples read as arrays); insertion order is preserved throughout. User callbacks
receive ``(value, key)`` but may declare fewer parameters — extra positional arguments
are dropped, mirroring JavaScript's arity tolerance.

Deviations from upstream (all outside the exercised paths): unhashable ``groupBy``
discriminators are impossible (JS stringifies object keys); ``assign`` ignores
non-mapping sources instead of coercing primitives; ``has``/``pick`` see instance
``__dict__`` (then ``hasattr``) instead of the prototype chain; ``for_each`` iterates a
snapshot; ``bind`` rebinds through ``types.MethodType`` because Python functions have
no dynamic ``this`` (call sites declare the receiver explicitly); numeric-string
array keys must be canonical (``'01'`` is not an index).
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Mapping
from contextlib import suppress
from types import MethodType
from typing import TYPE_CHECKING, Any, TypeVar, cast

from bpmn_io._js import UNDEFINED, UndefinedType, strict_equal

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "assign",
    "bind",
    "filter",
    "find",
    "find_index",
    "for_each",
    "has",
    "is_function",
    "is_object",
    "is_string",
    "map",
    "pick",
    "set",
]

#: Collections ``for_each``/``find``/``filter``/``map`` iterate, mirroring the upstream
#: ``Collection`` typedef (arrays, plain objects, and nil).
Collection = dict[Any, Any] | list[Any] | tuple[Any, ...] | str | None | UndefinedType

_T = TypeVar("_T")
_F = TypeVar("_F", bound="Callable[..., Any]")

_POSITIONAL_KINDS = frozenset(
    {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD},
)


def _adapt(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``fn`` so trailing positional args beyond its arity are dropped.

    JavaScript calls callbacks with a fixed argument list regardless of the declared
    parameters; the wrapper reproduces that tolerance. Functions with ``*args`` or
    defaulted parameters are returned unchanged (a full call always binds).
    """
    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return fn
    if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params):
        return fn
    positional = [p for p in params if p.kind in _POSITIONAL_KINDS]
    if any(p.default is not inspect.Parameter.empty for p in positional):
        return fn
    count = len(positional)

    def call(*args: object) -> object:
        """Invoke ``fn`` with at most ``count`` positional arguments."""
        return fn(*args[:count]) if len(args) > count else fn(*args)

    return call


def _to_matcher(matcher: object) -> Callable[[object, object], object]:
    """Build the ``(value, key)`` predicate for a ``Matcher`` (function or value)."""
    if callable(matcher):
        return _adapt(matcher)
    return lambda val, _key: strict_equal(val, matcher)


def _parse_index_text(text: str) -> int | None:
    """Return the array index for a string key, else ``None`` when not canonical."""
    try:
        num = int(text)
    except ValueError:
        return None
    return num if str(num) == text and num >= 0 else None


def _as_index(key: object, length: int) -> int | None:
    """Return the in-range array index for ``key``, else ``None``.

    Accepts non-negative ``int`` keys and their canonical string form (``'1'`` but not
    ``'01'``), mirroring ``hasOwnProperty`` on arrays.
    """
    num: int | None
    if isinstance(key, bool):
        num = None
    elif isinstance(key, int):
        num = key
    elif isinstance(key, str):
        num = _parse_index_text(key)
    else:
        num = None
    if num is None or not 0 <= num < length:
        return None
    return num


def _write_index(key: object) -> int:
    """Return the writable array index for ``key`` (lists grow to fit)."""
    if isinstance(key, bool):
        msg = f"illegal key type: {_js_typeof(key)}. Key should be of type number or string."
        raise TypeError(msg)
    num = _parse_index_text(key) if isinstance(key, str) else key
    if isinstance(num, int) and num >= 0:
        return num
    if isinstance(key, (int, str)):
        msg = f"illegal key: {key!r} for array target"
    else:
        msg = f"illegal key type: {_js_typeof(key)}. Key should be of type number or string."
    raise TypeError(msg)


def _js_typeof(value: object) -> str:
    """Return the ``typeof`` name used in ``set`` key errors."""
    if value is UNDEFINED:
        return "undefined"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if callable(value):
        return "function"
    return "object"


def _parse_hex(text: str) -> int | float:
    """Parse a hexadecimal literal, returning ``NaN`` when invalid."""
    try:
        return int(text, 16)
    except ValueError:
        return math.nan


def _parse_decimal(text: str) -> float:
    """Parse a decimal literal, returning ``NaN`` when invalid."""
    try:
        return float(text)
    except ValueError:
        return math.nan


def _to_number_str(text: str) -> int | float:
    """Convert a trimmed string with unary-``+`` semantics (``''`` → ``0``)."""
    if text == "":
        return 0
    if "_" in text:
        return math.nan
    lowered = text.lower()
    if lowered in ("infinity", "+infinity"):
        return math.inf
    if lowered == "-infinity":
        return -math.inf
    if lowered.startswith(("0x", "+0x", "-0x")):
        return _parse_hex(text)
    return _parse_decimal(text)


def _to_number(value: object) -> int | float:
    """Return the unary-``+`` conversion used by ``set`` to scaffold arrays.

    Mirrors ``Number(value)`` for the key shapes paths produce (``None`` → ``0``,
    numerics, numeric strings, hex literals); anything else is ``NaN``.
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _to_number_str(value.strip())
    return math.nan


def _prop_dict(target: dict[Any, Any], key: object) -> object:
    """Read one dict property with JS object key coercion, else ``UNDEFINED``."""
    try:
        if key in target:
            return target[key]
    except TypeError:
        return UNDEFINED
    if isinstance(key, int) and not isinstance(key, bool):
        text = str(key)
        if text in target:
            return target[text]
    return UNDEFINED


def _prop(target: object, key: object) -> object:
    """Read one property, returning ``UNDEFINED`` when absent (never raising).

    ``dict`` keys follow JS object coercion (numeric keys read their string form);
    lists/tuples/strings resolve canonical indices; other objects read attributes.
    """
    if isinstance(target, dict):
        return _prop_dict(target, key)
    if isinstance(target, (list, tuple, str)):
        index = _as_index(key, len(target))
        return target[index] if index is not None else UNDEFINED
    if target is None or target is UNDEFINED or not isinstance(key, str):
        return UNDEFINED
    return getattr(target, key, UNDEFINED)


def _assign_key(target: object, key: object, val: object) -> None:
    """Write one property, growing lists with ``UNDEFINED`` holes like upstream."""
    if isinstance(target, dict):
        target[key if isinstance(key, str) else str(key)] = val
    elif isinstance(target, list):
        index = _write_index(key)
        while len(target) <= index:
            target.append(UNDEFINED)
        target[index] = val
    elif isinstance(key, str):
        setattr(target, key, val)
    else:
        msg = f"illegal key: {key!r} for {type(target).__name__} target"
        raise TypeError(msg)


def _delete_key(target: object, key: object) -> None:
    """Delete one property (``set`` with an ``UNDEFINED`` value)."""
    if isinstance(target, dict):
        target.pop(key if isinstance(key, str) else str(key), None)
    elif isinstance(target, list):
        index = _as_index(key, len(target))
        if index is not None:
            target[index] = UNDEFINED
    elif isinstance(key, str):
        with suppress(AttributeError):
            delattr(target, key)


def _is_nil(value: object) -> bool:
    """Return the ``isNil`` predicate (``None`` or ``UNDEFINED``)."""
    return value is None or value is UNDEFINED


def _is_array(value: object) -> bool:
    """Return the ``isArray`` predicate (lists read as arrays, tuples included)."""
    return isinstance(value, (list, tuple))


def _is_defined(value: object) -> bool:
    """Return the ``isDefined`` predicate (anything but ``UNDEFINED``)."""
    return value is not UNDEFINED


def _has_dict(target: dict[Any, Any], key: object) -> bool:
    """Return dict membership, ``False`` for unhashable keys."""
    try:
        return key in target
    except TypeError:
        return False


def has(target: object, key: object) -> bool:
    """Return true when ``target`` owns a property ``key`` (``hasOwnProperty``).

    ``None``/``UNDEFINED`` own nothing; dicts check membership; sequences and strings
    accept the ``length`` property and canonical indices; other objects check instance
    ``__dict__`` first, then ``hasattr``.
    """
    if target is None or target is UNDEFINED:
        return False
    if isinstance(target, dict):
        return _has_dict(target, key)
    if isinstance(target, (list, tuple, str)):
        return key == "length" or _as_index(key, len(target)) is not None
    if not isinstance(key, str):
        return False
    try:
        return key in vars(target)
    except TypeError:
        return hasattr(target, key)


def is_function(obj: object) -> bool:
    """Return the ``isFunction`` predicate (any callable, classes included)."""
    return callable(obj)


def is_object(obj: object) -> bool:
    """Return the ``isObject`` predicate (plain data mappings read as objects)."""
    return isinstance(obj, dict)


def is_string(obj: object) -> bool:
    """Return the ``isString`` predicate."""
    return isinstance(obj, str)


def _pairs(collection: Collection) -> list[tuple[Any, Any]] | None:
    """Snapshot a collection as ``(key, value)`` pairs, else ``None`` when empty-ish."""
    if isinstance(collection, dict):
        return [(key, val) for key, val in list(collection.items()) if has(collection, key)]
    if isinstance(collection, (list, tuple)):
        return list(enumerate(list(collection)))
    if isinstance(collection, str):
        return [(str(idx), val) for idx, val in enumerate(collection)]
    return None


def for_each(collection: Collection, iterator: Callable[..., Any]) -> object:
    """Iterate over a collection; returning ``False`` stops and yields that value.

    Arrays (and tuples) pass numeric indices, objects pass string keys, strings pass
    index strings; ``None``/``UNDEFINED`` iterate nothing. Completing the iteration
    returns ``UNDEFINED``, as upstream.
    """
    if collection is None or collection is UNDEFINED:
        return UNDEFINED
    pairs = _pairs(collection)
    if pairs is None:
        return UNDEFINED
    call = _adapt(iterator)
    for key, val in pairs:
        if call(val, key) is False:
            return val
    return UNDEFINED


def find(collection: Collection, matcher: object) -> object:
    """Return the first element matching ``matcher``, else ``UNDEFINED``."""
    match_fn = _to_matcher(matcher)
    found: list[Any] = [UNDEFINED]

    def visit(val: object, key: object) -> bool | None:
        """Capture the first match and stop the iteration."""
        if match_fn(val, key):
            found[0] = val
            return False
        return None

    for_each(collection, visit)
    return found[0]


def find_index(collection: Collection, matcher: object) -> object:
    """Return the key of the first match: index, property name, or ``UNDEFINED``.

    Arrays start at ``-1`` when nothing matches, mirroring upstream.
    """
    match_fn = _to_matcher(matcher)
    idx: Any = -1 if _is_array(collection) else UNDEFINED

    def visit(val: object, key: object) -> bool | None:
        """Capture the first matching key and stop the iteration."""
        nonlocal idx
        if match_fn(val, key):
            idx = key
            return False
        return None

    for_each(collection, visit)
    return idx


def filter(collection: Collection, matcher: object) -> list[Any]:  # noqa: A001
    """Return the values matching ``matcher`` (always a new list)."""
    match_fn = _to_matcher(matcher)
    result: list[Any] = []

    def visit(val: object, key: object) -> None:
        """Append matching values."""
        if match_fn(val, key):
            result.append(val)

    for_each(collection, visit)
    return result


def map(collection: Collection, fn: Callable[..., Any]) -> list[Any]:  # noqa: A001
    """Transform a collection by piping each member through ``fn``."""
    call = _adapt(fn)
    result: list[Any] = []

    def visit(val: object, key: object) -> None:
        """Append transformed values."""
        result.append(call(val, key))

    for_each(collection, visit)
    return result


def _assign_items(source: object) -> list[tuple[Any, Any]] | None:
    """Return the own entries to copy from ``source``, else ``None`` to skip it."""
    if source is None or source is UNDEFINED:
        return None
    if isinstance(source, Mapping):
        return list(source.items())
    if hasattr(source, "__dict__"):
        return list(vars(source).items())
    # Primitive sources contribute no properties, as with `Object.assign`.
    return None


def assign(target: _T, *others: object) -> _T:
    """Copy own properties of ``others`` onto ``target`` (``Object.assign``)."""
    if target is None or target is UNDEFINED:
        msg = f"assign() requires an object target, got {target!r}"
        raise TypeError(msg)
    for source in others:
        items = _assign_items(source)
        if items is None:
            continue
        if isinstance(target, dict):
            for key, val in items:
                target[key] = val
        else:
            for key, val in items:
                if not isinstance(key, str):
                    msg = f"assign() cannot set non-string key {key!r} on object target"
                    raise TypeError(msg)
                setattr(target, key, val)
    return target


def pick(target: object, properties: Iterable[Any]) -> dict[Any, Any]:
    """Pick properties from ``target`` (inherited ones included, like ``in``)."""
    result: dict[Any, Any] = {}
    if isinstance(target, dict):
        for prop in properties:
            try:
                if prop in target:
                    result[prop] = target[prop]
            except TypeError:
                continue
    else:
        for prop in properties:
            if isinstance(prop, str) and hasattr(target, prop):
                result[prop] = getattr(target, prop)
    return result


def _set_step(
    current: object,
    path: Sequence[Any],
    key: object,
    idx: object,
    value: object,
) -> object:
    """Apply one ``set`` path segment, returning the next current target."""
    if isinstance(key, bool) or not isinstance(key, (int, str)):
        msg = f"illegal key type: {_js_typeof(key)}. Key should be of type number or string."
        raise TypeError(msg)
    if key in {"constructor", "__proto__"}:
        msg = f"illegal key: {key}"
        raise ValueError(msg)
    next_key = path[idx + 1] if isinstance(idx, int) and idx + 1 < len(path) else UNDEFINED
    next_target = _prop(current, key)
    if _is_defined(next_key) and _is_nil(next_target):
        scaffold: Any = [] if not math.isnan(_to_number(next_key)) else {}
        _assign_key(current, key, scaffold)
        next_target = scaffold
    if next_key is UNDEFINED:
        if value is UNDEFINED:
            _delete_key(current, key)
        else:
            _assign_key(current, key, value)
        return current
    return next_target


def set(target: _T, path: list[Any] | tuple[Any, ...], value: object) -> _T:  # noqa: A001
    """Set a nested property, scaffolding ``{}``/``[]`` and deleting on ``UNDEFINED``.

    This mutates ``target`` and returns it. Numeric path segments scaffold arrays
    (grown with ``UNDEFINED`` holes); ``constructor``/``__proto__`` and non
    string/number keys raise, blocking prototype pollution as upstream.
    """
    holder: list[Any] = [target]

    def visit(key: object, idx: object) -> None:
        """Apply one path segment, threading the current target."""
        holder[0] = _set_step(holder[0], path, key, idx, value)

    for_each(path, visit)
    return target


def bind(fn: _F, target: object) -> _F:
    """Bind ``fn`` against ``target`` (the ``this`` receiver).

    Already-bound callables pass through; plain functions become methods of
    ``target``, so ported call sites declare the receiver as their first parameter.
    """
    if hasattr(fn, "__self__"):
        return fn
    return cast("_F", MethodType(fn, target))
