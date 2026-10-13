# CLI

An interactive tester: type sentences, see what each detector found, why each value is kept or dropped,
and what the model would receive.

```sh
ezpiizi              # presidio mode
ezpiizi --tracer         # tracer mode (Presidio + PII-Tracer)
ezpiizi --tracer-alone   # PII-Tracer alone: raw output, every label, no Presidio, no filters
```

`tracer-alone` shows what the model finds before any rule: dates, URLs and secrets too, and untrimmed spans
(`DNI 12345678Z`). Use it to understand a decision of the tracer mode, not to protect data.

Example in tracer mode:

```text
texte[+tracer]> Je suis Amina El Idrissi
  combinaison Presidio + PII-Tracer :
  PERSON   'Amina El Idrissi'   score=0.93  (PII-Tracer)  -> gardé
  PERSON   'Amina El Idrissi'   score=0.85  (spaCy)       -> écarté  PII-Tracer prioritaire
  le modèle voit : Je suis <PERSON_1>
```

## Commands

| Command | Effect |
|---|---|
| `/vault` | show the placeholder ↔ value table built so far |
| `/restore <text>` | show what the customer would see: `/restore Bonjour <PERSON_1>` |
| `/context <message>` | set the previous assistant message (e.g. `/context Quel est votre numéro de CIN ?`) |
| `/mode presidio` / `/mode tracer` / `/mode tracer-alone` | switch detector without restarting |
| `/reset` | empty the vault |
| `/quit` | exit (Ctrl+D works too) |

The vault persists across lines like a conversation: the same name keeps its placeholder. It is also
shared across modes: values found in one mode are replaced in the next by the consistency pass, so run
`/reset` before comparing modes on the same sentence. A line starting
with `{` or `[` is handled as JSON (a tool result): known keys decide without detection.

The first sentence in tracer mode is slow (model warm-up, ~3 s); then a few hundred ms per sentence.
