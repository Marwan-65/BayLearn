from __future__ import annotations
import torch
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from transformers import (DistilBertForSequenceClassification,DistilBertTokenizerFast,)
logger = logging.getLogger(__name__)

BLOOM6_TO_LEVEL = {
    "remember":   "easy",
    "understand": "easy",
    "apply":      "medium",
    "analyze":    "medium",
    "evaluate":   "hard",
    "create":     "hard",
}
LEVELS = ("easy", "medium", "hard")

@dataclass(frozen=True)
class BloomPrediction:
    level: Optional[str]
    confidence: float
    probs: Optional[dict[str, float]] = None


class BloomClassifier:
    def __init__(self, model, tokenizer, device, label_map: dict[str, int]):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.label_to_id = label_map
        self.id_to_label = {v: k for k, v in label_map.items()}
        self.max_len = 128

    @classmethod
    def load(cls, model_dir: str | Path) -> "BloomClassifier":
        model_dir = Path(model_dir)
        if not model_dir.exists():
            logger.warning("BloomBERT weights not found at %s — running in stub mode "
                "(no level validation will be performed).", model_dir,)
            return _StubBloomClassifier()
        try:
            tokenizer = DistilBertTokenizerFast.from_pretrained(str(model_dir))
            model = DistilBertForSequenceClassification.from_pretrained(str(model_dir))
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model.to(device).eval()
            label_map_path = model_dir / "label_map.json"
            if label_map_path.exists():
                label_map = json.loads(label_map_path.read_text())
            else:
                label_map = {"easy": 0, "medium": 1, "hard": 2}
            logger.info("BloomBERT loaded from %s on %s", model_dir, device)
            return cls(model, tokenizer, device, label_map)
        except Exception as e:
            logger.error("Failed to load BloomBERT from %s: %s", model_dir, e)
            return _StubBloomClassifier()

    def predict(self, text: str) -> BloomPrediction:
        return self.predict_batch([text])[0]

    def predict_batch(self, texts: Iterable[str]) -> list[BloomPrediction]:
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
                probs={self.id_to_label[i]: float(pr[i]) for i in range(len(pr))},))
        return results


class _StubBloomClassifier(BloomClassifier):

    def __init__(self):
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


def bloom6_to_level(bloom6: str) -> str:
    s = bloom6.lower().strip()
    if s in LEVELS:
        return s
    return BLOOM6_TO_LEVEL.get(s, "medium")
