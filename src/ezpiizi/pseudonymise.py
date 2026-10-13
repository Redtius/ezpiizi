import json
import re
from functools import lru_cache

from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from ezpiizi import config, detection
from ezpiizi.vault import PiiVault

MASKED = re.compile(r"\*{2,}")   # already masked upstream ("MA64 **** 1724")


@lru_cache(maxsize=1)
def anonymizer() -> AnonymizerEngine:
    return AnonymizerEngine()


def context_words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def pseudonymise_text(text: str, vault: PiiVault, context: list[str] | None = None, mode: str | None = None) -> str:
    """context: words treated as if next to every match, e.g. the assistant's previous question ("votre CIN ?").
    mode: "presidio", "tracer" or "tracer-alone"; None = the process default (enable_tracer)."""
    if not text.strip():
        return text
    mode = mode or detection.mode()
    cache_key = f"{mode}\x00{text}\x00{' '.join(context or [])}"
    if cache_key in vault.cache:
        return vault.cache[cache_key]

    operators = {
        entity: OperatorConfig("custom", {"lambda": lambda value, e=entity: vault.placeholder_for(e, value)})
        for entity in config.ALL_ENTITIES
    }
    out = anonymizer().anonymize(text=text, analyzer_results=detection.detect(text, context, mode),
                                 operators=operators).text

    for (_, value), placeholder in sorted(vault.by_value.items(), key=lambda kv: -len(kv[0][1])):
        if len(value) > 2:
            out = out.replace(value, placeholder)

    vault.cache[cache_key] = out
    return out


def pseudonymise_json(value, vault: PiiVault, key: str | None = None, mode: str | None = None):
    if isinstance(value, dict):
        return {k: pseudonymise_json(v, vault, k, mode) for k, v in value.items()}
    if isinstance(value, list):
        return [pseudonymise_json(v, vault, key, mode) for v in value]
    if isinstance(value, str):
        if key in config.PII_KEYS and not MASKED.search(value):
            return vault.placeholder_for(config.PII_KEYS[key], value)
        return pseudonymise_text(value, vault, mode=mode)
    return value


def pseudonymise_content(content: str, vault: PiiVault, mode: str | None = None) -> str:
    """JSON (tool results) uses its keys; anything else is free text."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return pseudonymise_text(content, vault, mode=mode)
    if isinstance(data, (dict, list)):
        return json.dumps(pseudonymise_json(data, vault, mode=mode), ensure_ascii=False)
    return pseudonymise_text(content, vault, mode=mode)
