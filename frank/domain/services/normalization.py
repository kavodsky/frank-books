"""Normalize source text before chapter/paragraph splitting (roadmap 1.2)."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from pydantic import BaseModel, ConfigDict

_SOFT_HYPHEN = "\u00ad"
_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}
_DOUBLE_QUOTES = frozenset('"“”„«»')
_SINGLE_QUOTES = frozenset("'‘’‚")
_PAGE_NUMBER = re.compile(r"^\s*\d+\s*$")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_MULTI_SPACE = re.compile(r"[^\S\n]+")
_MULTI_BLANK = re.compile(r"\n{3,}")


class NormalizeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    lang: str
    header_max_chars: int
    header_min_repeats: int


def normalize_text(text: str, config: NormalizeConfig) -> str:
    """NFC, ligatures, hyphenation, quotes, running headers, whitespace.

    German: „Gänsefüßchen“ from mixed "straight" quotes.
    Hungarian: same pair, after stripping a repeated running title.
    """
    nfc = unicodedata.normalize("NFC", text.replace(_SOFT_HYPHEN, ""))
    folded = _replace_ligatures(nfc)
    newlines = folded.replace("\r\n", "\n").replace("\r", "\n")
    joined = _HYPHEN_BREAK.sub(r"\1\2", newlines)
    quoted = _unify_quotes(joined, config.lang)
    without_headers = _drop_running_headers(quoted, config)
    squeezed = _MULTI_SPACE.sub(" ", without_headers)
    return _MULTI_BLANK.sub("\n\n", squeezed).strip() + "\n"


def _replace_ligatures(text: str) -> str:
    out = text
    for src, dst in _LIGATURES.items():
        out = out.replace(src, dst)
    return out


def _unify_quotes(text: str, lang: str) -> str:
    open_dq, close_dq = ("„", "“")
    open_sq, close_sq = ("‚", "‘") if lang == "de" else ("«", "»")
    chars = list(text)
    double_open = True
    single_open = True
    for i, char in enumerate(chars):
        if char in _DOUBLE_QUOTES:
            chars[i] = open_dq if double_open else close_dq
            double_open = not double_open
        elif char in _SINGLE_QUOTES:
            chars[i] = open_sq if single_open else close_sq
            single_open = not single_open
    return "".join(chars)


def _drop_running_headers(text: str, config: NormalizeConfig) -> str:
    lines = text.split("\n")
    counts = Counter(_header_key(line, config.header_max_chars) for line in lines)
    drop = {
        key
        for key, n in counts.items()
        if key is not None and n >= config.header_min_repeats
    }
    kept = [
        line
        for line in lines
        if _header_key(line, config.header_max_chars) not in drop
        and not _PAGE_NUMBER.match(line)
    ]
    return "\n".join(kept)


def _header_key(line: str, max_chars: int) -> str | None:
    stripped = line.strip()
    if stripped == "" or len(stripped) > max_chars:
        return None
    return stripped
