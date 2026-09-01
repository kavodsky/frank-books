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
    kept = [token for token in sent if not token.is_space]
    index_of = {token.i: index for index, token in enumerate(kept, start=1)}
    return tuple(_parsed_token(token, index_of[token.i], index_of) for token in kept)


def _parsed_token(token: Token, index: int, index_of: dict[int, int]) -> ParsedToken:
    surface = token.text
    lemma = token.lemma_.strip() or surface
    return ParsedToken(
        index=index,
        surface=surface,
        lemma=lemma,
        upos=token.pos_ or "X",
        morph=_morphology(token),
        dep=token.dep_ or "",
        head_index=_head_index(token, index_of),
        ent_type=token.ent_type_ or "",
    )


def _head_index(token: Token, index_of: dict[int, int]) -> int:
    if token.head.i == token.i:
        return 0
    return index_of.get(token.head.i, 0)


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
