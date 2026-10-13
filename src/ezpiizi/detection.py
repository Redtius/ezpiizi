"""Detection, two modes:

    presidio      Presidio alone: regex + checksums + context + spaCy NER (default, no model to load)
    tracer        Presidio + PII-Tracer combined (hybrid.py), after enable_tracer(): recommended
    tracer-alone  PII-Tracer's raw output, every label, no Presidio, no filters (enable_tracer(alone=True)):
                  to see what the model finds; not for production (no checksums, trimming or filters)
"""
from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import CreditCardRecognizer, EmailRecognizer, SpacyRecognizer

from ezpiizi import config
from ezpiizi.recognizers import MoroccanIbanRecognizer, moroccan_cin, moroccan_phone

USE_TRACER = False
TRACER_ALONE = False


@lru_cache(maxsize=1)
def analyzer() -> AnalyzerEngine:
    try:
        nlp_engine = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": config.LANGUAGE, "model_name": config.SPACY_MODEL}],
            "ner_model_configuration": {"model_to_presidio_entity_mapping": {"PER": "PERSON"}},
        }).create_engine()
    except OSError as e:
        raise RuntimeError(f"spaCy model missing: python -m spacy download {config.SPACY_MODEL}") from e

    registry = RecognizerRegistry(supported_languages=[config.LANGUAGE])
    for recognizer in (
        SpacyRecognizer(supported_language=config.LANGUAGE, supported_entities=["PERSON"]),
        EmailRecognizer(supported_language=config.LANGUAGE),
        CreditCardRecognizer(supported_language=config.LANGUAGE),
        MoroccanIbanRecognizer(),
        moroccan_phone(),
        moroccan_cin(),
    ):
        registry.add_recognizer(recognizer)
    return AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=[config.LANGUAGE])


def is_plausible(r: RecognizerResult, text: str, doc) -> bool:
    """NER post-filter: a name has a proper noun (not "Réponds") and no digit (not "BE123456")."""
    if r.entity_type != "PERSON":
        return True
    span = doc.char_span(r.start, r.end, alignment_mode="expand")
    has_proper_noun = span is not None and any(t.pos_ == "PROPN" for t in span)
    return has_proper_noun and not any(c.isdigit() for c in text[r.start:r.end])


def detect_presidio(text: str, context: list[str] | None = None) -> list[RecognizerResult]:
    engine = analyzer()
    artifacts = engine.nlp_engine.process_text(text, config.LANGUAGE)
    results = engine.analyze(text=text, language=config.LANGUAGE, entities=config.ENTITIES,
                             nlp_artifacts=artifacts, score_threshold=config.SCORE_THRESHOLD,
                             allow_list=config.ALLOW_LIST, context=context)
    return [r for r in results if is_plausible(r, text, artifacts.tokens)]


MODES = ("presidio", "tracer", "tracer-alone")


def check_mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}: expected one of {', '.join(MODES)}")
    return mode


def prepare(mode: str) -> None:
    """Load what a mode needs now (PII-Tracer takes a few seconds), instead of on the first message."""
    check_mode(mode)
    analyzer()
    if mode != "presidio":
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except ImportError as e:
            raise RuntimeError(f'{mode} mode needs the optional dependencies: pip install "ezpiizi[tracer]"') from e
        from ezpiizi import tracer
        tracer.model()


def enable_tracer(on: bool = True, alone: bool = False) -> None:
    """Default mode of this process: Presidio + PII-Tracer, or PII-Tracer alone (loads the model now)."""
    global USE_TRACER, TRACER_ALONE
    if on:
        prepare("tracer-alone" if alone else "tracer")
    USE_TRACER = on
    TRACER_ALONE = on and alone


def mode() -> str:
    if USE_TRACER:
        return "tracer-alone" if TRACER_ALONE else "tracer"
    return "presidio"


def detect(text: str, context: list[str] | None = None, mode: str | None = None) -> list[RecognizerResult]:
    """mode: "presidio", "tracer" or "tracer-alone"; None = the process default (enable_tracer)."""
    mode = check_mode(mode) if mode else globals()["mode"]()
    if mode == "tracer-alone":
        from ezpiizi.tracer import detect_tracer
        return detect_tracer(text, labels=config.TRACER_ALL_LABELS)
    if mode == "tracer":
        from ezpiizi.hybrid import detect_hybrid
        return detect_hybrid(text, context)
    return detect_presidio(text, context)
