"""
unified schema for all question sources:
    question   (str)
    level      ("easy" , "medium" , "hard")
    bloom level  (BTL)     (1..6)
    source     (str)

label normalization:
    BTL-1/2 / Remember/Understand / "remember"/"understand"  -> easy / btl=1 or 2
    BTL-3/4 / Apply/Analyze                                  -> medium
    BTL-5/6 / Evaluate/Create                                -> hard
    
config file tells how to read each source and deduplication of questions across
the whole final set is done

run command:
    python3 scripts/build_training_set.py
    
outputs:
    data/processed/train.csv
    data/processed/val.csv
    data/processed/test.csv
    data/processed/merge_report.txt
"""
from __future__ import annotations
import csv
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
EXT_DIR = ROOT / "data" / "raw_external"

SEED = 42 # we chose this for all randomizations tasks in this module 
TRAIN_SPLIT, VAL_SPLIT = 0.80, 0.10  # and test gets the remaining 0.10

# label normalization
NAME_TO_BTL = {
    "remember": 1, "remembering": 1, "knowledge": 1, "recall": 1,
    "understand": 2, "understanding": 2, "comprehension": 2,
    "apply": 3, "applying": 3, "application": 3,
    "analyze": 4, "analyse": 4, "analyzing": 4, "analysing": 4, "analysis": 4,
    "evaluate": 5, "evaluating": 5, "evaluation": 5,
    "create": 6, "creating": 6, "synthesis": 6, "synthesise": 6, "synthesize": 6, "design": 6, "designing": 6,
}
BTL_TO_LEVEL = {1: "easy", 2: "easy", 3: "medium", 4: "medium", 5: "hard", 6: "hard"}


def label_to_btl(label: str) -> int | None:
    """normalize any common bloom-level encoding to BTL number 1..6"""
    if label is None:
        return None
    label = str(label).strip().lower()
    if not label:
        return None
    # "BTL-N", "BTL N", "BT-N", "BTN" — any of these forms we noticed in the sources we uploaded 
    matched_BTL = re.search(r"bt[l]?[\s\-_]?([1-6])", label)
    if matched_BTL:
        return int(matched_BTL.group(1))
    # just digit 1-6
    if label in {"1", "2", "3", "4", "5", "6"}:
        return int(label)
    # bloom level name
    for word, btl in NAME_TO_BTL.items():
        if word in label:
            return btl
    return None

EXTERNAL_CONFIGS: list[dict] = [
    {
        "filename": "devane.csv",
        "question_col": None,  
        "label_col": None,      # detect first col containing "level"/"category"/"bloom"
        "source_tag": "devane",
    },
]


def normalize_question(question: str) -> str:
    question = re.sub(r"\s+", " ", question).strip().lower()
    question = re.sub(r"^\d+[\.\-\)]\s*", "", question)
    return question


def autodetect_column(header: list[str], *patterns: str) -> str | None:
    for col in header:
        low = col.lower()
        if any(p in low for p in patterns):
            return col
    return None


def load_external(cfg: dict) -> list[dict]:
    path = EXT_DIR / cfg["filename"]
    if not path.exists():
        print(f"  [skip] {cfg['filename']} not found in {EXT_DIR}")
        return []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        rdr = csv.DictReader(f)
        header = rdr.fieldnames or []
        q_col = cfg["question_col"] or autodetect_column(header, "quest", "text", "sentence")
        l_col = cfg["label_col"] or autodetect_column(header, "level", "bloom", "categor", "label", "class")
        if not q_col or not l_col:
            print(f"  [warn] could not detect question/label columns in {cfg['filename']}")
            print(f"         header was: {header}")
            return []
        rows = []
        for r in rdr:
            q = (r.get(q_col) or "").strip()
            btl = label_to_btl(r.get(l_col) or "")
            if not q or btl is None or len(q) < 8:
                continue
            rows.append({
                "question": q,
                "level": BTL_TO_LEVEL[btl],
                "btl": btl,
                "source": cfg["source_tag"],
            })
        print(f"  [{cfg['source_tag']:>10}] loaded {len(rows)} rows  (cols: {q_col!r} / {l_col!r})")
        return rows


def load_srm() -> list[dict]:
    path = PROC / "srm_questions.csv"
    if not path.exists():
        print(f"{path} not found , run parse_srm_question_bank.py first")
        sys.exit(1)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            btl = int(r["btl"])
            rows.append({
                "question": r["question"],
                "level": r["level"],
                "btl": btl,
                "source": "srm",
            })
    # check count 
    print(f"srm loaded {len(rows)} rows")
    return rows


def split_data(rows: list[dict], TRAIN_SPLIT: float, VAL_SPLIT: float,
                    seed: int) -> tuple[list, list, list]:
    """
    we avoid two data leakage and failure modes:
    1. source bias — one source dominates one split (like all SRM in train) so 
    the model learns source style, not Bloom level.
    2. class imbalance per split.
    we split by bucket(source, level), split each bucket 80/10/10, then concatenate.
    """
    random_generator = random.Random(seed)
    by_bucket: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_bucket[(row["source"], row["level"])].append(row)

    train, val, test = [], [], []
    for (src, level), items in sorted(by_bucket.items()):
        random_generator.shuffle(items)
        n = len(items)
        n_train = int(n * TRAIN_SPLIT)
        n_val = int(n * VAL_SPLIT)
        train.extend(items[:n_train])
        val.extend(items[n_train:n_train + n_val])
        test.extend(items[n_train + n_val:])
    random_generator.shuffle(train)
    random_generator.shuffle(val)
    random_generator.shuffle(test)
    return train, val, test


def write_split(name: str, rows: list[dict]) -> Path:
    out = PROC / f"{name}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["question", "level", "btl", "source"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in ["question", "level", "btl", "source"]})
    return out


def main() -> int:
    all_rows: list[dict] = []
    all_rows.extend(load_srm())
    for config in EXTERNAL_CONFIGS:
        all_rows.extend(load_external(config))

    if not all_rows:
        print("No data loaded — aborting", file=sys.stderr)
        return 1

    # dedupe across all sources 
    print(f"\nDeduplicating {len(all_rows)} total rows")
    seen: dict[str, dict] = {}
    duplications = 0
    for row in all_rows:
        key = normalize_question(r["question"])
        if not key:
            continue
        if key in seen:
            duplications += 1
            # we prefer srm labels (educator-assigned) over external sources
            if seen[key]["source"] != "srm" and r["source"] == "srm":
                seen[key] = row
            continue
        seen[key] = row
    deduped = list(seen.values())

    # first split 
    train, val, test = split_data(deduped, TRAIN_SPLIT, VAL_SPLIT, SEED)
    write_split("train", train)
    write_split("val", val)
    write_split("test", test)

    # then report 
    src_counts = Counter(r["source"] for r in deduped)
    lines = []
    lines.append("Training set build report")
    lines.append(f"Total unique rows:     {len(deduped)}")
    lines.append(f"Duplicates removed:    {duplications}")
    lines.append("")
    lines.append("Per-source counts (post-dedup):")
    for src, n in src_counts.most_common():
        lines.append(f"  {src:<12} {n}")
    lines.append("")
    # logging per split 
    for split_name, split_rows in (("train", train), ("val", val), ("test", test)):
        lines.append(f"{split_name} (n={len(split_rows)})")

        src_dist = Counter(r["source"] for r in split_rows)
        for src, n in sorted(src_dist.items()):
            pct = 100.0 * n / max(1, len(split_rows))
            lines.append(f"  source={src:<10} {n:>6} ({pct:5.1f}%)")

        lvl_dist = Counter(r["level"] for r in split_rows)
        for lvl in ("easy", "medium", "hard"):
            n = lvl_dist[lvl]
            pct = 100.0 * n / max(1, len(split_rows))
            lines.append(f"  level={lvl:<7} {n:>6} ({pct:5.1f}%)")

        lines.append(f"  source x level:")
        crosstab: dict[tuple[str, str], int] = Counter()
        for r in split_rows:
            crosstab[(r["source"], r["level"])] += 1
        for (src, lvl), n in sorted(crosstab.items()):
            lines.append(f"    {src:<10} {lvl:<7} {n:>6}")
        lines.append("")
    lines.append(f"outputs: {PROC}/train.csv, val.csv, test.csv")
    report = PROC / "merge_report.txt"
    report.write_text("\n".join(lines))
    print("\n" + "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
