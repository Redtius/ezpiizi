# Changelog

## 0.1.0 (unreleased)

First public release.

- Two detection modes: `presidio` (Moroccan IBAN with mod-97, CIN, +212 phones, emails, cards, spaCy
  names) and `tracer` (Presidio + PII-Tracer: trimming, typing, cross-confirmation, filters).
- Per-conversation vault with consistent placeholders, JSON-aware pseudonymisation, restore with
  protection against invented placeholders.
- `configure()` for application-specific allow-list words and identifier patterns.
- LangChain `PseudonymisationMiddleware`: pseudonymises every model call, restores answers and tool-call
  arguments, runs detection off the event loop.
- `ezpiizi` interactive CLI and `ezpiizi-bench` benchmark (MAPA, Gretel, custom JSONL).
- `tracer-alone` diagnostic mode (`ezpiizi --tracer-alone`, `enable_tracer(alone=True)`): PII-Tracer's raw
  output with every label (dates, URLs, secrets), no Presidio and no filters.
- Tracer mode keeps identifiers that mix letters and digits (Spanish DNI/NIE, French passport, Italian
  codice fiscale, UK NI number) and completes tokens cut by PII-Tracer (`2345678Z` -> `12345678Z`).
- `PseudonymisationMiddleware(mode=...)`: `"tracer-alone"` (default, PII-Tracer only), `"tracer"` (Presidio +
  PII-Tracer) or `"presidio"`; per middleware, independent of the global mode. `mode=` also on
  `detect()` and `pseudonymise_*()`; `prepare(mode)` loads a mode's detectors at startup; `MODES` lists them.
