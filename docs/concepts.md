# Concepts

## Placeholders

Each detected value is replaced by a placeholder made of its type and a number: `<PERSON_1>`,
`<MA_IBAN_2>`, `<MA_PHONE_1>`. The LLM can reason with them ("send the RIB to <PERSON_1>") and copy them
into its answer; they are turned back into real values afterwards.

Types pseudonymised (`config.ALL_ENTITIES`):

| Type | Example | Found by |
|---|---|---|
| `PERSON` | Amina El Idrissi | spaCy (presidio), PII-Tracer (tracer) |
| `EMAIL_ADDRESS` | amina@example.ma | Presidio |
| `CREDIT_CARD` | 4532 0151 1283 0366 | Presidio (Luhn), PII-Tracer + typing |
| `MA_IBAN` | MA64 0111 1000 0012 3456 7890 1234 | Presidio (mod-97), PII-Tracer + typing |
| `MA_PHONE` | 06 12 34 56 78, +212 6 12 34 56 78 | Presidio |
| `MA_CIN` | BE123456 | Presidio (with a context word), PII-Tracer + typing |
| `ADDRESS` | 12 rue Ibn Batouta | PII-Tracer (tracer mode only) |
| `ACCOUNT`, `MA_RIB` | other account numbers, 24-digit RIB | PII-Tracer + typing (tracer mode only) |

Locations, organisations and dates are **not** pseudonymised on purpose: masking them hurts the answers
more than it protects ("une agence à Casablanca" must stay readable).

## The vault

`PiiVault` maps placeholders to values for **one conversation**:

```python
vault = PiiVault()
pseudonymise_text("Appelez Karim au 0612345678", vault)   # "Appelez <PERSON_1> au <MA_PHONE_1>"
pseudonymise_text("Karim a rappelé", vault)               # "<PERSON_1> a rappelé"  (same value, same placeholder)
vault.by_placeholder                                      # {"<PERSON_1>": "Karim", "<MA_PHONE_1>": "0612345678"}
```

- **Consistent:** the same value always gets the same placeholder within a vault, and values already in
  the vault are replaced even when the detector misses them in a later message (consistency pass,
  longest values first).
- **Per conversation:** `vault_for(conversation_id)` returns the vault of a conversation (created on first
  use). Never share a vault between customers: placeholders would point to another customer's data.
- **Cached:** each vault caches the pseudonymised version of texts it has already seen, so a long
  conversation re-sent to the LLM at every call is only analysed once per message.
- **Thread-safe** placeholder creation (a lock), since the middleware pseudonymises in a background thread.
- **In memory:** a vault lives as long as the process (see [Limitations](limitations.md)).

## Restoring

`vault.restore(text)` replaces every known placeholder by its value. A placeholder that is **not** in the
vault was invented by the model: it becomes `[information non disponible]`, never something that looks
like data, and a warning is logged.

## Text and JSON

| Function | Input | Behaviour |
|---|---|---|
| `pseudonymise_text(text, vault, context=None)` | free text | detection + replacement |
| `pseudonymise_json(value, vault)` | parsed JSON | walks dicts and lists; known keys decide directly, other strings are analysed as text |
| `pseudonymise_content(content, vault)` | a string | JSON when it parses as an object or a list (tool results), text otherwise |

Known keys (`config.PII_KEYS`) are trusted without detection: `first_name`, `last_name`, `full_name`,
`email`, `phone`, `mobile`, `iban`, `cin`, `card_number`. `name` is deliberately absent: it can be a
company. Values that are already masked upstream (`4532 **** **** 1187`) are left as they are.

## Context

Some values are only recognisable with the previous message: a bare `BE123456` is a CIN after
"Quel est votre numéro de CIN ?". Pass the previous assistant message as context words:

```python
from ezpiizi import context_words
pseudonymise_text("BE123456", vault, context=context_words("Quel est votre numéro de CIN ?"))
# "<MA_CIN_1>"
```

The LangChain middleware does this automatically for each customer message.

## Placeholder-looking text from outside

Text that *looks* like a placeholder but was typed by the user or found in tool data (`<PERSON_1>` in a
message) is neutralised to `‹PERSON_1›` before pseudonymisation (`middleware.neutralise`). Otherwise the
restore step would turn it into a real value of the vault.
