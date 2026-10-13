# ezpiizi

[![PyPI](https://img.shields.io/pypi/v/ezpiizi)](https://pypi.org/project/ezpiizi/)
[![Python](https://img.shields.io/pypi/pyversions/ezpiizi)](https://pypi.org/project/ezpiizi/)
[![CI](https://github.com/redtius/ezpiizi/actions/workflows/ci.yml/badge.svg)](https://github.com/redtius/ezpiizi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/redtius/ezpiizi/blob/main/LICENSE)

Reversible PII pseudonymisation for French / Moroccan banking assistants. The LLM only ever sees
placeholders (`<PERSON_1>`, `<MA_IBAN_1>`); tools, storage and the customer keep the real values.

```text
"Je suis Amina El Idrissi, mon IBAN est MA64 0111 1000 0012 3456 7890 1234"
        │ pseudonymise_text (vault of this conversation)
        ▼
"Je suis <PERSON_1>, mon IBAN est <MA_IBAN_1>"   ──► LLM ──► "Bonjour <PERSON_1>, ..."
                                                                   │ vault.restore
                                                                   ▼
                                                     "Bonjour Amina El Idrissi, ..."
```

## Detection modes

| Mode | What runs | When to use |
|---|---|---|
| `presidio` (default) | Presidio: Moroccan IBAN (mod-97), CIN, +212 phones, emails, cards (Luhn), spaCy names | tests, machines without a GPU, latency-critical paths |
| `tracer` | Presidio + [PII-Tracer](https://huggingface.co/perplexity-ai/PII-Tracer), combined with trimming, typing, cross-confirmation and filters | production: much better on names, addresses and account numbers |
| `tracer-alone` | PII-Tracer's raw output, every label (dates, URLs, secrets too), no Presidio, no filters | diagnosis: see what the model finds; not for production |

## Install

```sh
pip install ezpiizi                          # presidio mode
pip install "ezpiizi[tracer,langchain]"      # + PII-Tracer and the LangChain middleware
python -m spacy download fr_core_news_md     # French spaCy model (required, not on PyPI)
```

| Extra | Adds |
|---|---|
| `tracer` | `torch` + `transformers`: PII-Tracer (~1.2 GB, downloaded from Hugging Face on first use, pinned revision) |
| `langchain` | the LangChain middleware |
| `bench` | the benchmark datasets loaders |

For development: `pip install -e ".[tracer,langchain,bench,dev]"`.

## Quick start

```python
from ezpiizi import PiiVault, configure, enable_tracer, pseudonymise_text

configure(allow=["MyBank"], id_patterns=[r"CLM-\d{4}-\d{4}"])   # optional: your names and ids, never masked
enable_tracer()                       # optional: tracer mode (loads the model now)
vault = PiiVault()                    # one per conversation
safe = pseudonymise_text("Je suis Amina El Idrissi, tél 0612345678", vault)
# "Je suis <PERSON_1>, tél <MA_PHONE_1>"
vault.restore("Bonjour <PERSON_1>")   # "Bonjour Amina El Idrissi"
```

In a LangChain agent:

```python
from ezpiizi.middleware import PseudonymisationMiddleware

agent = create_agent(model, tools, middleware=[PseudonymisationMiddleware()], context_schema=Context)
# Context needs a `conversation_id`: it selects the vault.
# Detector: PII-Tracer only by default; mode="tracer" for Presidio + PII-Tracer, mode="presidio" without model.
```

Try it interactively:

```sh
ezpiizi --tracer            # or --tracer-alone to see PII-Tracer's raw output
```

## Documentation

| Page | Read it to |
|---|---|
| [Concepts](https://github.com/redtius/ezpiizi/blob/main/docs/concepts.md) | understand placeholders, the vault, restoring, JSON tool results and context |
| [Detection](https://github.com/redtius/ezpiizi/blob/main/docs/detection.md) | know what is detected, how the two modes work, and how to tune them |
| [LangChain integration](https://github.com/redtius/ezpiizi/blob/main/docs/langchain.md) | wire the middleware into an agent, and protect LLM calls made outside it |
| [CLI](https://github.com/redtius/ezpiizi/blob/main/docs/cli.md) | test sentences interactively and see why each value is kept or dropped |
| [Benchmark](https://github.com/redtius/ezpiizi/blob/main/docs/benchmark.md) | measure detection on MAPA, Gretel or your own sentences |
| [Limitations](https://github.com/redtius/ezpiizi/blob/main/docs/limitations.md) | know the false positives, what is *not* protected, and the performance envelope |

## Layout

```text
src/ezpiizi/
  config.py        entities, thresholds, allow lists, model ids
  recognizers.py   Moroccan IBAN / CIN / phone recognizers for Presidio
  detection.py     presidio mode, mode switch (enable_tracer), detect()
  tracer.py        PII-Tracer loading (pinned revision) and inference
  hybrid.py        tracer mode: Presidio + PII-Tracer combination
  pseudonymise.py  text / JSON pseudonymisation with a vault
  vault.py         placeholder <-> value store, restore
  middleware.py    LangChain middleware, PII thread
  cli.py           interactive tester (ezpiizi)
  bench/           benchmark (ezpiizi-bench)
tests/             pytest (pseudonymisation, hybrid rules, middleware, bench scoring)
```

Run the tests with `pytest` and the linter with `ruff check src tests`.

## Release

Bump `version` in `pyproject.toml`, update `CHANGELOG.md`, then push a matching tag (`git tag v0.1.0 &&
git push --tags`): the `Publish to PyPI` workflow tests, builds and publishes with trusted publishing.

## License

MIT. PII-Tracer is published by Perplexity under the MIT license and downloaded from Hugging Face at a
pinned revision; it is not bundled with this package.
