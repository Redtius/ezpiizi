# Benchmark

```sh
ezpiizi-bench                                      # MAPA (French), systems C and H6
ezpiizi-bench --dataset gretel --systems C,H6      # Gretel synthetic finance, French
ezpiizi-bench --systems C,H1,H2,H3,H4,H5,H6        # contribution of each step of the combination
ezpiizi-bench --dataset my.jsonl --details         # your sentences, every error listed
ezpiizi-bench --limit 100                          # first 100 sentences only
```

Datasets are downloaded from Hugging Face on first use (`pip install -e ".[bench]"`).

## Systems

| System | What it is |
|---|---|
| `C` | presidio mode |
| `H1` | Presidio + PII-Tracer, union only |
| `H2` | + trim |
| `H3` | + typing |
| `H4` | + cross-confirmation |
| `H5` | + filters |
| `H6` | + spaCy names: **the tracer mode** |

## Datasets

| Name | Source | Notes |
|---|---|---|
| `mapa` | [joelniklaus/mapa](https://huggingface.co/datasets/joelniklaus/mapa), EUR-Lex court decisions, CC-BY-4.0 | only `PERSON` is scored. `--mapa-level fine` (default): the name itself; `coarse`: MAPA's spans, titles and roles included. Other annotations (organisations, dates, amounts, countries) are ignored spans |
| `gretel` | [gretelai/synthetic_pii_finance_multilingual](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual), French split | synthetic financial documents, many types |
| a `.jsonl` path | your file | one object per line, see below |

Your own sentences, one JSON object per line:

```json
{"text": "Mon IBAN est MA64 0111 1000 0012 3456 7890 1234", "entities": [{"type": "IBAN", "value": "MA64 0111 1000 0012 3456 7890 1234"}]}
```

`value` must appear in `text` (its first occurrence is used). Types are the benchmark's: `EMAIL`, `CARD`,
`CIN`, `PHONE`, `IBAN`, `RIB`, `PERSON`, `ADDRESS`… Include sentences **without** PII too: they measure
over-masking.

## Metrics

Span-based, per type:

| Metric | Meaning |
|---|---|
| full | a prediction of the right type covers the whole value: found |
| partial | overlaps but leaves part of the value visible: not found |
| false + | a prediction overlapping no value of its type (and no ignored span): over-masking |
| leak | a value covered by no prediction at all: what matters for privacy |
| chars | label-agnostic character precision / recall / F1, as in the PII-TRACE paper; ignored spans count neither way |
| ms/sentence | detection time |

A generic `ACCOUNT` prediction counts as found for an `IBAN`, `RIB`, `CARD` or `ID` value.
