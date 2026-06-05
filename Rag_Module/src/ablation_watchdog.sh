#!/bin/bash
# ============================================================================
# Ablation watchdog — self-healing overnight runner
# ----------------------------------------------------------------------------
# Runs the rag_mixed ablation ONE CONFIG AT A TIME so it regains control after
# each. On a config failure (key exhausted / error / EvalSR<1), it rotates to
# the backup Cerebras key and retries (up to MAX_ATTEMPTS across both keys).
# Resumable: ab_run.py skips configs already saved with overall>0.
# Writes a human-readable progress log + a FINAL_SUMMARY block at the end.
# ============================================================================
set -u
cd /Users/manarfarghaly/Desktop/Data/senior2firstterm/GP/BayLearn/Rag_Module/src

LOG=ablation_watchdog.log
PRIMARY_KEY="$(grep '^OPENAI_COMPAT_API_KEY=' .env | cut -d= -f2-)"
BACKUP_KEY="csk-88jccpytpexd9t8djhe3f8kp4tdn6pemt5rjrx33dktw6vtw"
KEYS=("$PRIMARY_KEY" "$BACKUP_KEY")
KEY_IDX=0
MAX_ATTEMPTS=4

# rag_mixed ladder (+contextual skipped — no rag_mixed_ctx collection built)
CONFIGS=("baseline" "baseline+hyde" "rag_fusion" "+hybrid" "+reranker" "+compression")

ts() { date '+%Y-%m-%d %H:%M:%S'; }
say() { echo "[$(ts)] $*" | tee -a "$LOG"; }

set_key() {
  # Rewrite the OPENAI_COMPAT_API_KEY line in .env (portable sed on macOS)
  local k="$1"
  python3 - "$k" <<'PY'
import sys, re
key = sys.argv[1]
p = ".env"
lines = open(p).read().splitlines()
out = []
done = False
for ln in lines:
    if ln.startswith("OPENAI_COMPAT_API_KEY="):
        out.append("OPENAI_COMPAT_API_KEY=" + key); done = True
    else:
        out.append(ln)
if not done:
    out.append("OPENAI_COMPAT_API_KEY=" + key)
open(p, "w").write("\n".join(out) + "\n")
PY
}

is_done() {
  # Exit 0 if the given config is saved with overall>0 AND eval_success_rate>=0.85
  python3 - "$1" <<'PY'
import json, sys
cfg = sys.argv[1]
key = f"networks@rag_mixed::{cfg}"
try:
    d = json.load(open("ablation_results.json"))
except Exception:
    sys.exit(1)
r = d.get(key, {})
s = r.get("scores", {})
ok = s.get("overall", 0) > 0 and s.get("eval_success_rate", 0) >= 0.85
sys.exit(0 if ok else 1)
PY
}

drop_entry() {
  # Remove a config's saved entry so ab_run.py actually RE-RUNS it instead of
  # skipping (ab_run skips any config already saved with overall>0). Without
  # this, a config saved with a low EvalSR could never be retried.
  python3 - "$1" <<'PY'
import json, sys
cfg = sys.argv[1]
try:
    d = json.load(open("ablation_results.json"))
except Exception:
    sys.exit(0)
for k in (f"networks@rag_mixed::{cfg}", f"os_threads@rag_mixed::{cfg}"):
    d.pop(k, None)
json.dump(d, open("ablation_results.json", "w"), indent=2)
PY
}

cur_key_tag() { echo "...${KEYS[$KEY_IDX]: -6}"; }

say "==================== WATCHDOG START ===================="
say "Configs to run: ${CONFIGS[*]}"
say "Starting on key $(cur_key_tag)"

for cfg in "${CONFIGS[@]}"; do
  if is_done "$cfg"; then
    say "SKIP '$cfg' (already complete)."
    continue
  fi
  attempt=0
  while (( attempt < MAX_ATTEMPTS )); do
    attempt=$((attempt+1))
    set_key "${KEYS[$KEY_IDX]}"
    drop_entry "$cfg"   # force a real re-run (don't let ab_run skip a low-EvalSR save)
    say "RUN '$cfg' — attempt $attempt/$MAX_ATTEMPTS on key $(cur_key_tag)"
    AB_Q_TIMEOUT=240 PYTHONPATH=. caffeinate -i .venv/bin/python ablation/ab_run.py \
      --dataset networks --collection rag_mixed --per-level --config "$cfg" >> "$LOG" 2>&1
    rc=$?
    if is_done "$cfg"; then
      say "DONE '$cfg' ✓ (rc=$rc)"
      break
    fi
    say "FAIL '$cfg' (rc=$rc, not saved or EvalSR<0.9). Rotating key."
    KEY_IDX=$(( (KEY_IDX + 1) % ${#KEYS[@]} ))
    say "Switched to key $(cur_key_tag). Cooling down 45s before retry."
    sleep 45
  done
  if ! is_done "$cfg"; then
    say "GIVE UP on '$cfg' after $MAX_ATTEMPTS attempts. Moving on."
  fi
done

# ---- Restore primary key in .env so the app default is unchanged ----
set_key "$PRIMARY_KEY"

# ---- Final summary ----
say "==================== ABLATION FINISHED ===================="
python3 - <<'PY' | tee -a "$LOG"
import json
try:
    d = json.load(open("ablation_results.json"))
except Exception as e:
    print("Could not read results:", e); raise SystemExit
print("\n========== FINAL_SUMMARY (rag_mixed) ==========")
hdr = f"{'config':<16} {'Faith':>6} {'Relev':>6} {'Prec':>6} {'Recall':>6} {'Overall':>8} {'EvalSR':>7}"
print(hdr); print("-"*len(hdr))
order = ["baseline","baseline+hyde","rag_fusion","+hybrid","+reranker","+compression"]
for cfg in order:
    k = f"networks@rag_mixed::{cfg}"
    if k not in d:
        print(f"{cfg:<16}  (not run)"); continue
    s = d[k]["scores"]
    nc = s.get("none_counts", {})
    print(f"{cfg:<16} {s.get('Faithfulness',0):>6.3f} {s.get('AnswerRelevancy',0):>6.3f} "
          f"{s.get('ContextPrecision',0):>6.3f} {s.get('ContextRecall',0):>6.3f} "
          f"{s.get('overall',0):>8.3f} {s.get('eval_success_rate',0):>7.3f}")
    if any(v>0 for v in nc.values()):
        print(f"{'':16}  ^ judge failures: {nc}")
print("\nEvalSR=1.000 means all 7 questions scored on all 4 metrics (valid comparison).")
done = [c for c in order if f"networks@rag_mixed::{c}" in d
        and d[f"networks@rag_mixed::{c}"]["scores"].get("overall",0)>0]
print(f"\nCompleted {len(done)}/6 configs: {done}")
PY
say "WATCHDOG DONE. Wrote FINAL_SUMMARY above."
# Marker file so a quick check tells the whole story
echo "WATCHDOG_COMPLETED_AT=$(ts)" > ablation_watchdog.DONE
