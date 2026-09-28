"""Seeker language detection (fastText lid.176, 176 languages, offline, <1 ms).

    detect_language("مسلمان کعبہ کی عبادت کیوں کرتے ہیں؟")  -> ("ur", 0.97)

The model file is downloaded by `python -m ingest.download` to data/models/.
Notes:
  * `model.f.predict` is used directly: fastText's Python wrapper breaks on NumPy 2.
  * Short English questions are often mistaken for Malay/Indonesian by fastText,
    so text with enough common English function words is classified as English.
  * Regional Arabic labels (arz, ary, ...) are folded into "ar"; Punjabi-Shahmukhi into "ur".
"""
from __future__ import annotations

import re
from functools import lru_cache

from retrieval import config

MODEL_PATH = config.DATA_DIR / "models" / "lid.176.ftz"
MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"
_FOLD = {"arz": "ar", "ary": "ar", "acm": "ar", "apc": "ar", "ajp": "ar", "pnb": "ur", "ms": "ms"}
_EN_WORDS = frozenset(
    "the is are was were do does did why what how who can could would should will i you he she "
    "we they it this that my your of to in on and or not a an be have has with for about islam "
    "muslims muslim god allah quran prophet".split()
)


@lru_cache(maxsize=1)
def _model():
    import fasttext

    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"{MODEL_PATH} missing; run: python -m ingest.download")
    fasttext.FastText.eprint = lambda *a, **k: None  # silence load warning
    return fasttext.load_model(str(MODEL_PATH))


def detect_language(text: str) -> tuple[str, float]:
    """Return (ISO 639-1-ish code, confidence 0-1). Empty text -> ("en", 0.0)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return "en", 0.0
    words = re.findall(r"[a-zA-Z']+", text.lower())
    labels = _model().f.predict(text + "\n", 3, 0.0, "strict")
    prob, label = labels[0]
    code = label.replace("__label__", "")
    code = _FOLD.get(code, code)
    if words and code != "en":
        share = sum(w in _EN_WORDS for w in words) / len(words)
        if share >= 0.3 and len(words) >= 2:
            return "en", round(max(prob, share), 3)
    return code, round(float(prob), 3)
