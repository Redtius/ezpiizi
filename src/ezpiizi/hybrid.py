"""Presidio + PII-Tracer. Each step can be switched off to measure it (see bench systems H1-H5):

    union    Presidio (minus spaCy names) + PII-Tracer; Presidio wins overlaps
    trim     cut PII-Tracer spans down to the value ("Mon IBAN est MA64..." -> "MA64...")
    typing   give account_number its real type (IBAN, RIB, card, CIN) via format checks
    cross    a weak Presidio match + a PII-Tracer span confirm each other; a low-score PII-Tracer
             identifier without Presidio support is dropped
    filters  the application's own IDs (configure(id_patterns=...)), already-masked values, implausible names
    spacy_names  also keep spaCy's names, only where PII-Tracer found nothing
Priority on overlaps: Presidio structured identifiers > PII-Tracer > spaCy names.
"""
import re

from presidio_analyzer import RecognizerResult

from ezpiizi import config, detection, tracer

TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9./-]*[A-Za-z0-9])?")    # "MA64", "12345678Z", "085-05-1120"
PREFIX = re.compile(r"[A-Z]{1,2}")                                   # "BE" in "BE 123456"
PHONE = re.compile(r"\+?\d(?:[\d\s.-]*\d)?")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
STREET = re.compile(r"\d+\s*,?\s*(?:bis\s+)?(?:rue|avenue|av\.?|bd|boulevard|lot|lotissement|r[ée]sidence|hay"
                    r"|quartier|place|route|imm(?:euble)?|angle)\b|\b(?:rue|avenue|bd|boulevard|lot|lotissement"
                    r"|r[ée]sidence|hay|quartier|place|route)\b", re.I)
TITLE = re.compile(r"^(?:bonjour|bonsoir|salut|cher|chère|monsieur|madame|mademoiselle|messieurs|mesdames|mme"
                   r"|mlle|mr|m|dr|docteur|maître|me|mes)\b\s*\.?\s*", re.I)
MASKED = re.compile(r"\*{2,}")


def _longest(pattern: re.Pattern, text: str, start: int, end: int, min_digits: int = 0):
    best = None
    for m in pattern.finditer(text, start, end):
        if sum(c.isdigit() for c in m.group()) >= min_digits and (not best or len(m.group()) > best[1] - best[0]):
            best = (m.start(), m.end())
    return best


def _identifier(text: str, start: int, end: int, min_digits: int = 4) -> tuple[int, int] | None:
    """An identifier inside a span: the longest run of tokens containing digits, one space apart, letters
    allowed (Spanish DNI 12345678Z, French passport 19FV12345, codice fiscale), with an optional 1-2 capital
    letter prefix ("BE 123456"). PII-Tracer sometimes cuts a token ("2345678Z" in "12345678Z"): the span is
    first extended to whole tokens."""
    while start > 0 and text[start - 1].isalnum():
        start -= 1
    while end < len(text) and text[end].isalnum():
        end += 1
    best = run = previous = None
    for m in TOKEN.finditer(text, start, end):
        adjacent = previous is not None and m.start() - previous.end() == 1 and text[previous.end()].isspace()
        if any(c.isdigit() for c in m.group()):
            if run and adjacent:
                run = (run[0], m.end())
            elif adjacent and PREFIX.fullmatch(previous.group()):
                run = (previous.start(), m.end())
            else:
                run = (m.start(), m.end())
            digits = sum(c.isdigit() for c in text[run[0]:run[1]])
            if digits >= min_digits and (not best or run[1] - run[0] > best[1] - best[0]):
                best = run
        else:
            run = None
        previous = m
    return best


def trim(entity: str, start: int, end: int, text: str) -> tuple[int, int] | None:
    """Span reduced to the value itself, or None when nothing of the right shape is inside."""
    if entity == "ACCOUNT":
        return _identifier(text, start, end)
    if entity == "MA_PHONE":
        return _longest(PHONE, text, start, end, min_digits=8)
    if entity == "EMAIL_ADDRESS":
        return _longest(EMAIL, text, start, end) or (start, end)   # spelled-out emails: keep as is
    if entity == "ADDRESS":
        m = STREET.search(text, start, end)
        return (m.start(), end) if m else (start, end)
    if entity == "PERSON":
        while start < end and not text[start].isalnum():
            start += 1
        while m := TITLE.match(text[start:end]):
            start += m.end()
        return (start, end) if end - start >= 2 else None
    return start, end


def _luhn(digits: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def type_account(value: str) -> str:
    v = re.sub(r"[\s.-]", "", value)
    if re.fullmatch(r"MA\d{26}", v, re.I):
        return "MA_IBAN"
    if re.fullmatch(r"\d{24}", v):
        return "MA_RIB"
    if re.fullmatch(r"\d{13,19}", v) and _luhn(v):
        return "CREDIT_CARD"
    if re.fullmatch(r"[A-Za-z]{1,2}\d{5,8}", v):
        return "MA_CIN"
    return "ACCOUNT"


# A word glued to an object pronoun by a dash is a verb in the imperative (French).
IMPERATIVE = re.compile(r"-(?:moi|toi|nous|vous|le|la|les|lui|leur|y|en)\b", re.IGNORECASE)


def rejected(entity: str, start: int, end: int, text: str) -> str | None:
    value = text[start:end]
    token_start = start      # whole token, dashes included ("CLM-2026-0412", "A1001")
    while token_start > 0 and (text[token_start - 1].isalnum() or text[token_start - 1] == "-"):
        token_start -= 1
    token_end = end
    while token_end < len(text) and (text[token_end].isalnum() or text[token_end] == "-"):
        token_end += 1
    if any(re.fullmatch(p, text[token_start:token_end]) for p in config.ID_ALLOW_PATTERNS):
        return "identifiant applicatif"
    if MASKED.search(text[max(0, start - 12):end]):   # "MA64 **** 1724": the mask is a separate token
        return "déjà masqué"
    if value in config.ALLOW_LIST:
        return "allow list"
    if entity == "PERSON" and any(c.isdigit() for c in value):
        return "nom avec chiffres"
    if entity == "PERSON" and IMPERATIVE.match(text, end):
        return "verbe à l'impératif"            # "Rappelle-moi", "Dis-nous", "Envoie-le": never a name
    return None


def _overlaps(a, b) -> bool:
    return a.start < b.end and a.end > b.start


def detect_hybrid(text: str, context: list[str] | None = None, *, trim_spans: bool = True,
                  typing: bool = True, cross: bool = True, filters: bool = True,
                  spacy_names: bool = True, trace: list | None = None) -> list[RecognizerResult]:
    def note(source, r, verdict):
        if trace is not None:
            trace.append((source, r.entity_type, text[r.start:r.end], r.score, verdict))

    presidio = detection.detect_presidio(text, context)
    kept = [r for r in presidio if r.entity_type != "PERSON"]
    names = [r for r in presidio if r.entity_type == "PERSON"] if spacy_names else []
    for r in kept:
        note("Presidio", r, "gardé")
    weak = []
    if cross:
        engine = detection.analyzer()
        weak = [r for r in engine.analyze(text=text, language=config.LANGUAGE, entities=config.ENTITIES,
                                          score_threshold=0, allow_list=config.ALLOW_LIST, context=context)
                if r.entity_type != "PERSON" and r.score < config.SCORE_THRESHOLD]

    tracer_spans = tracer.detect_tracer(text)
    for t in tracer_spans:
        entity, start, end = t.entity_type, t.start, t.end
        if trim_spans:
            span = trim(entity, start, end, text)
            if span is None:
                note("PII-Tracer", t, "écarté  rien de la bonne forme dedans")
                continue
            start, end = span
        if typing and entity == "ACCOUNT":
            entity = type_account(text[start:end])
        r = RecognizerResult(entity, start, end, t.score)
        if filters and (reason := rejected(entity, start, end, text)):
            note("PII-Tracer", r, f"écarté  {reason}")
            continue
        if any(_overlaps(r, k) for k in kept):
            note("PII-Tracer", r, "écarté  Presidio prioritaire")
            continue
        if cross:
            support = [w for w in weak if _overlaps(r, w)]
            if support:
                best = max(support, key=lambda w: w.score)
                kept.append(best)
                note("Presidio faible", best, "gardé  confirmé par PII-Tracer")
                continue
            if entity != "PERSON" and t.score < config.TRACER_CONFIRM:
                note("PII-Tracer", r, f"écarté  score < {config.TRACER_CONFIRM} sans appui Presidio")
                continue
        kept.append(r)
        note("PII-Tracer", r, "gardé")

    other = [t for t in tracer_spans if t.entity_type != "PERSON"]   # even if dropped above
    for n in names:   # spaCy names last: only where nothing else was found
        if any(_overlaps(n, k) for k in kept):
            note("spaCy", n, "écarté  PII-Tracer prioritaire")
        elif any(_overlaps(n, t) for t in other):
            note("spaCy", n, "écarté  PII-Tracer y voit autre chose qu'un nom")
        else:
            kept.append(n)
            note("spaCy", n, "gardé")
    return kept
