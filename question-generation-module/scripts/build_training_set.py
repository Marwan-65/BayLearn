"""
Merge SRM + external Bloom datasets into unified train/val/test CSVs.

External datasets (e.g. Devane Kaggle, Gotmare Kaggle, Mohammed, Yahya) come in
different column names and label encodings. We map them to one shared schema:

    Unified schema:
        question   (str)
        level      ("easy" | "medium" | "hard")
        btl        (1..6)
        source     (str — origin label like "srm", "devane", ...)

Label normalization:
    BTL-1/2 / Remember/Understand / "remember"/"understand"  → easy / btl=1 or 2
    BTL-3/4 / Apply/Analyze                                  → medium
    BTL-5/6 / Evaluate/Create                                → hard

Config below tells the merger HOW to read each external CSV.
After merging, dedupe by normalized question text and stratified-split 80/10/10.

Run:
    python3 scripts/build_training_set.py
Outputs:
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

SEED = 42
TRAIN_FRAC, VAL_FRAC = 0.80, 0.10  # test gets the remaining 0.10

# ---- Label normalization ----------------------------------------------------
NAME_TO_BTL = {
    "remember": 1, "remembering": 1, "knowledge": 1, "recall": 1,
    "understand": 2, "understanding": 2, "comprehension": 2,
    "apply": 3, "applying": 3, "application": 3,
    "analyze": 4, "analyse": 4, "analyzing": 4, "analysing": 4, "analysis": 4,
    "evaluate": 5, "evaluating": 5, "evaluation": 5,
    "create": 6, "creating": 6, "synthesis": 6, "synthesise": 6, "synthesize": 6,
}
BTL_TO_LEVEL = {1: "easy", 2: "easy", 3: "medium", 4: "medium", 5: "hard", 6: "hard"}


def label_to_btl(raw: str) -> int | None:
    """Normalize any common Bloom-level encoding to BTL number 1..6."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    # "BTL-N", "BTL N", "BT-N", "BTN" — any of these forms
    m = re.search(r"bt[l]?[\s\-_]?([1-6])", s)
    if m:
        return int(m.group(1))
    # Bare digit 1-6
    if s in {"1", "2", "3", "4", "5", "6"}:
        return int(s)
    # Bloom level name
    for word, btl in NAME_TO_BTL.items():
        if word in s:
            return btl
    return None


# ---- External dataset configs -----------------------------------------------
# Each entry: filename (in data/raw_external/), question column, label column.
# If a dataset has a question_type column we can also skip non-questions.
# Edit this list as you add datasets — re-running the script picks them up.
EXTERNAL_CONFIGS: list[dict] = [
    {
        "filename": "devane.csv",
        "question_col": None,   # auto-detect: first col containing "quest"
        "label_col": None,      # auto-detect: first col containing "level"/"category"/"bloom"
        "source_tag": "devane",
    },
    # Gotmare excluded: verified 99.6% byte-identical overlap with Devane (1845/1852).
    # The 7 "unique" rows had empty fields. Keep the file in raw_external/ for
    # provenance; do not feed it to the merger.
]


# ---- Helpers ----------------------------------------------------------------
def normalize_question(q: str) -> str:
    q = re.sub(r"\s+", " ", q).strip().lower()
    q = re.sub(r"^\d+[\.\-\)]\s*", "", q)
    return q


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
        print(f"  [FATAL] {path} not found — run parse_srm_question_bank.py first")
        sys.exit(1)
    with path.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        rows = []
        for r in rdr:
            btl = int(r["btl"])
            rows.append({
                "question": r["question"],
                "level": r["level"],
                "btl": btl,
                "source": "srm",
            })
    print(f"  [       srm] loaded {len(rows)} rows")
    return rows


def stratified_split(rows: list[dict], train_frac: float, val_frac: float,
                     seed: int) -> tuple[list, list, list]:
    """Per-source AND per-level stratified split.

    Avoids two failure modes:
      1. Source bias — one source dominates one split (e.g., all SRM in train,
         all Devane in test) so the model learns source style, not Bloom level.
      2. Class imbalance per split — already protected.

    We bucket by (source, level), split each bucket 80/10/10, concatenate.
    """
    rng = random.Random(seed)
    by_bucket: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by_bucket[(r["source"], r["level"])].append(r)

    train, val, test = [], [], []
    for (src, lvl), items in sorted(by_bucket.items()):
        rng.shuffle(items)
        n = len(items)
        n_train = int(n * train_frac)
        n_val = int(n * val_frac)
        train.extend(items[:n_train])
        val.extend(items[n_train:n_train + n_val])
        test.extend(items[n_train + n_val:])
    rng.shuffle(train); rng.shuffle(val); rng.shuffle(test)
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
    print("Loading datasets...")
    all_rows: list[dict] = []
    all_rows.extend(load_srm())
    for cfg in EXTERNAL_CONFIGS:
        all_rows.extend(load_external(cfg))

    if not all_rows:
        print("No data loaded — aborting", file=sys.stderr)
        return 1

    # ---- Dedupe across all sources ------------------------------------------
    print(f"\nDeduplicating {len(all_rows)} total rows...")
    seen: dict[str, dict] = {}
    dup = 0
    for r in all_rows:
        key = normalize_question(r["question"])
        if not key:
            continue
        if key in seen:
            dup += 1
            # Prefer SRM labels (educator-assigned) over external sources
            if seen[key]["source"] != "srm" and r["source"] == "srm":
                seen[key] = r
            continue
        seen[key] = r
    deduped = list(seen.values())
    print(f"  removed {dup} duplicates → {len(deduped)} unique rows")

    # ---- Split ---------------------------------------------------------------
    train, val, test = stratified_split(deduped, TRAIN_FRAC, VAL_FRAC, SEED)
    write_split("train", train)
    write_split("val", val)
    write_split("test", test)

    # ---- Report --------------------------------------------------------------
    src_counts = Counter(r["source"] for r in deduped)
    lines = []
    lines.append("Training set build report")
    lines.append("=========================")
    lines.append(f"Total unique rows:     {len(deduped)}")
    lines.append(f"Duplicates removed:    {dup}")
    lines.append("")
    lines.append("Per-source counts (post-dedup):")
    for src, n in src_counts.most_common():
        lines.append(f"  {src:<12} {n}")
    lines.append("")
    # Per-split: show source x level cross-tab to prove no leakage
    for split_name, split_rows in (("train", train), ("val", val), ("test", test)):
        lines.append(f"=== {split_name} (n={len(split_rows)}) ===")
        # Source proportions
        src_dist = Counter(r["source"] for r in split_rows)
        for src, n in sorted(src_dist.items()):
            pct = 100.0 * n / max(1, len(split_rows))
            lines.append(f"  source={src:<10} {n:>6} ({pct:5.1f}%)")
        # Level proportions
        lvl_dist = Counter(r["level"] for r in split_rows)
        for lvl in ("easy", "medium", "hard"):
            n = lvl_dist[lvl]
            pct = 100.0 * n / max(1, len(split_rows))
            lines.append(f"  level={lvl:<7} {n:>6} ({pct:5.1f}%)")
        # Source x level cross-tab
        lines.append(f"  source x level:")
        crosstab: dict[tuple[str, str], int] = Counter()
        for r in split_rows:
            crosstab[(r["source"], r["level"])] += 1
        for (src, lvl), n in sorted(crosstab.items()):
            lines.append(f"    {src:<10} {lvl:<7} {n:>6}")
        lines.append("")
    lines.append(f"Outputs: {PROC}/train.csv, val.csv, test.csv")
    report = PROC / "merge_report.txt"
    report.write_text("\n".join(lines))
    print("\n" + "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
