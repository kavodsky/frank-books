"""Frequency/dictionary lists shipped in data/ (roadmap 2.2b)."""

from __future__ import annotations

from pathlib import Path

from frank.domain.errors import UnknownError

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


def load_forms(path: Path) -> frozenset[str]:
    forms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            forms.append(stripped.casefold())
    return frozenset(forms)
