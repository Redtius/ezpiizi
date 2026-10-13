import pytest

from ezpiizi import config
from ezpiizi.hybrid import rejected, trim, type_account


@pytest.fixture(autouse=True)
def app_ids():
    """The application's own identifiers (as an assistant would configure them)."""
    saved = list(config.ID_ALLOW_PATTERNS)
    config.configure(id_patterns=[r"[ABCK]\d{3,4}", r"CLM-\d{4}-\d{4}"])
    yield
    config.ID_ALLOW_PATTERNS[:] = saved



@pytest.mark.parametrize("entity, text, expected", [
    ("ACCOUNT", "Mon IBAN est MA64 1043 3218 1960 0133 8908 3863", "MA64 1043 3218 1960 0133 8908 3863"),
    ("ACCOUNT", "ma C.I.N est BW19236", "BW19236"),
    ("ACCOUNT", "mon RIB : 011 780 0000012345678901 23", "011 780 0000012345678901 23"),
    ("ACCOUNT", "un virement de 12345 dirhams", "12345"),
    ("ADDRESS", "J'habite au 12 rue Ibn Sina, Casablanca", "12 rue Ibn Sina, Casablanca"),
    ("PERSON", "Bonjour Monsieur Benali", "Benali"),
    ("PERSON", "M . Heiko Jonny Maniero", "Heiko Jonny Maniero"),
    ("PERSON", "'Amina", "Amina"),
    ("MA_PHONE", "tél 0612345678", "0612345678"),
])
def test_trim(entity, text, expected):
    start, end = trim(entity, 0, len(text), text)
    assert text[start:end] == expected


@pytest.mark.parametrize("text, span, expected", [
    ("here's my DNI 12345678Z", "2345678Z", "12345678Z"),                  # span cut by PII-Tracer, letter kept
    ("Mon NIE espagnol est X1234567L.", "X1234567L", "X1234567L"),
    ("My National Insurance number is QQ123456C.", "QQ123456C", "QQ123456C"),
    ("Mon passeport français : 19FV12345.", "19FV12345", "19FV12345"),
    ("Il mio codice fiscale è RSSMRA85M01H501Z.", "RSSMRA85M01H501Z", "RSSMRA85M01H501Z"),
    ("My SSN is 078-05-1120.", "078-05-1120", "078-05-1120"),
    ("Mon numéro national belge : 85.07.30-033.28.", "85.07.30-033.28", "85.07.30-033.28"),
    ("Ma CIN est BE 123456, merci", "BE 123456, merci", "BE 123456"),
])
def test_trim_foreign_identifiers(text, span, expected):
    i = text.index(span)
    start, end = trim("ACCOUNT", i, i + len(span), text)
    assert text[start:end] == expected


def test_trim_drops_span_without_value():
    assert trim("ACCOUNT", 0, 9, "C.I.N est") is None


@pytest.mark.parametrize("value, expected", [
    ("MA64 1043 3218 1960 0133 8908 3863", "MA_IBAN"),
    ("011 780 0000012345678901 23", "MA_RIB"),
    ("4539 1488 0343 6467", "CREDIT_CARD"),
    ("BW19236", "MA_CIN"),
    ("1234 5678 9012 3456", "ACCOUNT"),      # 16 digits but fails Luhn
])
def test_type_account(value, expected):
    assert type_account(value) == expected


@pytest.mark.parametrize("text, start, end, reason", [
    ("Mon compte A1001", 12, 16, "identifiant applicatif"),     # "1001" inside "A1001"
    ("ma carte K1001", 9, 14, "identifiant applicatif"),
    ("réclamation CLM-2026-0412", 12, 25, "identifiant applicatif"),
    ("bénéficiaire MA64 **** 1724", 13, 27, "déjà masqué"),
    ("bénéficiaire MA64 **** 1724", 23, 27, "déjà masqué"),          # only "1724" detected
    ("réclamation CLM-2026-0412", 16, 25, "identifiant applicatif"),        # only "2026-0412" detected
])
def test_rejected(text, start, end, reason):
    assert rejected("ACCOUNT", start, end, text) == reason


def test_real_value_not_rejected():
    assert rejected("ACCOUNT", 12, 19, "ma CIN est BW19236") is None


def test_imperative_verb_is_not_a_person():
    # PII-Tracer took "Rappelle" (capitalised at the start) for a first name: the model then saw
    # "<PERSON_2>-moi la toute première chose..." and refused, thinking it was about another customer.
    from ezpiizi.hybrid import rejected
    text = "Rappelle-moi la toute première chose que je t'ai demandée."
    assert rejected("PERSON", 0, len("Rappelle"), text) == "verbe à l'impératif"
    text = "Envoie-le à Karim Bennani."
    assert rejected("PERSON", 0, len("Envoie"), text) == "verbe à l'impératif"
    i = text.index("Karim")
    assert rejected("PERSON", i, i + len("Karim Bennani"), text) is None      # real names still masked
