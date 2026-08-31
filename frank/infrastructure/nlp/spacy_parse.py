"""Map a spaCy/HuSpaCy Doc onto ParsedSentence value objects (roadmap 2.2)."""

from __future__ import annotations

from spacy.tokens import Doc, Span, Token

from frank.domain.model.annotation import (
    MorphFeature,
    Morphology,
    ParsedSentence,
    ParsedToken,
)


def parsed_sentences(doc: Doc) -> tuple[ParsedSentence, ...]:
    found: list[ParsedSentence] = []
    index = 1
    for sent in doc.sents:
        text = sent.text.strip()
        if not text:
            continue
        found.append(
            ParsedSentence(
                index=index,
                text=text,
                tokens=_tokens(sent),
            )
        )
        index += 1
    return tuple(found)


def _tokens(sent: Span) -> tuple[ParsedToken, ...]:
    found: list[ParsedToken] = []
    index = 1
    for token in sent:
        if token.is_space:
            continue
        found.append(_parsed_token(token, index))
        index += 1
    return tuple(found)


def _parsed_token(token: Token, index: int) -> ParsedToken:
    surface = token.text
    lemma = token.lemma_.strip() or surface
    return ParsedToken(
        index=index,
        surface=surface,
        lemma=lemma,
        upos=token.pos_ or "X",
        morph=_morphology(token),
    )


def _morphology(token: Token) -> Morphology:
    raw = token.morph.to_dict()
    features = tuple(
        MorphFeature(key=key, value=_feature_value(raw[key])) for key in sorted(raw)
    )
    return Morphology(features=features)


def _feature_value(raw: object) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return ",".join(str(item) for item in raw)
    return str(raw)
