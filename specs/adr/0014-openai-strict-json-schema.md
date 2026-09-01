# ADR 0014 — Structured output must be OpenAI-strict JSON Schema

Date: 2026-08-31. Status: accepted.

## Context
ADR 0009 requires `response_format` with schemas from Pydantic. Live checks on
2026-08-31 (LM Studio `http://127.0.0.1:1234/v1` and an OpenAI-protocol proxy on
`http://127.0.0.1:4000/v1`) showed that `Model.model_json_schema()` is not enough:
Azure-backed chat rejects the schema unless every object has
`additionalProperties: false`. This is the OpenAI structured-output contract, not
a vendor fork.

The same session screened lemma/reunion SMART fitness on
`gold/lemma_disputed.jsonl` (n=4) and `gold/reunion.jsonl` (n=4). This does **not**
replace `frank bench` (chrF/BLEU on translation gold). Model names stay in
`config.toml` only (ADR 0010).

**LM Studio**

| model | json_schema | notes |
|---|---|---|
| `qwen/qwen3.8-27b` | no | JSON in `reasoning_content`, `content` empty → `SchemaInvalid` |
| `google/gemma-4-12b` | yes | DE lemmas match gold; HU lemmas wrong; vote pass produced garbage strings |

**Proxy (unprefixed names only).** `/v1/models` lists many `openai/…` ids; this
key cannot call them. `claude_5_sonnet` reaches Bedrock and rejects
`json_schema` (`output_config.format` extra input). `gpt-5.5` and `gpt-5.6-*`
reject `temperature: 0`. Reasoning chat (`gpt-5`, `o4-mini`, `o3-mini`) with a
small `max_tokens` spends the budget on reasoning and returns empty `content`;
the client does not send `max_tokens`.

Gold with a **strictified** schema (Pydantic schema plus `additionalProperties:
false` on every object). Lemma column is 4/4 for every Azure model that accepted
the schema. Reunion is the discriminator (Hungarian igekötő):

| model | reunion | latency (lemma / reunion) |
|---|---|---|
| `gpt-5.4` | 4/4 | ~2 s / ~2 s |
| `gpt-5.2` | 4/4 | ~2 s / ~2.5 s |
| `gpt-5` | 4/4 | ~5 s / ~18 s |
| `gpt-5.4-mini`, `gpt-4.1-nano` | 3/4 | missed ambiguous `umfahren` (null) |
| `gpt-4.1`, `gpt-4-turbo` | 2/4 | HU → null |
| `gpt-4o`, `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-5.1`, `gpt-5.4-nano` | 1/4 | only `anrufen` |
| `claude_5_sonnet` | — | no `json_schema` |

Without strictifying, **zero** proxy models accepted our current client body.

## Decision
1. Before sending `response_format.json_schema`, make the schema OpenAI-strict:
   `additionalProperties: false` on every object. Still one protocol, still
   Pydantic as the source of fields.
2. Read only `choices[0].message.content`. Empty content is `SchemaInvalid`
   even if JSON sits in `reasoning_content` or inside markdown fences.
3. Do not drop `response_format` for servers that reject it (Bedrock). That
   model is not a SMART candidate until the server speaks the protocol.
4. Keep `temperature: 0`. Models that forbid it are not candidates.
5. If a localhost server requires `Authorization`, the key lives in config (or
   the environment), never in code. Sending a Bearer token is still the OpenAI
   protocol.

## Alternatives rejected
- Parse markdown fences or `reasoning_content`: a second decoder, forbidden by
  ADR 0009.
- Azure/Bedrock-specific request bodies: backend forks.
- Assign FAST/SMART in this ADR: names belong only in config after a real
  `frank bench`.

## Consequences
+ Azure-compatible SMART works once the client strictifies schemas.
− Thinking-local Qwen and Bedrock Claude cannot be SMART today.
− Proxy catalogue ids with an `openai/` prefix are not an allow-list; use the
  short names (`gpt-5.4`, not `openai/gpt-5.4`).
− Tiny 2.2 gold: `gpt-5.4` / `gpt-5.2` are the only reunion-complete Azure
  candidates seen on 2026-08-31; confirm with `frank bench` before pinning.
