"""Fill Term.translation_uk from exonyms and SMART renderings (roadmap 3.2)."""

from __future__ import annotations

from frank.domain.model.termbase import Exonym, Term, TermRendering

_EXONYM_NOTE = "конвенційна форма"


def apply_exonyms(
    terms: tuple[Term, ...], exonyms: tuple[Exonym, ...]
) -> tuple[Term, ...]:
    """Use listed conventional forms; never invent Wien → Відень in the LLM.

    German: ``Wien`` / ``München``. Hungarian: ``Duna`` / ``Budapest``.
    """
    by_lemma = {item.lemma.casefold(): item for item in exonyms}
    found: list[Term] = []
    for term in terms:
        hit = by_lemma.get(term.lemma.casefold())
        if hit is None:
            found.append(term)
            continue
        found.append(
            term.model_copy(
                update={"translation_uk": hit.translation_uk, "note": _EXONYM_NOTE}
            )
        )
    return tuple(found)


def untranslated(terms: tuple[Term, ...]) -> tuple[Term, ...]:
    return tuple(item for item in terms if not item.translation_uk.strip())


def apply_renderings(
    terms: tuple[Term, ...], renderings: tuple[TermRendering, ...]
) -> tuple[Term, ...]:
    """Copy SMART/exonym Ukrainian onto matching lemmas; leave approved false."""
    by_lemma = {item.lemma.casefold(): item for item in renderings}
    found: list[Term] = []
    for term in terms:
        hit = by_lemma.get(term.lemma.casefold())
        if hit is None or not hit.translation_uk.strip():
            found.append(term)
            continue
        found.append(
            term.model_copy(
                update={"translation_uk": hit.translation_uk.strip(), "note": hit.note}
            )
        )
    return tuple(found)
