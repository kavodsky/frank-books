"""Closed particle lists shipped in data/ (roadmap 2.2c)."""

from __future__ import annotations

from pathlib import Path

from frank.domain.errors import UnknownError
from frank.domain.model.reunion import PrefixInventory
from frank.infrastructure.nlp.lexicon import load_forms

_REPO_DATA = Path(__file__).resolve().parents[3] / "data"
_DE_AUX = frozenset(
    {
        "haben",
        "sein",
        "werden",
        "können",
        "müssen",
        "sollen",
        "wollen",
        "dürfen",
        "mögen",
    }
)
_HU_AUX = frozenset({"tud", "fog", "akar", "kell", "lehet", "szokott"})


def load_inventory(lang: str) -> PrefixInventory:
    if lang == "de":
        return PrefixInventory(
            lang="de",
            particles=_forms("de_separable_prefixes.txt"),
            ambiguous=_forms("de_ambiguous_prefixes.txt"),
            auxiliaries=_DE_AUX,
        )
    if lang == "hu":
        return PrefixInventory(
            lang="hu",
            particles=_forms("hu_igekoto.txt"),
            ambiguous=frozenset(),
            auxiliaries=_HU_AUX,
        )
    raise UnknownError(f"unsupported source language: {lang}")


def _forms(name: str) -> frozenset[str]:
    path = _REPO_DATA / name
    if not path.is_file():
        raise UnknownError(f"prefix list not found: {path}")
    return load_forms(path)
