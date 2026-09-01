"""Merge dialogue T/V observations into AddressPair rows (roadmap 3.4)."""

from __future__ import annotations

from frank.domain.model.termbase import (
    AddressMatrixConfig,
    AddressObservation,
    AddressPair,
    Character,
    TvForm,
    UnresolvedPair,
)


def merge_address_observations(
    book_id: str,
    observations: tuple[AddressObservation, ...],
    characters: tuple[Character, ...],
    config: AddressMatrixConfig,
) -> tuple[tuple[AddressPair, ...], tuple[UnresolvedPair, ...]]:
    """Keep pairs with a consistent T or V; leave unknown form for SMART.

    German: Bumble→Oliver always ``du`` stays T; a later ``Sie`` on the same pair
    becomes MIXED (a plot-level switch). Hungarian ``te`` vs ``ön`` likewise.
    Speaker or addressee missing → drop; literary attribution is not full coverage.
    """
    names = {item.id: item.canonical_name for item in characters}
    grouped = _grouped(observations)
    resolved: list[AddressPair] = []
    unresolved: list[UnresolvedPair] = []
    for (speaker_id, addressee_id), rows in grouped:
        form = _merged_form(rows)
        sentences = _sentences(rows, config.evidence_sentences_per_pair)
        if form is None:
            unresolved.append(
                UnresolvedPair(
                    book_id=book_id,
                    speaker_id=speaker_id,
                    addressee_id=addressee_id,
                    speaker_name=names.get(speaker_id, speaker_id),
                    addressee_name=names.get(addressee_id, addressee_id),
                    sentences=sentences,
                )
            )
            continue
        resolved.append(
            AddressPair(
                book_id=book_id,
                speaker_id=speaker_id,
                addressee_id=addressee_id,
                tv_form=form,
            )
        )
    return tuple(resolved), tuple(unresolved)


def fill_unresolved_mixed(
    book_id: str,
    unresolved: tuple[UnresolvedPair, ...],
    resolved: tuple[AddressPair, ...],
) -> tuple[AddressPair, ...]:
    """Pairs SMART did not answer stay MIXED (roadmap 3.4)."""
    have = {(item.speaker_id, item.addressee_id) for item in resolved}
    extra = [
        AddressPair(
            book_id=book_id,
            speaker_id=item.speaker_id,
            addressee_id=item.addressee_id,
            tv_form=TvForm.MIXED,
        )
        for item in unresolved
        if (item.speaker_id, item.addressee_id) not in have
    ]
    return _sorted(resolved + tuple(extra))


def _grouped(
    observations: tuple[AddressObservation, ...],
) -> tuple[tuple[tuple[str, str], tuple[AddressObservation, ...]], ...]:
    buckets: dict[tuple[str, str], list[AddressObservation]] = {}
    for item in observations:
        if item.speaker_id is None or item.addressee_id is None:
            continue
        if item.speaker_id == item.addressee_id:
            continue
        key = (item.speaker_id, item.addressee_id)
        buckets.setdefault(key, []).append(item)
    return tuple((key, tuple(rows)) for key, rows in sorted(buckets.items()))


def _merged_form(rows: tuple[AddressObservation, ...]) -> TvForm | None:
    forms = {item.tv_form for item in rows if item.tv_form is not None}
    if TvForm.MIXED in forms or (TvForm.T in forms and TvForm.V in forms):
        return TvForm.MIXED
    if len(forms) == 1:
        return next(iter(forms))
    return None


def _sentences(rows: tuple[AddressObservation, ...], limit: int) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()
    for item in rows:
        if item.sentence in seen:
            continue
        seen.add(item.sentence)
        found.append(item.sentence)
        if len(found) >= limit:
            break
    return tuple(found)


def _sorted(pairs: tuple[AddressPair, ...]) -> tuple[AddressPair, ...]:
    return tuple(sorted(pairs, key=lambda item: (item.speaker_id, item.addressee_id)))
