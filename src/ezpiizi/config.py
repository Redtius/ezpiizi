LANGUAGE = "fr"
SPACY_MODEL = "fr_core_news_md"

# Types we pseudonymise. Locations, organisations and dates are left alone on purpose (over-masking).
ENTITIES = ["PERSON", "EMAIL_ADDRESS", "CREDIT_CARD", "MA_IBAN", "MA_PHONE", "MA_CIN"]
ALL_ENTITIES = ENTITIES + ["ADDRESS", "ACCOUNT", "MA_RIB",   # only from PII-Tracer (tracer modes)
                           "DATE", "URL", "SECRET", "OTHER_PII"]   # only from PII-Tracer alone

SCORE_THRESHOLD = 0.5

# Known false positives of NER (places, card brands) that must never be masked.
# Add your own (product, brand, assistant names) with ezpiizi.configure(allow=[...]).
ALLOW_LIST = ["Maarif", "Anfa", "Agdal", "Gauthier", "Casablanca", "Rabat", "Marrakech", "Tanger", "Fès",
              "Visa", "Mastercard", "Premier"]

# JSON keys that say what a value is: trusted directly, no detection.
# "name" is deliberately absent: it can be a person or a company.
PII_KEYS = {
    "first_name": "PERSON", "last_name": "PERSON", "full_name": "PERSON",
    "email": "EMAIL_ADDRESS", "phone": "MA_PHONE", "mobile": "MA_PHONE",
    "iban": "MA_IBAN", "cin": "MA_CIN", "card_number": "CREDIT_CARD",
}

# PII-Tracer (Perplexity, MIT). Runs remote code: always load the reviewed revision.
TRACER_MODEL = "perplexity-ai/PII-Tracer"
TRACER_REVISION = "d25c16f2e57e321f6d2527715c01df9112f956f5"
TRACER_LABELS = {   # private_url, private_date, secret, other_pii: not used
    "private_person": "PERSON", "private_email": "EMAIL_ADDRESS", "private_phone": "MA_PHONE",
    "private_address": "ADDRESS", "account_number": "ACCOUNT",
}
TRACER_ALL_LABELS = TRACER_LABELS | {   # tracer-alone mode: everything the model knows
    "private_date": "DATE", "private_url": "URL", "secret": "SECRET", "other_pii": "OTHER_PII",
}
TRACER_THRESHOLD = 0.5        # minimum score for any PII-Tracer span
TRACER_CONFIRM = 0.9          # with cross-confirmation: non-person spans below this need Presidio support

# Your application's own identifiers (account, card, claim ids...): never PII. Regexes matching a whole
# token, e.g. [r"K\d{4}", r"CLM-\d{4}-\d{4}"]. Set with ezpiizi.configure(id_patterns=[...]).
ID_ALLOW_PATTERNS: list[str] = []


def configure(allow: list[str] | None = None, id_patterns: list[str] | None = None) -> None:
    """Application-specific settings, once at startup (before the first message: vaults cache results).

    allow        words never masked, added to ALLOW_LIST (your product, brand or assistant names)
    id_patterns  regexes of your own identifiers, never masked (replaces ID_ALLOW_PATTERNS)
    """
    if allow:
        ALLOW_LIST.extend(w for w in allow if w not in ALLOW_LIST)
    if id_patterns is not None:
        ID_ALLOW_PATTERNS[:] = id_patterns
