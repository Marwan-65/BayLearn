import os
import csv
import json
import random
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, to import question_generation_model

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
from torch.cuda.amp import autocast, GradScaler
from transformers import (
    DistilBertTokenizerFast,
    get_linear_schedule_with_warmup,
    get_cosine_schedule_with_warmup,
)
from sklearn.metrics import classification_report, confusion_matrix, f1_score

from question_generation_model.bloom_model import (
    LABEL_TO_ID,
    ID_TO_LABEL,
    BloomDataset,
    build_model,
    make_loss,
    export_hf_copy,
)

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)

ROOT = Path(__file__).resolve().parents[1]

DEFAULTS = {
    "model_name": "distilbert-base-uncased",
    "max_len": 128,
    "batch_size": 32,
    "epochs": 4,
    "lr": 2e-5,
    "llrd_decay": 0.9,
    "weight_decay": 0.01,
    "warmup_frac": 0.10,
    "unfreeze_top": 3,
    "num_classes": 3,
    "use_amp": True,
    "focal_gamma": 0.0,
    "label_smoothing": 0.0,
    "pooling": "cls",
    "head_dropout": 0.1,
    "schedule": "linear",
}

CONFIGS = {
    "base": {},
    "focal": {"epochs": 8, "focal_gamma": 2.0},
    "focal_cosine": {"epochs": 8, "focal_gamma": 2.0, "schedule": "cosine"},
    "focal_smoothing": {"epochs": 8, "focal_gamma": 2.0, "label_smoothing": 0.1},
    "focal_cosine_smoothing": {
        "epochs": 8, "focal_gamma": 2.0, "schedule": "cosine", "label_smoothing": 0.1,
    },
    "focal_meanpool": {"epochs": 8, "focal_gamma": 2.0, "pooling": "mean"},
    "focal_meanpool_smoothing": {
        "epochs": 8, "focal_gamma": 2.0, "pooling": "mean", "label_smoothing": 0.1,
    },
    "combined": {
        "epochs": 8, "focal_gamma": 2.0, "label_smoothing": 0.1,
        "pooling": "mean", "schedule": "cosine",
    },
}


def load_data(data_dir):
    dfs = {}
    for name in ("train", "val", "test"):
        df = pd.read_csv(f"{data_dir}/{name}.csv")
        before = len(df)
        df.dropna(subset=["question", "level"], inplace=True)
        df["level"] = df["level"].str.lower().str.strip()
        df.drop(df[~df["level"].isin(LABEL_TO_ID.keys())].index, inplace=True)
        print(f"  {name}: {len(df)}/{before} after cleaning")
        dfs[name] = df
    return dfs["train"], dfs["val"], dfs["test"]


def make_loaders(train_df, val_df, test_df, tokenizer, config):
    train_ds = BloomDataset(train_df, tokenizer, config["max_len"])
    val_ds = BloomDataset(val_df, tokenizer, config["max_len"])
    test_ds = BloomDataset(test_df, tokenizer, config["max_len"])
    train_loader = DataLoader(train_ds, batch_size=config["batch_size"], shuffle=True, num_workers=2, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=config["batch_size"], shuffle=False, num_workers=2, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=config["batch_size"], shuffle=False, num_workers=2, pin_memory=True)
    return train_loader, val_loader, test_loader


def compute_class_weights(train_df, num_classes, device):
    counts = train_df["level"].value_counts()
    total = counts.sum()
    weights = {l: total / (num_classes * counts[l]) for l in counts.index}
    return torch.tensor(
        [weights[ID_TO_LABEL[i]] for i in range(num_classes)],
        dtype=torch.float, device=device,
    )


def build_llrd_parameter_groups(model, base_lr, decay, weight_decay):
    no_decay_names = ("bias", "LayerNorm.weight", "LayerNorm.bias")
    groups = []
    for layer_idx in range(6):
        depth_from_top = 5 - layer_idx
        lr = base_lr * (decay ** depth_from_top)
        prefix = f"encoder.transformer.layer.{layer_idx}."
        decay_params, nodecay_params = [], []
        for n, p in model.named_parameters():
            if not p.requires_grad or not n.startswith(prefix):
                continue
            if any(nd in n for nd in no_decay_names):
                nodecay_params.append(p)
            else:
                decay_params.append(p)
        if decay_params:
            groups.append({"params": decay_params, "lr": lr, "weight_decay": weight_decay})
        if nodecay_params:
            groups.append({"params": nodecay_params, "lr": lr, "weight_decay": 0.0})

    head_decay, head_nodecay = [], []
    for n, p in model.named_parameters():
        if not p.requires_grad:
            continue
        if "classifier" not in n and "pre_classifier" not in n:
            continue
        if any(nd in n for nd in no_decay_names):
            head_nodecay.append(p)
        else:
            head_decay.append(p)
    if head_decay:
        groups.append({"params": head_decay, "lr": base_lr, "weight_decay": weight_decay})
    if head_nodecay:
        groups.append({"params": head_nodecay, "lr": base_lr, "weight_decay": 0.0})
    return groups


def make_scheduler(config, optimizer, warmup_steps, total_steps):
    if config.get("schedule", "linear") == "cosine":
        return get_cosine_schedule_with_warmup(optimizer, warmup_steps, total_steps)
    return get_linear_schedule_with_warmup(optimizer, warmup_steps, total_steps)


def train_one_epoch(model, loader, optimizer, scheduler, loss_fn, scaler, config, device):
    model.train()
    total_loss = 0.0
    for batch in loader:
        optimizer.zero_grad()
        input_ids = batch["input_ids"].to(device, non_blocking=True)
        attn_mask = batch["attention_mask"].to(device, non_blocking=True)
        labels = batch["labels"].to(device, non_blocking=True)
        if config["use_amp"]:
            with autocast():
                logits = model(input_ids, attn_mask)
                loss = loss_fn(logits, labels)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            scaler.step(optimizer)
            scaler.update()
        else:
            logits = model(input_ids, attn_mask)
            loss = loss_fn(logits, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
        scheduler.step()
        total_loss += loss.item()
    return total_loss / len(loader)


@torch.no_grad()
def evaluate(model, loader, loss_fn, config, device):
    model.eval()
    total_loss = 0.0
    preds, gold = [], []
    for batch in loader:
        input_ids = batch["input_ids"].to(device, non_blocking=True)
        attn_mask = batch["attention_mask"].to(device, non_blocking=True)
        labels = batch["labels"].to(device, non_blocking=True)
        if config["use_amp"]:
            with autocast():
                logits = model(input_ids, attn_mask)
        else:
            logits = model(input_ids, attn_mask)
        total_loss += loss_fn(logits.float(), labels).item()
        preds.extend(logits.argmax(dim=-1).cpu().tolist())
        gold.extend(labels.cpu().tolist())
    macro = f1_score(gold, preds, average="macro")
    return total_loss / len(loader), macro, preds, gold


def save_test_artifacts(out_dir, preds, gold, test_loss, test_f1, history, config, df_for_questions=None):
    os.makedirs(out_dir, exist_ok=True)
    target_names = ["easy", "medium", "hard"]

    with open(f"{out_dir}/training_history.json", "w") as f:
        json.dump({
            "history": history,
            "test_macro_f1": test_f1,
            "test_loss": test_loss,
            "config": config,
        }, f, indent=2)

    text_report = classification_report(gold, preds, target_names=target_names, digits=4)
    with open(f"{out_dir}/test_classification_report.txt", "w") as f:
        f.write(f"TEST macro_f1 = {test_f1:.4f}   loss = {test_loss:.4f}\n\n")
        f.write(text_report)
    dict_report = classification_report(gold, preds, target_names=target_names, digits=4, output_dict=True)
    with open(f"{out_dir}/test_classification_report.json", "w") as f:
        json.dump(dict_report, f, indent=2)

    cm = confusion_matrix(gold, preds)
    with open(f"{out_dir}/test_confusion_matrix.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["true \\ pred"] + target_names)
        for i, row in enumerate(cm):
            w.writerow([target_names[i]] + list(row))

    with open(f"{out_dir}/test_predictions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "question", "true_level", "predicted_level", "correct", "source"])
        questions = df_for_questions["question"].tolist() if df_for_questions is not None else [""] * len(gold)
        sources = df_for_questions["source"].tolist() if (df_for_questions is not None and "source" in df_for_questions.columns) else [""] * len(gold)
        for i, (q, t, p) in enumerate(zip(questions, gold, preds)):
            w.writerow([i, q, target_names[t], target_names[p], "yes" if t == p else "no",
                        sources[i] if i < len(sources) else ""])

    with open(f"{out_dir}/label_map.json", "w") as f:
        json.dump(LABEL_TO_ID, f, indent=2)


def run_training(config, device, tokenizer, loaders, class_weights, test_df, out_dir, save=True):
    train_loader, val_loader, test_loader = loaders
    model = build_model(config, device)
    loss_fn = make_loss(config, class_weights)
    optimizer = torch.optim.AdamW(
        build_llrd_parameter_groups(model, config["lr"], config["llrd_decay"], config["weight_decay"])
    )
    total_steps = len(train_loader) * config["epochs"]
    warmup_steps = int(total_steps * config["warmup_frac"])
    scheduler = make_scheduler(config, optimizer, warmup_steps, total_steps)
    scaler = GradScaler(enabled=config["use_amp"])

    history = []
    best_f1, best_state = -1.0, None
    for epoch in range(1, config["epochs"] + 1):
        train_loss = train_one_epoch(model, train_loader, optimizer, scheduler, loss_fn, scaler, config, device)
        val_loss, val_f1, _, _ = evaluate(model, val_loader, loss_fn, config, device)
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss, "val_macro_f1": val_f1})
        print(f"  epoch {epoch}/{config['epochs']}   train_loss={train_loss:.4f}   val_loss={val_loss:.4f}   val_macro_f1={val_f1:.4f}")
        if val_f1 > best_f1:
            best_f1 = val_f1
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)
    test_loss, test_f1, preds, gold = evaluate(model, test_loader, loss_fn, config, device)
    print(f"\nTEST  macro_f1={test_f1:.4f}   loss={test_loss:.4f}")
    print(classification_report(gold, preds, target_names=["easy", "medium", "hard"], digits=4))
    print("Confusion matrix (rows=true, cols=pred):  easy / medium / hard")
    print(confusion_matrix(gold, preds))

    if save:
        os.makedirs(out_dir, exist_ok=True)
        torch.save({"state_dict": model.state_dict(), "config": config, "test_macro_f1": test_f1},
                   f"{out_dir}/model_state.pt")
        export_hf_copy(model, out_dir, tokenizer, config)
        save_test_artifacts(out_dir, preds, gold, test_loss, test_f1, history, config, df_for_questions=test_df)
        print(f"\nSaved model + tokenizer + report artifacts to {out_dir}")
    return test_f1, history


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="base", choices=list(CONFIGS.keys()))
    ap.add_argument("--data-dir", default=os.environ.get("BLOOM_DATA_DIR", str(ROOT / "data" / "processed")))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--ablation", action="store_true",
                    help="for the base variant, also sweep unfreeze_top in {1,2,3}")
    args = ap.parse_args()

    config = dict(DEFAULTS)
    config.update(CONFIGS[args.variant])
    out_dir = args.out_dir or str(ROOT / "models" / f"bloom_distilbert_{args.variant}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", device)
    print("Variant:", args.variant, "->", {k: config[k] for k in ("epochs", "focal_gamma", "label_smoothing", "pooling", "schedule")})

    train_df, val_df, test_df = load_data(args.data_dir)
    tokenizer = DistilBertTokenizerFast.from_pretrained(config["model_name"])
    loaders = make_loaders(train_df, val_df, test_df, tokenizer, config)
    class_weights = compute_class_weights(train_df, config["num_classes"], device)
    print("Class weights:", {ID_TO_LABEL[i]: round(class_weights[i].item(), 3) for i in range(config["num_classes"])})

    test_f1, _ = run_training(config, device, tokenizer, loaders, class_weights, test_df, out_dir, save=True)

    if args.variant == "base" and args.ablation:
        results = {config["unfreeze_top"]: test_f1}
        for ut in (1, 2, 3):
            if ut == config["unfreeze_top"]:
                continue
            print(f"\n=== Ablation: unfreezing top {ut} layer(s) ===")
            c = dict(config)
            c["unfreeze_top"] = ut
            f1, _ = run_training(c, device, tokenizer, loaders, class_weights, test_df, out_dir, save=False)
            results[ut] = f1
        print("\n=== Ablation summary (unfrozen top layers -> test macro-F1) ===")
        for ut in sorted(results):
            print(f"  {ut} layer(s):  {results[ut]:.4f}")
        with open(f"{out_dir}/ablation_results.json", "w") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
