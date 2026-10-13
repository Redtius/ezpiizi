# Detection

```python
from ezpiizi import detection, enable_tracer

detection.mode()          # "presidio"
enable_tracer()           # loads PII-Tracer now; detection.mode() == "tracer"
enable_tracer(alone=True) # "tracer-alone": PII-Tracer's raw output, every label, for diagnosis
enable_tracer(False)      # back to presidio
detection.detect(text, context=None)   # -> list of presidio RecognizerResult (type, start, end, score)
detection.detect(text, mode="tracer")  # one call in another mode, the global one unchanged
prepare("tracer")                       # load a mode's detectors without switching to it
```

`enable_tracer()` sets the mode global to the process, used by `pseudonymise_text` when no `mode=` is
given. The LangChain middleware does not use it: it has its own `mode` (default `tracer-alone`, see
[LangChain](langchain.md#choosing-the-detector)). `pseudonymise_text(text, vault, mode=...)` overrides it too.

## presidio mode

Presidio's `AnalyzerEngine` with French spaCy (`fr_core_news_md`) and these recognizers:

| Recognizer | Entity | Rule | Base score |
|---|---|---|---|
| `MoroccanIbanRecognizer` | `MA_IBAN` | `MA` + 26 digits, spaces allowed; a valid mod-97 checksum confirms it (an invalid one stays a candidate: a typo is still personal data) | 0.6 |
| `moroccan_phone` | `MA_PHONE` | `+212` / `00212` / `0`, then 5–7 and 8 digits | 0.6 |
| `moroccan_cin` (letters) | `MA_CIN` | 1–2 letters + 5–6 digits, not after a French article | 0.3 (needs a context word) |
| `moroccan_cin` (digits) | `MA_CIN` | 5–8 digits right after "CIN", "CNI", "carte nationale", "identité" | 0.6 |
| `EmailRecognizer`, `CreditCardRecognizer` | `EMAIL_ADDRESS`, `CREDIT_CARD` | Presidio built-ins (Luhn for cards) | |
| `SpacyRecognizer` | `PERSON` | spaCy NER, then a plausibility filter: a proper noun, no digit | |

Context words ("iban", "rib", "téléphone", "cin", "carte nationale"…) raise the score of a nearby match.
Only results at or above `SCORE_THRESHOLD` (0.5) are kept, and `ALLOW_LIST` values (Casablanca, Visa,
Mastercard… plus your own, see below) are never masked.

## tracer mode

[PII-Tracer](https://huggingface.co/perplexity-ai/PII-Tracer) (Perplexity, MIT) is a bidirectional encoder
that tags names, emails, phones, addresses and account numbers. It runs remote code, so it is always
loaded at the reviewed revision `config.TRACER_REVISION`. Device: CUDA (bf16) > Apple GPU (fp32) > CPU
(fp32), overridable with `EZPIIZI_TRACER_DEVICE` / `EZPIIZI_TRACER_DTYPE`. Texts over ~8,000 characters
are split.

`hybrid.detect_hybrid` combines it with Presidio in six steps:

```text
Presidio ──► structured identifiers kept (IBAN, CIN, phone, email, card)
         └─► spaCy names set aside
PII-Tracer spans
   1 union      Presidio wins every overlap
   2 trim       span cut down to the value: "Mon IBAN est MA64..." -> "MA64..."; titles removed from names
   3 typing     an account number gets its real type by format: MA_IBAN, MA_RIB, CREDIT_CARD, MA_CIN
   4 cross      a weak Presidio match (score < 0.5) confirmed by PII-Tracer is kept;
                a non-name PII-Tracer span below 0.9 with no Presidio support is dropped
   5 filters    your application's identifiers (configure(id_patterns=...)), values already masked (****),
                allow list, names containing digits, imperative verbs ("Rappelle-moi")
   6 spaCy names  kept only where PII-Tracer found nothing at all
Priority on overlaps: Presidio structured identifiers > PII-Tracer > spaCy names
```

Each step can be switched off (`detect_hybrid(text, trim_spans=False, ...)`), which is how the benchmark
measures them (systems H1–H6). `ezpiizi --tracer` shows the decision of every step for a sentence.

## Your application's words and identifiers

Call `configure()` once at startup, before the first message (vaults cache their results):

```python
import ezpiizi

ezpiizi.configure(
    allow=["MyBank", "Assistant"],                         # product, brand, assistant names: never masked
    id_patterns=[r"K\d{4}", r"CLM-\d{4}-\d{4}"],          # your own ids (cards, claims...): never masked
)
```

Without `id_patterns`, an internal reference such as `CLM-2026-0412` may be masked as an account number
by the tracer mode: harmless for privacy, but the model then cannot quote it back.

## Tuning (config.py)

| Setting | Effect |
|---|---|
| `SCORE_THRESHOLD` (0.5) | minimum Presidio score |
| `TRACER_THRESHOLD` (0.5) | minimum PII-Tracer score |
| `TRACER_CONFIRM` (0.9) | below this, a non-name PII-Tracer span needs Presidio support |
| `ALLOW_LIST` | words never masked (places, card brands); extend with `configure(allow=...)` |
| `ID_ALLOW_PATTERNS` | the application's own identifiers, never masked; set with `configure(id_patterns=...)` |
| `PII_KEYS` | JSON keys trusted without detection |
| `ENTITIES` | types Presidio looks for |

When you change a rule, add a case to `tests/` and run the [benchmark](benchmark.md) before and after.
