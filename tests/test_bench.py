from ezpiizi.bench.datasets import _bio_spans
from ezpiizi.bench.run import score


def test_bio_spans_rebuild_text_and_offsets():
    tokens = ["présence", "de", "Ronald", "Boyle", ",", "Irlande"]
    labels = ["O", "O", "B-PERSON", "I-PERSON", "O", "B-ADDRESS"]
    text, spans = _bio_spans(tokens, labels)
    assert [(t, text[s:e]) for t, s, e in spans] == [("PERSON", "Ronald Boyle"), ("ADDRESS", "Irlande")]


def test_score_ignores_annotated_non_pii():
    rows = [{"text": "Karim travaille chez Maroc Telecom",
             "gold": [("PERSON", 0, 5)], "ignore": [(21, 34)]}]
    def system(text):
        return [("PERSON", 0, 5), ("PERSON", 21, 34)]   # second one is on an ignored span
    stats, errors, _ = score(system, rows)
    assert stats["PERSON"]["full"] == 1 and stats["PERSON"]["false_pos"] == 0 and not errors
