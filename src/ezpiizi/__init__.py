"""ezpiizi: reversible PII pseudonymisation for French / Moroccan text.

Presidio alone, or Presidio + PII-Tracer combined (hybrid.py, enable_tracer()).

The LangChain middleware lives in `ezpiizi.middleware` (optional dependency).
"""
from ezpiizi.config import configure
from ezpiizi.detection import MODES, detect, enable_tracer, prepare
from ezpiizi.pseudonymise import context_words, pseudonymise_content, pseudonymise_json, pseudonymise_text
from ezpiizi.vault import PiiVault, vault_for

__all__ = ["MODES", "PiiVault", "configure", "prepare", "context_words", "detect", "enable_tracer", "pseudonymise_content",
           "pseudonymise_json", "pseudonymise_text", "vault_for"]
