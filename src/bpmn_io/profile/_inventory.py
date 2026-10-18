"""Externalization inventory checks (DESIGN R3.3 §12).

Verifies that the generic profile package carries no vendored business
literals and that distribution members stay within the expected generic set.
Lexicon matching uses hashes only, so guarded words never appear in tracked
bytes; callers supply no business text.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["INVENTORY_HASHES", "scan_paths_for_hashes", "scan_text_for_hashes"]

#: Hash-only lexicon mirroring the repo-wide guard hashes.
INVENTORY_HASHES: frozenset[str] = frozenset(
    {
        "36aa04f4333ebc94260a496b27815226e288d9f946e5eca92362e42c09626290",
        "138a62a1a80d724e866794bf5417ccf20e4c406452c2d4b2ba102fbd2288a30e",
        "d040b14773a422aa0191db4a5ebba83974ef6bc308aeca0aebcf35d73d398252",
        "c8e73184b9b79668836ee7b6ebf7da95b1716c2d03410e11937a7fe45326d677",
        "6ee912f4da943f9aa092e0630a282f4cb60cb152b228b19ae33bab9f4150e046",
        "edf9539d742397cb3c267b7ed30d2e5b3060f999b9512612de63a588f975bfc5",
        "fcb3d245658a5ecf9e75f59050fcc0fd20a92c9eeeb223a99632cd4ef789452c",
        "db66fe349809217e7926360ab81ae6ff26f9816c09a4b362e7dbfd5825b688be",
        "53d8731524013c0d509f1e36af2a69726f60270f88c360d562af794f0bc15fb9",
        "583423608eda0cb63146a67a6ad655858bc511ba6f0d4fd742c0d898b684295a",
        "32ed8e0a3026bc02976abc70f27ddfe1f149b8f4dc5dad00a1451dd7e86e42e9",
    }
)

_IDENTIFIER = re.compile(r"[A-Za-z0-9_]+")
_PART_SPLIT = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")
_BRACKETED = re.compile(r"\[[A-Za-z0-9_]+\]")
_WORD_PAIR = re.compile(r"(?=\b([A-Za-z]+ [A-Za-z]+)\b)")


def _sha256(data: bytes) -> str:
    """Return lowercase hex SHA-256."""
    return hashlib.sha256(data).hexdigest()


def scan_text_for_hashes(text: str, guarded: frozenset[str] = INVENTORY_HASHES) -> list[str]:
    """Scan one text for hashed lexicon hits (first hit per line)."""
    found: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        hits: list[str] = []
        for token in _IDENTIFIER.findall(line):
            parts = [token, *(p for p in _PART_SPLIT.split(token) if p and p != token)]
            hits.extend(
                part
                for part in parts
                if len(part) >= 3 and _sha256(part.lower().encode()) in guarded
            )
        candidates = _BRACKETED.findall(line) + _WORD_PAIR.findall(line)
        hits.extend(c for c in candidates if _sha256(c.lower().encode()) in guarded)
        if hits:
            found.append(f"line {lineno}: {hits[0]!r}")
    return found


def scan_paths_for_hashes(paths: list[Path]) -> list[str]:
    """Scan files for hashed lexicon hits."""
    hits: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_bytes().decode("utf-8", errors="ignore")
        hits.extend(f"{path} {entry}" for entry in scan_text_for_hashes(text))
    return hits
