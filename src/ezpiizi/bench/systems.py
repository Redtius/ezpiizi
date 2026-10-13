"""Systems under test: text -> [(type, start, end)] with benchmark types.

    C      presidio   ezpiizi presidio mode
    H1-H6  Presidio + PII-Tracer, one step added at a time (hybrid.py), H6 = ezpiizi tracer mode:
           H1 union, H2 + trim, H3 + typing, H4 + cross-confirmation, H5 + filters, H6 + spaCy names
"""
from ezpiizi import detection, hybrid, tracer

TO_BENCH = {"EMAIL_ADDRESS": "EMAIL", "CREDIT_CARD": "CARD", "MA_CIN": "CIN", "MA_PHONE": "PHONE",
            "MA_IBAN": "IBAN", "MA_RIB": "RIB", "PERSON": "PERSON", "ADDRESS": "ADDRESS", "ACCOUNT": "ACCOUNT"}
H_STEPS = {   # cumulative
    "H1": dict(trim_spans=False, typing=False, cross=False, filters=False, spacy_names=False),
    "H2": dict(trim_spans=True, typing=False, cross=False, filters=False, spacy_names=False),
    "H3": dict(trim_spans=True, typing=True, cross=False, filters=False, spacy_names=False),
    "H4": dict(trim_spans=True, typing=True, cross=True, filters=False, spacy_names=False),
    "H5": dict(trim_spans=True, typing=True, cross=True, filters=True, spacy_names=False),
    "H6": dict(trim_spans=True, typing=True, cross=True, filters=True, spacy_names=True),
}
H_NAMES = {"H1": "union", "H2": "+trim", "H3": "+typing", "H4": "+cross", "H5": "+filters", "H6": "+spacy"}


def _bench(results) -> list[tuple[str, int, int]]:
    return [(TO_BENCH[r.entity_type], r.start, r.end) for r in results]


def build(names: list[str]) -> dict:
    factories = {"C": ("C presidio", lambda: lambda text: _bench(detection.detect_presidio(text)))}
    for h, steps in H_STEPS.items():
        factories[h] = (f"{h} presidio+tracer {H_NAMES[h]}",
                        lambda steps=steps: lambda text: _bench(hybrid.detect_hybrid(text, **steps)))
    unknown = set(names) - set(factories)
    if unknown:
        raise SystemExit(f"Unknown systems {sorted(unknown)}: use C, H1-H6")
    systems = {factories[n][0]: factories[n][1]() for n in names}
    detection.analyzer()
    if set(names) & set(H_STEPS):
        tracer.model()
    return systems
