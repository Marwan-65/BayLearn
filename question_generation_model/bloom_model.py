import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset
from transformers import DistilBertModel, DistilBertForSequenceClassification


LABEL_TO_ID = {"easy": 0, "medium": 1, "hard": 2}
ID_TO_LABEL = {v: k for k, v in LABEL_TO_ID.items()}


class BloomDataset(Dataset):
    def __init__(self, df, tokenizer, max_len):
        self.texts = df["question"].astype(str).tolist()
        self.labels = [LABEL_TO_ID[l] for l in df["level"]]
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        enc = self.tokenizer(
            self.texts[idx],
            truncation=True,
            padding="max_length",
            max_length=self.max_len,
            return_tensors="pt",
        )
        return {
            "input_ids": enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "labels": torch.tensor(self.labels[idx], dtype=torch.long),
        }


class DistilBertBloomClassifier(nn.Module):
    def __init__(self, model_name, num_classes, pooling="cls", head_dropout=0.1):
        super().__init__()
        self.encoder = DistilBertModel.from_pretrained(model_name)
        hidden = self.encoder.config.hidden_size
        self.pooling = pooling
        self.pre_classifier = nn.Linear(hidden, hidden)
        self.dropout = nn.Dropout(head_dropout)
        self.classifier = nn.Linear(hidden, num_classes)
        nn.init.xavier_uniform_(self.pre_classifier.weight)
        nn.init.zeros_(self.pre_classifier.bias)
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.zeros_(self.classifier.bias)

    def forward(self, input_ids, attention_mask):
        hs = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        if self.pooling == "cls":
            pooled = hs[:, 0]
        else:
            mask = attention_mask.unsqueeze(-1).float()
            pooled = (hs * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
        x = F.gelu(self.pre_classifier(pooled))
        x = self.dropout(x)
        return self.classifier(x)


class FocalLossWithSmoothing(nn.Module):
    def __init__(self, gamma, alpha, label_smoothing, num_classes):
        super().__init__()
        self.gamma = gamma
        self.alpha = alpha
        self.eps = label_smoothing
        self.K = num_classes

    def forward(self, logits, targets):
        log_probs = F.log_softmax(logits, dim=-1)
        probs = log_probs.exp()
        with torch.no_grad():
            true_oh = F.one_hot(targets, num_classes=self.K).float()
            if self.eps > 0:
                soft = true_oh * (1.0 - self.eps) + (1.0 - true_oh) * (self.eps / (self.K - 1))
            else:
                soft = true_oh
        p_t = (probs * true_oh).sum(dim=-1)
        focal = (1.0 - p_t).clamp(min=1e-9).pow(self.gamma)
        ce = -(soft * log_probs).sum(dim=-1)
        return (self.alpha[targets] * focal * ce).mean()


def build_model(config, device):
    model = DistilBertBloomClassifier(
        config["model_name"],
        config["num_classes"],
        pooling=config.get("pooling", "cls"),
        head_dropout=config.get("head_dropout", 0.1),
    )
    for p in model.encoder.parameters():
        p.requires_grad = False
    layers = model.encoder.transformer.layer
    for i in range(6 - config["unfreeze_top"], 6):
        for p in layers[i].parameters():
            p.requires_grad = True
    for p in model.pre_classifier.parameters():
        p.requires_grad = True
    for p in model.classifier.parameters():
        p.requires_grad = True
    return model.to(device)


def make_loss(config, class_weights):
    gamma = config.get("focal_gamma", 0.0)
    eps = config.get("label_smoothing", 0.0)
    if gamma > 0 or eps > 0:
        return FocalLossWithSmoothing(gamma, class_weights, eps, config["num_classes"])
    return nn.CrossEntropyLoss(weight=class_weights)


def export_hf_copy(model, out_dir, tokenizer, config):
    hf = DistilBertForSequenceClassification.from_pretrained(
        config["model_name"], num_labels=config["num_classes"]
    )
    hf.distilbert.load_state_dict(model.encoder.state_dict())
    hf.pre_classifier.weight.data.copy_(model.pre_classifier.weight.data)
    hf.pre_classifier.bias.data.copy_(model.pre_classifier.bias.data)
    hf.classifier.weight.data.copy_(model.classifier.weight.data)
    hf.classifier.bias.data.copy_(model.classifier.bias.data)
    hf.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
