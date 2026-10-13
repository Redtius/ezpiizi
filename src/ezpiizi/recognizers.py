"""Presidio recognizers for Moroccan identifiers."""
from presidio_analyzer import Pattern, PatternRecognizer

from ezpiizi.config import LANGUAGE

IBAN_REGEX = r"\bMA\d{2}(?:\s?\d{4}){6}\b"
PHONE_REGEX = r"(?:\+212|00212|\b0)\s?[5-7](?:[\s.-]?\d{2}){4}\b"
CIN_LETTERS_REGEX = r"\b(?!(?:le|la|de|du|un|et|en|au|ou|il|je|tu|a|y)[\s-])[A-Z]{1,2}[\s-]?\d{5,6}\b"
CIN_DIGITS_REGEX = r"(?<=\b(?:cin|cni|carte nationale|identit[ée])\b[^\d\n]{0,15})\d{5,8}\b"


class MoroccanIbanRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(
            supported_entity="MA_IBAN",
            supported_language=LANGUAGE,
            patterns=[Pattern("ma_iban", IBAN_REGEX, score=0.6)],
            context=["iban", "rib", "compte", "virement"],
        )

    def validate_result(self, pattern_text: str):
        # A valid mod-97 checksum confirms it; an invalid one (typo) is still personal data: None, not False.
        s = pattern_text.replace(" ", "")
        number = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
        return True if int(number) % 97 == 1 else None


def moroccan_phone() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="MA_PHONE",
        supported_language=LANGUAGE,
        patterns=[Pattern("ma_phone", PHONE_REGEX, score=0.6)],
        context=["téléphone", "tel", "tél", "portable", "gsm", "numéro", "appeler", "phone"],
    )


def moroccan_cin() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="MA_CIN",
        supported_language=LANGUAGE,
        patterns=[
            Pattern("ma_cin_letters", CIN_LETTERS_REGEX, score=0.3),        # needs a context word to pass
            Pattern("ma_cin_digits_after_keyword", CIN_DIGITS_REGEX, score=0.6),
        ],
        context=["cin", "cni", "carte nationale", "identité", "pièce"],
    )
