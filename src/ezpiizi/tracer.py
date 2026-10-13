"""PII-Tracer (perplexity-ai/PII-Tracer): bidirectional Qwen3 encoder, BIOES tagging, 9 PII types.

Loaded with trust_remote_code at a pinned, reviewed revision (modeling code: torch + transformers only).
Inputs over 4,096 tokens are truncated by the model, so long texts are split here.
"""
import os
from functools import lru_cache

from presidio_analyzer import RecognizerResult

from ezpiizi import config

# torch and transformers are imported inside the functions: they are the optional [tracer] dependencies,
# and `import ezpiizi` must work without them (presidio mode).

CHUNK_CHARS = 8000


def _device_and_dtype():
    """CUDA (bf16) > Apple GPU (fp32) > CPU (fp32). Override with EZPIIZI_TRACER_DEVICE / _DTYPE.

    The checkpoint is bf16, but bf16 on a CPU without native support is ~13x slower than fp32
    (measured on an M-series Mac: 6.4 s vs 0.5 s per 1,400-char document, identical spans).
    """
    import torch
    device = os.getenv("EZPIIZI_TRACER_DEVICE") or (
        "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
    dtype = os.getenv("EZPIIZI_TRACER_DTYPE") or ("bfloat16" if device == "cuda" else "float32")
    return device, getattr(torch, dtype)


@lru_cache(maxsize=1)
def model():
    from transformers import AutoModel
    device, dtype = _device_and_dtype()
    m = AutoModel.from_pretrained(config.TRACER_MODEL, trust_remote_code=True, revision=config.TRACER_REVISION)
    return m.to(device=device, dtype=dtype).eval()


def _chunks(text: str):
    start = 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            cut = text.rfind(" ", start, end)
            end = cut if cut > start else end
        yield start, text[start:end]
        start = end


@lru_cache(maxsize=4096)
def _predict(text: str) -> tuple[tuple[str, int, int, float], ...]:
    out = []
    for offset, chunk in _chunks(text):
        spans, _sensitivity = model().predict(chunk)
        out += [(s.label, s.start + offset, s.end + offset, float(s.score)) for s in spans]
    return tuple(out)


def detect_tracer(text: str, threshold: float | None = None,
                  labels: dict[str, str] | None = None) -> list[RecognizerResult]:
    """PII-Tracer spans mapped to our types (labels not in `labels` dropped, e.g. dates, URLs), score >= threshold."""
    threshold = config.TRACER_THRESHOLD if threshold is None else threshold
    labels = config.TRACER_LABELS if labels is None else labels
    return [RecognizerResult(labels[label], start, end, score)
            for label, start, end, score in _predict(text)
            if label in labels and score >= threshold]
