import pytest

from ezpiizi import PiiVault, context_words, pseudonymise_content, pseudonymise_text


def masked(text: str, value: str, context: list[str] | None = None) -> bool:
    return value not in pseudonymise_text(text, PiiVault(), context)


@pytest.mark.parametrize("text, value", [
    ("mon cin est BW19236", "BW19236"),
    ("mon cin est BW 19236", "BW 19236"),
    ("mon CIN : bw-19236", "bw-19236"),
    ("voici mon CIN 19232", "19232"),
    ("ma carte d'identité c'est le 1234567", "1234567"),
])
def test_cin_detected(text, value):
    assert masked(text, value)


@pytest.mark.parametrize("text, value", [
    ("la référence AB654321", "AB654321"),
    ("un virement de 12345 dirhams", "12345"),
    ("le 123456", "123456"),
    ("CIN BW19236 et 12345 dirhams", "12345"),
])
def test_cin_not_detected(text, value):
    assert not masked(text, value)


def test_bare_code_depends_on_previous_message():
    assert not masked("NH12987", "NH12987")
    assert masked("NH12987", "NH12987", context_words("Pouvez-vous me donner votre numéro de CIN ?"))
    assert not masked("NH12987", "NH12987", context_words("Quelle est la référence de votre commande ?"))


def test_nothing_leaks_and_restore_is_exact():
    vault = PiiVault()
    text = "Je suis Amina El Idrissi, IBAN MA64 1043 3218 1960 0133 8908 3863, tél 06 12 34 56 78"
    out = pseudonymise_text(text, vault)
    for value in ("Amina El Idrissi", "MA64 1043", "06 12 34 56 78"):
        assert value not in out
    assert vault.restore(out) == text


def test_same_value_same_placeholder_in_text_and_json():
    vault = PiiVault()
    a = pseudonymise_text("Envoyez 500 dirhams à Karim El Idrissi", vault)
    b = pseudonymise_content('[{"id": "B1001", "name": "Karim El Idrissi"}]', vault)
    placeholder = vault.by_value[("PERSON", "Karim El Idrissi")]
    assert placeholder in a and placeholder in b


def test_no_over_masking():
    vault = PiiVault()
    text = "Où se trouve l'agence de Casablanca Maarif ?"
    assert pseudonymise_text(text, vault) == text
    out = pseudonymise_content('{"iban": "MA64 **** 1724", "bank": "Banque Populaire"}', vault)
    assert "MA64 **** 1724" in out and "Banque Populaire" in out
    assert "Réponds" in pseudonymise_text("Réponds en une phrase.", vault)


def test_invented_placeholder_is_never_shown():
    assert PiiVault().restore("Vous vous appelez <PERSON_9>") == "Vous vous appelez [information non disponible]"
