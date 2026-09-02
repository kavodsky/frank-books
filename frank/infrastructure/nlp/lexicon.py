"""Frequency/dictionary lists shipped in data/ (roadmap 2.2b, 2.4)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from frank.domain.errors import UnknownError
from frank.domain.model.annotation import GlossLists
from frank.domain.model.termbase import AddressCues, Exonym

_REPO_DATA = Path(__file__).resolve().parents[3] / "data"


class FileLexicon:
    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise UnknownError(f"frequency list not found: {path}")
        self._forms = load_forms(path)

    def contains(self, form: str) -> bool:
        return form.casefold() in self._forms


def load_gender_cues(lang: str) -> frozenset[str]:
    path = _REPO_DATA / f"{lang}_gender_cues.txt"
    if not path.is_file():
        raise UnknownError(f"gender-cue list not found: {path}")
    return load_forms(path)


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


def load_address_cues(lang: str) -> AddressCues:
    path = _REPO_DATA / "address_cues.toml"
    if not path.is_file():
        raise UnknownError(f"address-cue list not found: {path}")
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    table = payload.get(lang)
    if not isinstance(table, dict):
        raise UnknownError(f"address cues missing language: {lang}")
    return AddressCues(
        t_lemmas=_string_tuple(table.get("t_lemmas"), "t_lemmas"),
        v_lemmas=_string_tuple(table.get("v_lemmas"), "v_lemmas"),
        v_surfaces=_string_tuple(table.get("v_surfaces"), "v_surfaces"),
        speech_lemmas=_string_tuple(table.get("speech_lemmas"), "speech_lemmas"),
    )


def _string_tuple(raw: object, field: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise UnknownError(f"address cue {field} must be an array")
    found: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = str(item).strip()
        key = value.casefold() if field != "v_surfaces" else value
        if not value or key in seen:
            continue
        seen.add(key)
        found.append(value.casefold() if field != "v_surfaces" else value)
    return tuple(found)


def load_calques() -> tuple[str, ...]:
    path = _REPO_DATA / "uk_calques.toml"
    if not path.is_file():
        raise UnknownError(f"calque list not found: {path}")
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    phrases = payload.get("phrases", [])
    if not isinstance(phrases, list):
        raise UnknownError(f"calque list must be an array: {path}")
    found: list[str] = []
    seen: set[str] = set()
    for item in phrases:
        folded = str(item).casefold().strip()
        if not folded or folded in seen:
            continue
        seen.add(folded)
        found.append(folded)
    return tuple(found)


def exonyms_path() -> Path:
    return _REPO_DATA / "uk_exonyms.toml"


def load_exonyms(path: Path | None = None) -> tuple[Exonym, ...]:
    resolved = exonyms_path() if path is None else path
    if not resolved.is_file():
        raise UnknownError(f"exonym list not found: {resolved}")
    payload = tomllib.loads(resolved.read_text(encoding="utf-8"))
    found: list[Exonym] = []
    seen: set[str] = set()
    for table in ("place", "person"):
        found.extend(_exonyms_from_table(payload.get(table, {}), seen))
    return tuple(found)


def _exonyms_from_table(table: object, seen: set[str]) -> tuple[Exonym, ...]:
    if not isinstance(table, dict):
        raise UnknownError("exonym table must be a map of lemma to Ukrainian")
    found: list[Exonym] = []
    for raw_lemma, raw_uk in table.items():
        lemma = str(raw_lemma).casefold().strip()
        uk = str(raw_uk).strip()
        if not lemma or not uk or lemma in seen:
            continue
        seen.add(lemma)
        found.append(Exonym(lemma=lemma, translation_uk=uk))
    return tuple(found)
