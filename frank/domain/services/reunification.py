"""Separable-verb and igekötő pairing (roadmap 2.2c)."""

from __future__ import annotations

from frank.domain.model.annotation import Annotation, Token
from frank.domain.model.book import Sentence
from frank.domain.model.reunion import (
    PrefixInventory,
    ReunionCandidate,
    ReunionSource,
    VerbParticle,
)
from frank.domain.ports.linguistics import LemmaLexicon

_DE_PARTICLE_DEPS = frozenset({"svp", "prt", "compound:prt"})
_HU_PARTICLE_DEPS = frozenset({"compound:preverb"})
_NOT_PARTICLE_DEPS = frozenset({"case", "prep", "pm", "mark", "det"})
_PARTICLE_UPOS = frozenset({"PART", "ADV"})
_FEL_FOL = {"fel": "föl", "föl": "fel"}


def reunion_candidates(
    annotation: Annotation,
    inventory: PrefixInventory,
    lexicon: LemmaLexicon,
) -> tuple[ReunionCandidate, ...]:
    """Pair a detached particle with its verb; Hungarian *el tudta olvasni* → *elolvas*.

    German: ``ruft … an`` (dep ``svp``/``prt``, or PART/ADV fallback) → ``anrufen``.
    Hungarian: the preverb attaches to the infinitive, never to the auxiliary.
    """
    found: list[ReunionCandidate] = []
    claimed: set[str] = set()
    for sentence in annotation.sentences:
        tokens = tuple(
            token for token in annotation.tokens if token.sentence_id == sentence.id
        )
        for pair in _pairs(tokens, inventory):
            verb = pair[1]
            if verb.id in claimed:
                continue
            claimed.add(verb.id)
            found.append(_candidate(sentence, pair, inventory, lexicon))
    return tuple(found)


def partition_reunions(
    candidates: tuple[ReunionCandidate, ...],
) -> tuple[tuple[VerbParticle, ...], tuple[ReunionCandidate, ...]]:
    """Lexicon hits are accepted; ambiguous prefixes and OOV go to SMART."""
    accepted: list[VerbParticle] = []
    pending: list[ReunionCandidate] = []
    for item in candidates:
        if item.needs_arbitration:
            pending.append(item)
            continue
        accepted.append(_from_lexicon(item))
    return tuple(accepted), tuple(pending)


def apply_reunions(
    tokens: tuple[Token, ...], particles: tuple[VerbParticle, ...]
) -> tuple[Token, ...]:
    """Write the reunited lemma onto the verb token only."""
    by_verb = {item.verb_token_id: item.reunited_lemma for item in particles}
    return tuple(
        token.model_copy(update={"reunited_lemma": by_verb[token.id]})
        if token.id in by_verb
        else token
        for token in tokens
    )


def _pairs(
    tokens: tuple[Token, ...], inventory: PrefixInventory
) -> tuple[tuple[Token, Token], ...]:
    found: list[tuple[Token, Token]] = []
    for particle in tokens:
        if not _is_particle(particle, inventory):
            continue
        verb = _target_verb(particle, tokens, inventory)
        if verb is None or verb.id == particle.id:
            continue
        found.append((particle, verb))
    return tuple(found)


def _is_particle(token: Token, inventory: PrefixInventory) -> bool:
    if not _inventory_form(token, inventory):
        return False
    if token.dep in _particle_deps(inventory.lang):
        return True
    if token.dep in _NOT_PARTICLE_DEPS:
        return False
    return token.upos in _PARTICLE_UPOS


def _particle_deps(lang: str) -> frozenset[str]:
    if lang == "hu":
        return _HU_PARTICLE_DEPS
    return _DE_PARTICLE_DEPS


def _inventory_form(token: Token, inventory: PrefixInventory) -> str | None:
    for form in (token.lemma.casefold(), token.surface.casefold()):
        if form in inventory.particles:
            return form
    return None


def _target_verb(
    particle: Token, tokens: tuple[Token, ...], inventory: PrefixInventory
) -> Token | None:
    head = _by_index(tokens, particle.head_index)
    if head is not None and _is_auxiliary(head, inventory):
        inf = _pick_infinitive(tokens, particle, inventory)
        if inf is not None:
            return inf
    if head is not None and _is_content_verb(head, inventory):
        return head
    return _fallback_verb(particle, tokens, inventory)


def _fallback_verb(
    particle: Token, tokens: tuple[Token, ...], inventory: PrefixInventory
) -> Token | None:
    inf = _pick_infinitive(tokens, particle, inventory)
    if inf is not None:
        return inf
    verbs = [token for token in tokens if _is_content_verb(token, inventory)]
    before = [token for token in verbs if token.index < particle.index]
    if before:
        return before[-1]
    after = [token for token in verbs if token.index > particle.index]
    return after[0] if after else None


def _pick_infinitive(
    tokens: tuple[Token, ...], particle: Token, inventory: PrefixInventory
) -> Token | None:
    infs = [
        token
        for token in tokens
        if _is_infinitive(token) and not _is_auxiliary(token, inventory)
    ]
    if not infs:
        return None
    return _nearest(infs, particle)


def _is_auxiliary(token: Token, inventory: PrefixInventory) -> bool:
    if token.upos == "AUX":
        return True
    return token.lemma.casefold() in inventory.auxiliaries


def _is_content_verb(token: Token, inventory: PrefixInventory) -> bool:
    return token.upos == "VERB" and not _is_auxiliary(token, inventory)


def _is_infinitive(token: Token) -> bool:
    if token.morph.value_of("VerbForm") == "Inf":
        return True
    return token.upos == "VERB" and token.surface.casefold().endswith("ni")


def _nearest(tokens: list[Token], origin: Token) -> Token:
    return min(tokens, key=lambda item: abs(item.index - origin.index))


def _by_index(tokens: tuple[Token, ...], index: int) -> Token | None:
    if index <= 0:
        return None
    for token in tokens:
        if token.index == index:
            return token
    return None


def _candidate(
    sentence: Sentence,
    pair: tuple[Token, Token],
    inventory: PrefixInventory,
    lexicon: LemmaLexicon,
) -> ReunionCandidate:
    particle, verb = pair
    forms = _proposed_lemmas(particle, verb, inventory)
    known = next((form for form in forms if lexicon.contains(form)), forms[0])
    prefix = _inventory_form(particle, inventory) or particle.surface.casefold()
    needs_llm = prefix in inventory.ambiguous or not lexicon.contains(known)
    return ReunionCandidate(
        sentence_id=sentence.id,
        particle_token_id=particle.id,
        verb_token_id=verb.id,
        example_sentence=sentence.text,
        particle=particle.surface,
        verb=verb.lemma,
        proposed_lemma=known,
        needs_arbitration=needs_llm,
    )


def _proposed_lemmas(
    particle: Token, verb: Token, inventory: PrefixInventory
) -> tuple[str, ...]:
    stem = verb.lemma.casefold()
    found: list[str] = []
    for prefix in _prefix_variants(particle, inventory):
        form = stem if stem.startswith(prefix) else f"{prefix}{stem}"
        if form not in found:
            found.append(form)
    return tuple(found) if found else (stem,)


def _prefix_variants(particle: Token, inventory: PrefixInventory) -> tuple[str, ...]:
    form = _inventory_form(particle, inventory) or particle.surface.casefold()
    other = _FEL_FOL.get(form)
    if other is not None and other in inventory.particles:
        return (form, other)
    return (form,)


def _from_lexicon(item: ReunionCandidate) -> VerbParticle:
    return VerbParticle(
        sentence_id=item.sentence_id,
        particle_token_id=item.particle_token_id,
        verb_token_id=item.verb_token_id,
        reunited_lemma=item.proposed_lemma,
        source=ReunionSource.LEXICON,
    )
