"""TOML codec for the 3.6 review file. Shape only; referential checks live next door."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable

from frank.domain.errors import SchemaInvalid
from frank.domain.model.termbase import (
    Gender,
    ReviewAddressPair,
    ReviewCharacter,
    ReviewDocument,
    ReviewTerm,
    TermKind,
    TvForm,
)

_HEADER = (
    "# frank-books termbase review (roadmap 3.6).\n"
    "# Edit translations, genders, and T/V, then: frank approve <slug> < this-file\n"
)


def render_review_toml(document: ReviewDocument) -> str:
    """Array-of-tables TOML a human can edit in ~15 minutes (ADR 0002)."""
    chunks = [_HEADER]
    chunks.extend(_section("terms", document.terms, _term_lines))
    chunks.extend(_section("characters", document.characters, _character_lines))
    chunks.extend(_section("address_pairs", document.address_pairs, _pair_lines))
    return "".join(chunks)


def load_review_toml(text: str) -> ReviewDocument:
    raw = _loads(text)
    return ReviewDocument(
        terms=tuple(_parse_term(row) for row in _rows(raw.get("terms"), "terms")),
        characters=tuple(
            _parse_character(row) for row in _rows(raw.get("characters"), "characters")
        ),
        address_pairs=tuple(
            _parse_pair(row) for row in _rows(raw.get("address_pairs"), "address_pairs")
        ),
    )


def _section[T](
    name: str, items: tuple[T, ...], lines_for: Callable[[T], list[str]]
) -> list[str]:
    if not items:
        return [f"{name} = []\n"]
    found: list[str] = []
    for item in items:
        found.append(f"[[{name}]]\n")
        found.extend(lines_for(item))
        found.append("\n")
    return found


def _term_lines(item: ReviewTerm) -> list[str]:
    return [
        f"id = {_quote(item.id)}\n",
        f"kind = {_quote(item.kind.value)}\n",
        f"lemma = {_quote(item.lemma)}\n",
        f"translation_uk = {_quote(item.translation_uk)}\n",
        f"note = {_quote(item.note)}\n",
        f"surface_forms = {_quote_list(item.surface_forms)}\n",
    ]


def _character_lines(item: ReviewCharacter) -> list[str]:
    return [
        f"id = {_quote(item.id)}\n",
        f"canonical_name = {_quote(item.canonical_name)}\n",
        f"translation_uk = {_quote(item.translation_uk)}\n",
        f"gender = {_quote(item.gender.value)}\n",
        f"aliases = {_quote_list(item.aliases)}\n",
        f"role_note = {_quote(item.role_note)}\n",
    ]


def _pair_lines(item: ReviewAddressPair) -> list[str]:
    return [
        f"speaker_id = {_quote(item.speaker_id)}\n",
        f"addressee_id = {_quote(item.addressee_id)}\n",
        f"tv_form = {_quote(item.tv_form.value)}\n",
    ]


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _quote_list(values: tuple[str, ...]) -> str:
    inner = ", ".join(_quote(item) for item in values)
    return f"[{inner}]"


def _loads(text: str) -> dict[str, object]:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SchemaInvalid(f"review TOML is invalid: {exc}") from exc
    return dict(raw)


def _rows(raw: object, name: str) -> tuple[object, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise SchemaInvalid(f"{name} must be an array of tables")
    return tuple(raw)


def _parse_term(row: object) -> ReviewTerm:
    return ReviewTerm(
        id=_field(row, "id"),
        kind=_kind(_field(row, "kind")),
        lemma=_field(row, "lemma"),
        translation_uk=_optional(row, "translation_uk"),
        note=_optional(row, "note"),
        surface_forms=_str_tuple(row, "surface_forms"),
    )


def _parse_character(row: object) -> ReviewCharacter:
    return ReviewCharacter(
        id=_field(row, "id"),
        canonical_name=_field(row, "canonical_name"),
        translation_uk=_optional(row, "translation_uk"),
        gender=_gender(_field(row, "gender")),
        aliases=_str_tuple(row, "aliases"),
        role_note=_optional(row, "role_note"),
    )


def _parse_pair(row: object) -> ReviewAddressPair:
    return ReviewAddressPair(
        speaker_id=_field(row, "speaker_id"),
        addressee_id=_field(row, "addressee_id"),
        tv_form=_tv(_field(row, "tv_form")),
    )


def _field(row: object, key: str) -> str:
    text = _optional(row, key)
    if not text:
        raise SchemaInvalid(f"review field {key} is required")
    return text


def _optional(row: object, key: str) -> str:
    mapping = _table(row)
    value = mapping.get(key, "")
    if value is None:
        return ""
    if isinstance(value, str | int | float | bool):
        return str(value).strip()
    raise SchemaInvalid(f"review field {key} must be a string")


def _str_tuple(row: object, key: str) -> tuple[str, ...]:
    mapping = _table(row)
    raw = mapping.get(key, [])
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise SchemaInvalid(f"review field {key} must be an array")
    return tuple(str(item).strip() for item in raw if str(item).strip())


def _table(row: object) -> dict[str, object]:
    if not isinstance(row, dict):
        raise SchemaInvalid("review row must be a table")
    return {str(key): value for key, value in row.items()}


def _kind(value: str) -> TermKind:
    try:
        return TermKind(value)
    except ValueError as exc:
        raise SchemaInvalid(f"unknown kind: {value}") from exc


def _gender(value: str) -> Gender:
    try:
        return Gender(value)
    except ValueError as exc:
        raise SchemaInvalid(f"unknown gender: {value}") from exc


def _tv(value: str) -> TvForm:
    try:
        return TvForm(value)
    except ValueError as exc:
        raise SchemaInvalid(f"unknown tv_form: {value}") from exc
