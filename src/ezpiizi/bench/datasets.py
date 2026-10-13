"""Benchmark datasets, all converted to the same shape:

    {"text": str, "gold": [(type, start, end)], "ignore": [(start, end)]}

gold: values that must be masked. ignore: annotated spans that are not PII for us (organisations, dates,
countries...): a detection there counts neither as found nor as a false positive.
"""
import json
from pathlib import Path

TYPES = ["EMAIL", "CARD", "CIN", "PHONE", "IBAN", "RIB", "PERSON", "ADDRESS",
         "ID", "DOB", "SECRET", "IP", "USERNAME"]   # the last five: Gretel only

MAPA_REPO = "joelniklaus/mapa"   # CC-BY-4.0, EUR-Lex court decisions, 24 EU languages
# level="fine" (default): only the name itself is scored. MAPA's coarse PERSON also covers titles ("M .",
# "messieurs"), roles ("juge", "avocat général") and case names: not personal data in our sense.
# level="coarse": MAPA's PERSON spans as annotated.
# In both, every other annotated span (organisations, dates, amounts, countries...) is ignored.
MAPA_NAME_LABELS = {"FAMILY NAME", "GIVEN NAME", "INITIAL NAME"}


def _from_values(rows: list[dict]) -> list[dict]:
    """Our hand-written format: {"text", "entities": [{"type", "value"}]} (first occurrence of value)."""
    out = []
    for row in rows:
        text = row["text"]
        gold = []
        for e in row["entities"]:
            start = text.index(e["value"])
            gold.append((e["type"], start, start + len(e["value"])))
        out.append({"text": text, "gold": gold, "ignore": []})
    return out


def load_jsonl(path: str | Path) -> list[dict]:
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return _from_values(rows)


def _bio_spans(tokens: list[str], labels: list[str]):
    """Rebuild text (tokens joined by spaces) and (label, start, end) spans from BIO tags."""
    text, offsets, pos = [], [], 0
    for tok in tokens:
        offsets.append((pos, pos + len(tok)))
        text.append(tok)
        pos += len(tok) + 1
    spans, current = [], None
    for (start, end), label in zip(offsets, labels, strict=True):
        tag, _, name = label.partition("-")
        if tag == "I" and current and current[0] == name:
            current[2] = end
            continue
        if current:
            spans.append(tuple(current))
            current = None
        if tag in ("B", "I"):
            current = [name, start, end]
    if current:
        spans.append(tuple(current))
    return " ".join(text), spans


def load_mapa(language: str = "fr", splits: tuple[str, ...] = ("test", "validation"),
              level: str = "fine") -> list[dict]:
    from huggingface_hub import hf_hub_download

    out = []
    for split in splits:
        path = hf_hub_download(MAPA_REPO, f"{split}.jsonl", repo_type="dataset")
        for line in Path(path).read_text().splitlines():
            row = json.loads(line)
            if row["language"] != language:
                continue
            text, coarse = _bio_spans(row["tokens"], row["coarse_grained"])
            _, fine = _bio_spans(row["tokens"], row["fine_grained"])
            if level == "fine":
                gold = [("PERSON", s, e) for t, s, e in fine if t in MAPA_NAME_LABELS]
            else:
                gold = [("PERSON", s, e) for t, s, e in coarse if t == "PERSON"]
            gold_spans = {(s, e) for _, s, e in gold}
            ignore = [(s, e) for _, s, e in coarse + fine if (s, e) not in gold_spans]
            out.append({"text": text, "gold": gold, "ignore": ignore})
    return out


GRETEL_REPO = "gretelai/synthetic_pii_finance_multilingual"   # Apache 2.0, synthetic financial documents
GRETEL_REVISION = "7b844d16738527a04264f50214cb426a4cea0897"
# Gretel label -> our type. Not in the map (ignored, not personal): company, date, time, date_time,
# swift_bic_code, bank_routing_number. Labels are generated, so expect some noise.
GRETEL_TYPES = {
    "name": "PERSON", "first_name": "PERSON", "last_name": "PERSON",
    "street_address": "ADDRESS", "local_latlng": "ADDRESS",
    "phone_number": "PHONE", "email": "EMAIL", "iban": "IBAN", "bban": "RIB",
    "credit_card_number": "CARD", "date_of_birth": "DOB",
    "customer_id": "ID", "employee_id": "ID", "passport_number": "ID", "ssn": "ID",
    "driver_license_number": "ID",
    "account_pin": "SECRET", "credit_card_security_code": "SECRET", "password": "SECRET", "api_key": "SECRET",
    "ipv4": "IP", "ipv6": "IP", "user_name": "USERNAME",
}


def load_gretel(language: str = "France", split: str = "test") -> list[dict]:
    """Gretel French financial documents (independent of the models tested: different generator)."""
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(GRETEL_REPO, f"data/{language}_{split}-00000-of-00001.parquet",
                           repo_type="dataset", revision=GRETEL_REVISION)
    out = []
    for row in pq.read_table(path).to_pylist():
        spans = json.loads(row["pii_spans"])
        gold = [(GRETEL_TYPES[s["label"]], s["start"], s["end"]) for s in spans if s["label"] in GRETEL_TYPES]
        ignore = [(s["start"], s["end"]) for s in spans if s["label"] not in GRETEL_TYPES]
        out.append({"text": row["generated_text"], "gold": gold, "ignore": ignore})
    return out


DATASETS = {"mapa": load_mapa, "gretel": load_gretel}
