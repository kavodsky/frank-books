"""Frequency/dictionary lists shipped in data/ (roadmap 2.2b, 2.4)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from frank.domain.errors import UnknownError
from frank.domain.model.annotation import GlossLists

_REPO_DATA = Path(__file__).resolve().parents[3] / "data"


class FileLexicon:
    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise UnknownError(f"frequency list not found: {path}")
        self._forms = load_forms(path)

    def contains(self, form: str) -> bool:
        return form.casefold() in self._forms


def lexicon_path(lang: str) -> Path:
    return _REPO_DATA / f"{lang}_frequency_top.txt"


def false_friends_path(lang: str) -> Path:
    return _REPO_DATA / f"{lang}_false_friends.toml"


def load_gloss_lists(lang: str) -> GlossLists:
    ranked = load_ranked(lexicon_path(lang))
    friends = load_false_friends(false_friends_path(lang))
    return GlossLists(ranked=ranked, false_friends=friends, idioms=())


def load_forms(path: Path) -> frozenset[str]:
    return frozenset(load_ranked(path))


def load_ranked(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        raise UnknownError(f"frequency list not found: {path}")
    forms: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        folded = stripped.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        forms.append(folded)
    return tuple(forms)


def load_false_friends(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        raise UnknownError(f"false-friend list not found: {path}")
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    lemmas = payload.get("lemmas", [])
    if not isinstance(lemmas, list):
        raise UnknownError(f"false-friend list must be an array: {path}")
    found: list[str] = []
    seen: set[str] = set()
    for item in lemmas:
        folded = str(item).casefold()
        if not folded or folded in seen:
            continue
        seen.add(folded)
        found.append(folded)
    return tuple(found)
