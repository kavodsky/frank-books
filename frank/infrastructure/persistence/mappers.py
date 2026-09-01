"""Explicit row <-> domain conversions. Boring on purpose."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from frank.domain.errors import ErrorClass
from frank.domain.model.annotation import (
    GlossDecision,
    GlossReason,
    MorphFeature,
    Morphology,
    SenseUnit,
    Token,
)
from frank.domain.model.book import (
    Book,
    BookStatus,
    Chapter,
    Paragraph,
    ParagraphStatus,
    Passage,
    Sentence,
)
from frank.domain.model.lemma import LemmaOverride, LemmaSource
from frank.domain.model.reunion import ReunionSource, VerbParticle
from frank.domain.model.run import Run, RunStatus
from frank.domain.model.termbase import (
    AddressPair,
    Character,
    Gender,
    StyleCard,
    Term,
    TermKind,
    TvForm,
)
from frank.infrastructure.persistence.tables import (
    AddressPairRow,
    BookRow,
    ChapterRow,
    CharacterRow,
    GlossPlanRow,
    LemmaOverrideRow,
    ParagraphRow,
    PassageRow,
    RunRow,
    SenseUnitRow,
    SentenceRow,
    StyleCardRow,
    TermRow,
    TokenRow,
    VerbParticleRow,
)


def run_from_row(row: RunRow) -> Run:
    error_class = None if row.error_class is None else ErrorClass(row.error_class)
    return Run(
        id=row.id,
        book_id=row.book_id,
        started_at=_as_utc(row.started_at),
        ended_at=None if row.ended_at is None else _as_utc(row.ended_at),
        status=RunStatus(row.status),
        passages_done=row.passages_done,
        last_passage_id=row.last_passage_id,
        error_class=error_class,
        error_msg=row.error_msg,
    )


def row_from_run(run: Run) -> RunRow:
    return RunRow(
        id=run.id,
        book_id=run.book_id,
        started_at=run.started_at,
        ended_at=run.ended_at,
        status=run.status.value,
        passages_done=run.passages_done,
        last_passage_id=run.last_passage_id,
        error_class=None if run.error_class is None else run.error_class.value,
        error_msg=run.error_msg,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def book_from_row(row: BookRow) -> Book:
    return Book(
        id=row.id,
        slug=row.slug,
        lang=row.lang,
        title=row.title,
        author=row.author,
        source_url=row.source_url,
        license_note=row.license_note,
        status=BookStatus(row.status),
    )


def row_from_book(book: Book) -> BookRow:
    return BookRow(
        id=book.id,
        slug=book.slug,
        lang=book.lang,
        title=book.title,
        author=book.author,
        source_url=book.source_url,
        license_note=book.license_note,
        status=book.status.value,
    )


def chapter_from_row(row: ChapterRow) -> Chapter:
    return Chapter(
        id=row.id,
        book_id=row.book_id,
        index=row.index,
        title=row.title,
        summary_uk=row.summary_uk,
    )


def row_from_chapter(chapter: Chapter) -> ChapterRow:
    return ChapterRow(
        id=chapter.id,
        book_id=chapter.book_id,
        index=chapter.index,
        title=chapter.title,
        summary_uk=chapter.summary_uk,
    )


def passage_from_row(row: PassageRow) -> Passage:
    return Passage(id=row.id, chapter_id=row.chapter_id, index=row.index)


def row_from_passage(passage: Passage) -> PassageRow:
    return PassageRow(
        id=passage.id,
        chapter_id=passage.chapter_id,
        index=passage.index,
    )


def paragraph_from_row(row: ParagraphRow) -> Paragraph:
    return Paragraph(
        id=row.id,
        chapter_id=row.chapter_id,
        passage_id=row.passage_id,
        index=row.index,
        raw_text=row.raw_text,
        hash=row.hash,
        status=ParagraphStatus(row.status),
    )


def row_from_paragraph(paragraph: Paragraph) -> ParagraphRow:
    return ParagraphRow(
        id=paragraph.id,
        chapter_id=paragraph.chapter_id,
        passage_id=paragraph.passage_id,
        index=paragraph.index,
        raw_text=paragraph.raw_text,
        hash=paragraph.hash,
        status=paragraph.status.value,
    )


def sentence_from_row(row: SentenceRow) -> Sentence:
    return Sentence(
        id=row.id,
        paragraph_id=row.paragraph_id,
        index=row.index,
        text=row.text,
    )


def row_from_sentence(sentence: Sentence) -> SentenceRow:
    return SentenceRow(
        id=sentence.id,
        paragraph_id=sentence.paragraph_id,
        index=sentence.index,
        text=sentence.text,
    )


def token_from_row(row: TokenRow) -> Token:
    return Token(
        id=row.id,
        sentence_id=row.sentence_id,
        index=row.index,
        surface=row.surface,
        lemma=row.lemma,
        upos=row.upos,
        morph=_morph_from_json(row.morph_json),
        dep=row.dep,
        head_index=row.head_index,
        reunited_lemma=row.reunited_lemma,
        ent_type=row.ent_type,
    )


def row_from_token(token: Token) -> TokenRow:
    return TokenRow(
        id=token.id,
        sentence_id=token.sentence_id,
        index=token.index,
        surface=token.surface,
        lemma=token.lemma,
        upos=token.upos,
        morph_json=_morph_to_json(token.morph),
        dep=token.dep,
        head_index=token.head_index,
        reunited_lemma=token.reunited_lemma,
        ent_type=token.ent_type,
    )


def sense_unit_from_row(row: SenseUnitRow) -> SenseUnit:
    return SenseUnit(
        id=row.id,
        sentence_id=row.sentence_id,
        index=row.index,
        start_index=row.start_index,
        end_index=row.end_index,
    )


def row_from_sense_unit(unit: SenseUnit) -> SenseUnitRow:
    return SenseUnitRow(
        id=unit.id,
        sentence_id=unit.sentence_id,
        index=unit.index,
        start_index=unit.start_index,
        end_index=unit.end_index,
    )


def gloss_decision_from_row(row: GlossPlanRow) -> GlossDecision:
    return GlossDecision(
        token_id=row.token_id,
        gloss=row.gloss,
        reason=GlossReason(row.reason),
    )


def row_from_gloss_decision(item: GlossDecision) -> GlossPlanRow:
    return GlossPlanRow(
        token_id=item.token_id,
        gloss=item.gloss,
        reason=item.reason.value,
    )


def _morph_from_json(payload: str) -> Morphology:
    raw = json.loads(payload)
    features = tuple(MorphFeature(key=key, value=str(raw[key])) for key in sorted(raw))
    return Morphology(features=features)


def _morph_to_json(morph: Morphology) -> str:
    mapping = {feature.key: feature.value for feature in morph.features}
    return json.dumps(mapping, ensure_ascii=False, sort_keys=True)


def override_from_row(row: LemmaOverrideRow) -> LemmaOverride:
    return LemmaOverride(
        surface=row.surface,
        upos=row.upos,
        lemma=row.lemma,
        source=LemmaSource(row.source),
    )


def row_from_override(item: LemmaOverride) -> LemmaOverrideRow:
    return LemmaOverrideRow(
        surface=item.surface,
        upos=item.upos,
        lemma=item.lemma,
        source=item.source.value,
    )


def particle_from_row(row: VerbParticleRow) -> VerbParticle:
    return VerbParticle(
        sentence_id=row.sentence_id,
        particle_token_id=row.particle_token_id,
        verb_token_id=row.verb_token_id,
        reunited_lemma=row.reunited_lemma,
        source=ReunionSource(row.source),
    )


def row_from_particle(item: VerbParticle) -> VerbParticleRow:
    return VerbParticleRow(
        sentence_id=item.sentence_id,
        particle_token_id=item.particle_token_id,
        verb_token_id=item.verb_token_id,
        reunited_lemma=item.reunited_lemma,
        source=item.source.value,
    )


def term_from_row(row: TermRow) -> Term:
    surfaces = json.loads(row.surface_forms_json)
    return Term(
        id=row.id,
        book_id=row.book_id,
        kind=TermKind(row.kind),
        surface_forms=tuple(surfaces),
        lemma=row.lemma,
        translation_uk=row.translation_uk,
        note=row.note,
        approved=row.approved,
    )


def row_from_term(term: Term) -> TermRow:
    return TermRow(
        id=term.id,
        book_id=term.book_id,
        kind=term.kind.value,
        surface_forms_json=json.dumps(list(term.surface_forms), ensure_ascii=False),
        lemma=term.lemma,
        translation_uk=term.translation_uk,
        note=term.note,
        approved=term.approved,
    )


def character_from_row(row: CharacterRow) -> Character:
    aliases = json.loads(row.aliases_json)
    return Character(
        id=row.id,
        book_id=row.book_id,
        canonical_name=row.canonical_name,
        translation_uk=row.translation_uk,
        gender=Gender(row.gender),
        aliases=tuple(aliases),
        role_note=row.role_note,
    )


def row_from_character(item: Character) -> CharacterRow:
    return CharacterRow(
        id=item.id,
        book_id=item.book_id,
        canonical_name=item.canonical_name,
        translation_uk=item.translation_uk,
        gender=item.gender.value,
        aliases_json=json.dumps(list(item.aliases), ensure_ascii=False),
        role_note=item.role_note,
    )


def address_pair_from_row(row: AddressPairRow) -> AddressPair:
    return AddressPair(
        book_id=row.book_id,
        speaker_id=row.speaker_id,
        addressee_id=row.addressee_id,
        tv_form=TvForm(row.tv_form),
    )


def row_from_address_pair(item: AddressPair) -> AddressPairRow:
    return AddressPairRow(
        book_id=item.book_id,
        speaker_id=item.speaker_id,
        addressee_id=item.addressee_id,
        tv_form=item.tv_form.value,
    )


def style_card_from_row(row: StyleCardRow) -> StyleCard:
    return StyleCard(
        book_id=row.book_id,
        epoch=row.epoch,
        setting=row.setting,
        source_register=row.source_register,
        narration=row.narration,
        tone=row.tone,
        directives=row.directives,
    )


def row_from_style_card(item: StyleCard) -> StyleCardRow:
    return StyleCardRow(
        book_id=item.book_id,
        epoch=item.epoch,
        setting=item.setting,
        source_register=item.source_register,
        narration=item.narration,
        tone=item.tone,
        directives=item.directives,
    )
