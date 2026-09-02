"""Budgeted PromptContext assembly (roadmap Phase 4)."""

from __future__ import annotations

import pytest

from frank.domain.model.annotation import Morphology, Token
from frank.domain.model.book import Paragraph, ParagraphStatus
from frank.domain.model.context import (
    ContextAssemblyConfig,
    ContextAssemblyRequest,
    ContextSectionName,
    RollingSentence,
)
from frank.domain.model.termbase import (
    AddressPair,
    Character,
    Gender,
    StyleCard,
    Term,
    TermKind,
    TvForm,
)
from frank.domain.services.context_assembly import assemble_context, count_tokens
from frank.domain.services.style_card import render_style_card_markdown

_CFG = ContextAssemblyConfig(
    max_tokens=1800,
    rolling_window_sentences=3,
    scene_brief_sentences=2,
    style_card_digest_lines=5,
)
_INSTRUCTION = (
    "You produce Ilya Frank data for one paragraph. Follow Termbase MUST lines exactly."
)
_SNAPSHOT = """\
You produce Ilya Frank data for one paragraph. Follow Termbase MUST lines exactly.

MUST translate Bumble as Бамбл
MUST translate Oliver as Олівер

Oliver / Олівер (male)
Mr. Bumble / Бамбл (male)
Mr. Bumble → Oliver: T (ти)

Window:
Es war einmal ein armer Mann.
Жив колись бідний чоловік.
Er lebte am Waldrand.
Він жив на узліссі.

Scene:
Містер Бамбл веде Олівера з робітного дому. Хлопець мовчить.

Chapter:
Олівера віддають з робітного дому. Бамбл веде його далі.

# Style card

- **Epoch:** XIX ст.
- **Setting:** Англія, робітні доми
- **Register:** літературна німецька\
"""


def _para(
    *, text: str = "— Willst du mit mir gehen, Oliver?", pid: str = "p1"
) -> Paragraph:
    return Paragraph(
        id=pid,
        chapter_id="c1",
        passage_id="pass1",
        index=1,
        raw_text=text,
        hash="h",
        status=ParagraphStatus.RAW,
    )


def _tok(row: tuple[int, str, str, str], reunited: str | None = None) -> Token:
    index, surface, lemma, upos = row
    return Token(
        id=f"s1-t{index}",
        sentence_id="s1",
        index=index,
        surface=surface,
        lemma=lemma,
        upos=upos,
        morph=Morphology(),
        reunited_lemma=reunited,
    )


def _term(
    lemma: str, uk: str, *surfaces: str, kind: TermKind = TermKind.PERSON
) -> Term:
    forms = surfaces if surfaces else (lemma,)
    return Term(
        id=f"b-{kind.value}-{lemma.casefold()}",
        book_id="b",
        kind=kind,
        surface_forms=forms,
        lemma=lemma,
        translation_uk=uk,
        approved=True,
    )


def _char(name: str, uk: str, cid: str, *aliases: str) -> Character:
    return Character(
        id=cid,
        book_id="b",
        canonical_name=name,
        translation_uk=uk,
        gender=Gender.MALE,
        aliases=aliases,
    )


def _card() -> StyleCard:
    return StyleCard(
        book_id="b",
        epoch="XIX ст.",
        setting="Англія, робітні доми",
        source_register="літературна німецька",
        narration="третя особа, минулий час",
        tone="похмурий",
        directives="глоси сучасною українською",
    )


def _request(**overrides: object) -> ContextAssemblyRequest:
    base = dict(
        paragraph=_para(),
        tokens=(
            _tok((0, "Willst", "wollen", "VERB")),
            _tok((1, "du", "du", "PRON")),
            _tok((2, "Oliver", "Oliver", "PROPN")),
            _tok((3, "Bumble", "Bumble", "PROPN")),
        ),
        terms=(
            _term("Oliver", "Олівер", "Oliver", "Olivers"),
            _term("Bumble", "Бамбл", "Bumble", "Mr. Bumble"),
            _term("London", "Лондон", kind=TermKind.PLACE),
        ),
        characters=(
            _char("Oliver", "Олівер", "c-oliver"),
            _char("Mr. Bumble", "Бамбл", "c-bumble", "Bumble"),
        ),
        address_pairs=(
            AddressPair(
                book_id="b",
                speaker_id="c-bumble",
                addressee_id="c-oliver",
                tv_form=TvForm.T,
            ),
        ),
        rolling_window=(
            RollingSentence(
                source="Es war einmal ein armer Mann.",
                idiomatic_uk="Жив колись бідний чоловік.",
            ),
            RollingSentence(
                source="Er lebte am Waldrand.",
                idiomatic_uk="Він жив на узліссі.",
            ),
        ),
        scene_brief="Містер Бамбл веде Олівера з робітного дому. Хлопець мовчить.",
        chapter_summary="Олівера віддають з робітного дому. Бамбл веде його далі.",
        style_card=_card(),
        task_instruction=_INSTRUCTION,
        config=_CFG,
    )
    base.update(overrides)
    return ContextAssemblyRequest.model_validate(base)


def _text(ctx: object, name: ContextSectionName) -> str:
    for section in ctx.sections:  # type: ignore[attr-defined]
        if section.name is name:
            return section.text
    return ""


@pytest.mark.unit
def test_snapshot_of_assembled_prompt() -> None:
    assert assemble_context(_request()).rendered == _SNAPSHOT


@pytest.mark.unit
def test_same_inputs_are_byte_identical() -> None:
    request = _request()
    assert assemble_context(request).rendered == assemble_context(request).rendered


@pytest.mark.unit
def test_termbase_slice_is_exactly_the_terms_in_the_paragraph() -> None:
    text = _text(assemble_context(_request()), ContextSectionName.TERMBASE_SLICE)
    assert text == ("MUST translate Bumble as Бамбл\nMUST translate Oliver as Олівер")
    assert "London" not in text


@pytest.mark.unit
def test_hungarian_lemma_hits_termbase() -> None:
    ctx = assemble_context(
        _request(
            paragraph=_para(text="Sándor a várban volt."),
            tokens=(
                _tok((0, "Sándor", "Sándor", "PROPN")),
                _tok((1, "várban", "vár", "NOUN")),
            ),
            terms=(
                _term("Sándor", "Шандор"),
                _term("Pest", "Пешт", kind=TermKind.PLACE),
            ),
            characters=(_char("Sándor", "Шандор", "c-sandor"),),
            address_pairs=(),
        )
    )
    assert _text(ctx, ContextSectionName.TERMBASE_SLICE) == (
        "MUST translate Sándor as Шандор"
    )
    assert _text(ctx, ContextSectionName.SPEAKER_CONTEXT) == ""


@pytest.mark.unit
def test_reunited_lemma_and_multiword_surface_match() -> None:
    ctx = assemble_context(
        _request(
            paragraph=_para(text="Er ruft Oliver Twist an."),
            tokens=(
                _tok((0, "ruft", "rufen", "VERB"), reunited="anrufen"),
                _tok((1, "Oliver", "Oliver", "PROPN")),
                _tok((2, "Twist", "Twist", "PROPN")),
                _tok((3, "an", "an", "ADP")),
            ),
            terms=(
                _term("anrufen", "телефонувати", kind=TermKind.DISAMBIG),
                _term("Oliver Twist", "Олівер Твіст", "Oliver Twist"),
            ),
            characters=(),
            address_pairs=(),
        )
    )
    text = _text(ctx, ContextSectionName.TERMBASE_SLICE)
    assert "MUST translate anrufen as телефонувати" in text
    assert "MUST translate Oliver Twist as Олівер Твіст" in text


@pytest.mark.unit
def test_narrative_omits_speaker_context() -> None:
    ctx = assemble_context(_request(paragraph=_para(text="Oliver ging weiter.")))
    assert _text(ctx, ContextSectionName.SPEAKER_CONTEXT) == ""
    assert "MUST translate Oliver as Олівер" in ctx.rendered


@pytest.mark.unit
def test_mixed_address_is_a_scene_directive() -> None:
    ctx = assemble_context(
        _request(
            address_pairs=(
                AddressPair(
                    book_id="b",
                    speaker_id="c-oliver",
                    addressee_id="c-bumble",
                    tv_form=TvForm.MIXED,
                ),
            )
        )
    )
    speaker = _text(ctx, ContextSectionName.SPEAKER_CONTEXT)
    assert "Oliver → Mr. Bumble: MIXED — do not lock T/V; gloss a switch" in speaker


@pytest.mark.unit
def test_chapter_start_has_empty_rolling_window() -> None:
    ctx = assemble_context(_request(rolling_window=()))
    assert _text(ctx, ContextSectionName.ROLLING_WINDOW) == ""
    assert ctx.rolling_window_text == ""


@pytest.mark.unit
def test_rolling_window_keeps_last_n_and_hashes_them() -> None:
    extra = RollingSentence(
        source="Am Morgen stand er auf.",
        idiomatic_uk="Вранці він устав.",
    )
    older = RollingSentence(source="drop me", idiomatic_uk="випаде")
    window = (older, extra) + _request().rolling_window
    ctx = assemble_context(_request(rolling_window=window))
    rolling = _text(ctx, ContextSectionName.ROLLING_WINDOW)
    assert "drop me" not in rolling
    assert "Am Morgen stand er auf." in rolling
    assert ctx.rolling_window_text.startswith("Am Morgen stand er auf.")


@pytest.mark.unit
def test_scene_brief_clamps_to_configured_sentences() -> None:
    ctx = assemble_context(_request(scene_brief="Перша. Друга. Третя. Четверта."))
    assert _text(ctx, ContextSectionName.SCENE_BRIEF) == "Scene:\nПерша. Друга."


@pytest.mark.unit
def test_style_digest_is_first_configured_lines() -> None:
    digest = _text(assemble_context(_request()), ContextSectionName.STYLE_CARD_DIGEST)
    expected = "\n".join(render_style_card_markdown(_card()).splitlines()[:5])
    assert digest == expected
    assert "Directives" not in digest


@pytest.mark.unit
def test_budget_never_exceeded() -> None:
    request = _request()
    for max_tokens in (0, 1, 8, 20, 50, 1800):
        ctx = assemble_context(
            request.model_copy(
                update={"config": _CFG.model_copy(update={"max_tokens": max_tokens})}
            )
        )
        assert ctx.token_count <= max_tokens
        assert ctx.token_count == count_tokens(ctx.rendered)


@pytest.mark.unit
def test_truncation_drops_from_the_bottom() -> None:
    instruction_tokens = count_tokens(_INSTRUCTION)
    ctx = assemble_context(
        _request(config=_CFG.model_copy(update={"max_tokens": instruction_tokens + 4}))
    )
    names = tuple(section.name for section in ctx.sections)
    assert names[0] is ContextSectionName.TASK_INSTRUCTION
    assert ContextSectionName.STYLE_CARD_DIGEST not in names
    assert ContextSectionName.CHAPTER_SUMMARY not in names
    assert "MUST translate" in ctx.rendered
