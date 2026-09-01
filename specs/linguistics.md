# Linguistics

Language rules for German→Ukrainian and Hungarian→Ukrainian adaptation. This is
domain knowledge, not code documentation: it is the reasoning behind
`domain/services/` and the prompt templates. Update it whenever a rule is
discovered, changed, or overturned by reading generated output.

Every rule below must have exactly one implementation site (a domain service or a
prompt template) — noted in brackets.

---

## 1. Proper names

**Principle:** transliterate, do not localize; keep one rendering per name for the
whole book (enforced by the termbase, roadmap 3.2). [`prompts/term_translate.j2`;
exonyms applied in `domain/services/term_renderings.py`]

- Localize only where a Ukrainian conventional form exists: `Wien → Відень`,
  `München → Мюнхен`, `Duna → Дунай`. Conventional forms are listed in
  `data/uk_exonyms.toml`; anything not listed is transliterated.
- German: `ei → ай` (Heinrich → Гайнріх), `eu → ой`, `h` after a vowel is dropped
  (`Mahler → Малер`), `ü → ю`, `ö → е/ьо` by position, `sch → ш`, `z → ц`,
  `w → в`, `v → ф` (in German words) — follow current Ukrainian practice, which
  prefers `г` for `h` (`Hans → Ганс`) and `ґ` only where established.
- Hungarian: `s → ш` (Sándor → Шандор), `sz → с`, `cs → ч`, `zs → ж`, `gy → дь`,
  `ny → нь`, `ty → ть`, `ly → й`, `á → а`, `é → е`, `ö/ő → е`, `ü/ű → ю`,
  `j → й`. Hungarian name order is family-first in the source — restore
  given-name-first in Ukrainian narrative text (`Kovács János → Янош Ковач`) but
  keep source order inside a quoted formal address.
- Hungarian case endings must be stripped before transliteration
  (`Budapesten → Budapest → Будапешт`, `Jánosnak → János → Янош`), then Ukrainian
  declension applied. [`domain/services/reunification.py` handles the analogous
  stripping for verbs; name stripping is in term merging, roadmap 3.1]
- Diminutives and alias forms map to the SAME termbase entry with their own
  Ukrainian rendering (`Sanyi` → `Шані`, alias of `Шандор`), never merged away —
  the reader needs to see which form the original used.

## 2. Grammatical gender

Ukrainian past-tense verbs and adjectives are gendered, so every character needs a
gender before generation (roadmap 3.3). Two traps:

- Hungarian has **no grammatical gender and one third-person pronoun (`ő`)**. The
  model cannot infer gender from the sentence — it MUST come from the character
  registry. This is the single largest source of translation errors in HU→UK.
- German grammatical gender ≠ character gender (`das Mädchen` is neuter, the
  character is female). The registry stores the character's gender; the gloss may
  note the source's grammatical gender when it is instructive.

## 3. Address forms (T/V)

[`address_pair` table, roadmap 3.4; enforced in `validation.py`]

- German `du → ти`, `Sie → Ви` (capitalized in Ukrainian when addressing one
  person politely).
- Hungarian is three-way: `te → ти`; `ön → Ви` (formal, distant);
  `maga → Ви` (formal but familiar/regional — gloss the nuance rather than trying
  to encode it in the pronoun); the `tetszik` + infinitive construction
  (`Tetszik tudni?`) is polite deference to an elder — render as `Ви` and gloss
  the construction on first occurrence.
- A switch of address form mid-book is a plot event (intimacy or a quarrel). When
  the address matrix detects a switch, the gloss must mark it, e.g.
  «перейшов на «ти»».

## 4. Separable verbs and igekötő

[`domain/services/reunification.py`, roadmap 2.2c]

- The gloss shows the REUNITED lemma, never the bare stem: `anrufen – телефонувати`,
  not `rufen – кликати`.
- German: note the construction on first occurrence — «відокремлюваний префікс».
- Hungarian igekötő changes aspect and direction, and Ukrainian has prefixes that
  map naturally — exploit this in the gloss: `olvas – читати` vs
  `elolvas – прочитати`; `megír – написати`; `kimegy – вийти`; `bejön – увійти`.
  The gloss must show the aspectual pair, because that is exactly the intuition a
  Ukrainian speaker already has.

## 5. Cases and possessives

- Hungarian case suffixes are glossed by FUNCTION, not by name, on first
  occurrence of each case in the book:
  `-ban/-ben – у (де?)`, `-ba/-be – у (куди?)`, `-ból/-ből – з`,
  `-val/-vel – з (ким/чим)`, `-nak/-nek – (кому)`, `-t – (кого/що)`.
  Ukrainian has cases, so map to the Ukrainian case rather than explaining the
  Hungarian grammar term.
- Hungarian possessive suffixes are highly compressed
  (`házam – мій дім`, `házaim – мої доми`) — always glossed on first occurrence
  of a new possessive pattern.
- German case is mostly carried by articles; gloss the article with its case only
  when it disambiguates something the reader would otherwise misread
  (`dem Mann – чоловікові`).

## 6. Sense units

[`domain/services/segmentation.py`, roadmap 2.3]

A sense unit is a contiguous token span, the Frank interpolation unit. Splitting is
deterministic on the dependency parse (German TIGER-style labels from
`de_core_news_lg`, Hungarian UD from HuSpaCy). No LLM.

- Sentences with ≤ `short_sentence_max_tokens` **non-punctuation** tokens stay one
  unit. ``Es war einmal ein armer Mann.`` (6 content tokens) is never cut.
- Longer sentences split where the owning finite verb changes: subordinates
  (`mo`/`oc`/`rc`, UD `advcl`/`ccomp`/`acl`), coordinations (`cj`/`conj`), and
  relative clauses.   ``Als er aufstand, sah er, dass der Wald still war.`` → three
  units. ``Amikor megérkezett a várba, az őrök kinyitották a kaput.`` → two.
- A German coordinating conjunction (`cd`/`und`) moves onto the following unit.
  Leading commas attach to the preceding unit.
- Leftover spans with no finite verb merge into a neighbour when they are shorter
  than `sense_unit_min_tokens` (``Eine Stadt,`` joins its relative clause).
- Units still longer than `sense_unit_max_tokens` may split off a contiguous heavy
  PP (`mo`/`obl`/`nmod`, at least `heavy_pp_min_tokens` content tokens).
- Infinitival complements stay with their finite governor
  (``die ich nicht bezeichnen will`` is one relative unit).

## 7. Gloss planning

[`domain/services/gloss_planning.py`, roadmap 2.4]

A sequential reading-order pass decides which tokens get a word note later. No LLM.
Keys are the reunited lemma when 2.2c set one (`anrufen`, not `rufen`).

- NEVER: punctuation; the first `function_word_top_n` lemmas of the ranked
  frequency list (`der` / `a` / `az`), except proper names.
- GLOSS `first_occurrence` of a lemma outside `frequency_top_n`. Proper names
  (`PROPN`) gloss on first sight even when the lemma is in that list, and never
  again. If quota drops that first token, the next token of the same lemma retries
  until one gloss is kept.
- GLOSS `reminder` when the last kept gloss of that lemma is at least
  `reminder_gap_sentences` book-level sentence ordinals ago and the lemma occurs
  fewer than `reminder_max_occurrences` times in the book.
- ALWAYS (locked; survive the per-sentence quota): termbase idiom hits; false
  friends from `data/{lang}_false_friends.toml`; first occurrence of a reunited
  separable-verb / igekötő lemma (`morph_trap`); Hungarian tokens whose non-empty
  morph feature-set appears at most `rare_morph_max_count` times in the book
  (first `(lemma, signature)` only).
- Per-sentence quota shrinks with chapter index (`quota_chapter_start` in
  chapter 1 → `quota_last_third` from the last third). Over quota: drop reminders
  first, then the most frequent remaining `first_occurrence`. Books with fewer
  than three chapters keep the start quota.

## 8. Definiteness (Hungarian)

The definite/indefinite conjugation (`olvasok` vs `olvasom`) has no Ukrainian
equivalent and is invisible in translation. Gloss it on first occurrence and then
NEVER again — it is grammar trivia that would clutter every page. [gloss reason
`morph_trap`, quota-limited]

## 9. Word order and the literal layer

The `word_for_word_uk` layer exists to expose the source's structure, so it must
follow source order even when the result is awkward Ukrainian — that awkwardness
is pedagogically the point (see the reference: *просто живу в собственном доме:
«хозяин с жильём собственным»*). Rules:

- `natural_uk` — idiomatic Ukrainian for the sense unit.
- `word_for_word_uk` — source order preserved, in «guillemets», ONLY when it
  differs meaningfully from `natural_uk`; otherwise null.
- German verb-final subordinate clauses and separable-verb frames are the main
  German trigger; Hungarian topic-focus order and heavy pre-modifiers are the main
  Hungarian trigger.

## 10. Register and archaism

- Source archaism is reflected in the ORIGINAL (untouched) and lightly in
  `natural_uk`; glosses and grammar notes are always in plain modern Ukrainian.
  A learner should never have to decode the explanation. [`StyleCard` directive]
- Dialect and sociolect: translate the meaning, and note the register in the gloss
  («просторічно», «діалектне»), rather than substituting a Ukrainian dialect.

## 11. Idioms

- An idiom gets `natural_uk` = the Ukrainian equivalent idiom (if one exists) and
  `word_for_word_uk` = the literal image, because the literal image is what makes
  it memorable. HU `Kutyából nem lesz szalonna` → natural: «горбатого могила
  виправить»; literal: «з собаки не буде сала».
- Idioms are always glossed regardless of quota (roadmap 2.4).

## 12. Russian interference (critical)

Local models drift into Russian on Ukrainian output, especially in long runs, and
partially — a Russian word inside a Ukrainian sentence. Beyond the character-set
check (roadmap 5.2), watch for calques that pass that check:
`получити`, `рахувати` in the sense of "to consider", `приймати участь`,
`співпадати`, `на протязі` (in the temporal sense), `відноситися до`.
Maintain `data/uk_calques.toml` and treat hits as a blocking validation failure.
[`domain/services/validation.py`]

## 13. Passage grouping

[`domain/services/passage_grouping.py`, roadmap 2.5]

The Frank doubling unit is a **passage**: consecutive paragraphs packed to
`min_chars`–`max_chars` of original text. A paragraph is never split; a passage
never crosses a chapter. Generation and caching stay per paragraph.

A run of short dialogue paragraphs stays one passage even when the sum exceeds
`max_chars`, so adapted/unadapted doubling does not cut a conversation in half.
German: `— Guten Tag.` / `— Guten Abend.`. Hungarian: `— Hol vagy?` / `— Itt.`
Conservative opener heuristic: after strip, the paragraph is at most
`dialogue_max_chars` and starts with `— – - « » „ “ " '`. Short non-speech
(`Ja.` / `Igen.`) packs by the ordinary char budget.

## 14. Term candidates

[`domain/services/term_candidates.py`, roadmap 3.1]

Analyzer NER labels become Term kinds: `PER`/`PERSON` → PERSON, `LOC`/`GPE`/`FAC`
→ PLACE, `ORG` → ORG. Consecutive same-kind tokens in one sentence are one
mention (`Oliver Twist`). Variants merge when lemmas match, one is a prefix of
the other (`Budapesten` → `Budapest`, `Olivers` → `Oliver`), or they share a
stem of `merge_min_stem_chars` and Levenshtein distance ≤ `merge_max_edit_distance`.
Nicknames stay apart (`Sanyi` ≠ `Sándor`). PERSON/PLACE/ORG persist only at
`entity_min_occurrences`. High-frequency book lemmas absent from the frequency
lexicon (NOUN/VERB/ADJ) become DISAMBIG. Idiom candidates come from the static
idiom list (empty until lists exist), not from the LLM.

---

## Open questions

Add to this list rather than guessing silently; implement the conservative option
and note it.

- Poetry and verse inside prose: adapt with glosses, or leave untouched with a
  single prose translation? (Conservative: leave the verse intact, one prose
  translation after it, no per-unit splitting.)
- How dense should case-suffix reminders be for Hungarian after chapter 5?
- Should the unadapted passage repeat footnote-like grammar notes? (Conservative:
  no — the unadapted passage is always clean.)
- Hungarian `maga` vs `ön` — is a gloss enough, or is a per-book StyleCard
  directive needed?
- German separable-particle dependency label: roadmap 2.2c says `svp`, tech-stack
  says `prt`. `de_core_news_lg` 3.8 emits `svp` (UPOS `ADP`). Conservative: accept
  `svp`, `prt`, and `compound:prt`.
- Sense-unit length counts non-punctuation tokens. Should a comma-only split
  fire when a unit is still over `sense_unit_max_tokens` after clause and heavy-PP
  cuts? Conservative: leave the oversized unit intact.
- Roadmap 2.4 says morphological traps are ALWAYS glossed (locked, survive quota).
  §8 says Hungarian definiteness is `morph_trap` and quota-limited. Conservative:
  do not special-case `Definite=`; definite conjugation is common, so the rare-morph
  rule does not fire. Reunited-verb and rare-morph traps follow the roadmap ALWAYS.
- If quota drops a `first_occurrence`, is the next token of that lemma still a
  first occurrence? Conservative: yes, until one gloss of that lemma is kept.
- Dialogue-opener heuristic for passage grouping: is a leading hyphen or quote
  enough, or must the paragraph also look like turn-taking (no narrator verb)?
  Conservative: opener + `dialogue_max_chars` only; short `Ja.` / `Igen.` without
  an opener is not a dialogue run.
- spaCy `MISC` (and other unmapped NER labels): keep as terms, or drop? Conservative:
  drop. PERSON/PLACE/ORG only.
- Multiword idiom detection without a list (collocations, noun chunks)? Conservative:
  only phrases already in `GlossLists.idioms` (empty until a committed list exists).
- Does SMART term translation set `approved=true`? Conservative: no — 3.6 is the
  human gate; 3.2 only fills `translation_uk` and `note`.
