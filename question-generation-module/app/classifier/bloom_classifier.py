"""
Runtime wrapper around the fine-tuned BloomBERT classifier.

Usage:
    classifier = BloomClassifier.load("models/bloom_distilbert")
    pred = classifier.predict("Define a semaphore.")
    # pred.level == "easy", pred.confidence ~ 0.95

Design choices:
  * Single instance loaded at FastAPI startup, reused for all requests.
  * Graceful fallback: if weights aren't on disk yet (model still training on
    Kaggle), `BloomClassifier.load()` returns a stub whose `predict()` returns
    `BloomPrediction(level=None, confidence=0.0)`. The rest of the pipeline
    treats `None` as "no validation available" and proceeds without retry.
  * Batched prediction for efficiency when classifying multiple generated
    questions per request.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Bloom 6-level → 3-level mapping used everywhere in this module.
# Matches the mapping used during training in scripts/build_training_set.py.
BLOOM6_TO_LEVEL = {
    "remember":   "easy",
    "understand": "easy",
    "apply":      "medium",
    "analyze":    "medium",
    "evaluate":   "hard",
    "create":     "hard",
}


@dataclass(frozen=True)
class BloomPrediction:
    """Result of classifying a single question."""
    level: Optional[str]            # "easy" | "medium" | "hard" | None (stub)
    confidence: float               # softmax probability of the predicted class
    probs: Optional[dict[str, float]] = None  # full distribution if available


class BloomClassifier:
    """Wraps a fine-tuned DistilBertForSequenceClassification."""

    LEVELS = ("easy", "medium", "hard")

    def __init__(self, model, tokenizer, device, label_map: dict[str, int]):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.label_to_id = label_map
        self.id_to_label = {v: k for k, v in label_map.items()}
        self.max_len = 128

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, model_dir: str | Path) -> "BloomClassifier":
        """Load from a directory produced by Cell 8 of the training notebook.

        If the directory or weights are missing, returns a stub classifier
        whose predict() returns level=None (graceful degradation — the API
        can still serve generation requests, just without level validation).
        """
        model_dir = Path(model_dir)
        if not model_dir.exists():
            logger.warning(
                "BloomBERT weights not found at %s — running in stub mode "
                "(no level validation will be performed).", model_dir,
            )
            return _StubBloomClassifier()
        try:
            import torch
            from transformers import (
                DistilBertForSequenceClassification,
                DistilBertTokenizerFast,
            )
            tokenizer = DistilBertTokenizerFast.from_pretrained(str(model_dir))
            model = DistilBertForSequenceClassification.from_pretrained(str(model_dir))
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model.to(device).eval()
            label_map_path = model_dir / "label_map.json"
            if label_map_path.exists():
                label_map = json.loads(label_map_path.read_text())
            else:
                # default mapping if label_map.json is missing
                label_map = {"easy": 0, "medium": 1, "hard": 2}
            logger.info("BloomBERT loaded from %s on %s", model_dir, device)
            return cls(model, tokenizer, device, label_map)
        except Exception as e:  # noqa: BLE001 — wrapper must not crash startup
            logger.error("Failed to load BloomBERT from %s: %s", model_dir, e)
            return _StubBloomClassifier()

    # ------------------------------------------------------------- prediction
    def predict(self, text: str) -> BloomPrediction:
        return self.predict_batch([text])[0]

    def predict_batch(self, texts: Iterable[str]) -> list[BloomPrediction]:
        import torch
        texts = list(texts)
        if not texts:
            return []
        with torch.no_grad():
            enc = self.tokenizer(
                texts, padding=True, truncation=True,
                max_length=self.max_len, return_tensors="pt",
            ).to(self.device)
            logits = self.model(**enc).logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
            preds = logits.argmax(dim=-1).cpu().tolist()
        results = []
        for p, pr in zip(preds, probs):
            level = self.id_to_label[p]
            results.append(BloomPrediction(
                level=level,
                confidence=float(pr[p]),
                probs={self.id_to_label[i]: float(pr[i]) for i in range(len(pr))},
            ))
        return results


class _StubBloomClassifier(BloomClassifier):
    """No-op classifier used when weights aren't on disk yet."""

    def __init__(self):  # noqa: D401 — bypass parent __init__ deliberately
        self.model = None
        self.tokenizer = None
        self.device = None
        self.label_to_id = {}
        self.id_to_label = {}
        self.max_len = 0

    def predict(self, text: str) -> BloomPrediction:
        return BloomPrediction(level=None, confidence=0.0, probs=None)

    def predict_batch(self, texts: Iterable[str]) -> list[BloomPrediction]:
        return [BloomPrediction(level=None, confidence=0.0) for _ in texts]


# ---------------------------------------------------------------------- utils
def bloom6_to_level(bloom6: str) -> str:
    """Map a 6-level Bloom name (case-insensitive) to easy/medium/hard."""
    return BLOOM6_TO_LEVEL.get(bloom6.lower().strip(), "medium")
