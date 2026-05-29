"""
eppo_inference.py
=================
Launched by backend.py with CLI args:

    python eppo_inference.py \
        --user-id 3 \
        --session-id 47 \
        --scope-type course \
        --scope-value "algorithms,data structures"

    python eppo_inference.py \
        --user-id 3 \
        --session-id 48 \
        --scope-type files \
        --scope-value "uuid-1,uuid-2,uuid-3"

scope-value is always comma-separated — supports multiple courses or files.

Static config in .env:
    CONCEPT_DB_URL
    QUESTION_API_URL    (default: http://localhost:5000/generate)
    ANSWER_API_URL      (default: http://localhost:5000/answer)

Dependencies:
    pip install torch sentence-transformers==2.7.0 transformers==4.40.2
                huggingface-hub==0.23.4 numpy requests sqlalchemy
                psycopg2-binary python-dotenv
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from dotenv import load_dotenv
from torch.distributions import Categorical
from sentence_transformers import SentenceTransformer
from sqlalchemy import Column, Integer, String, Float, Boolean, \
    DateTime, create_engine, text
from sqlalchemy.orm import declarative_base, Session
import requests

load_dotenv(Path(__file__).parent / ".env")
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Static config
# ---------------------------------------------------------------------------
CONCEPT_DB_URL   = os.environ.get("CONCEPT_DB_URL", "").strip()
QUESTION_API_URL = os.environ.get("QUESTION_API_URL",
                                  "http://localhost:5000/generate")
ANSWER_API_URL   = os.environ.get("ANSWER_API_URL",
                                  "http://localhost:5000/answer")
MODEL_PATH       = os.path.join(os.path.dirname(__file__),
                                "models", "eppo_latest_model.pt")

if not CONCEPT_DB_URL:
    print("ERROR: CONCEPT_DB_URL not set in .env", file=sys.stderr)
    sys.exit(1)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {DEVICE}")

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------
_parser = argparse.ArgumentParser()
_parser.add_argument("--user-id",     type=int, required=True)
_parser.add_argument("--session-id",  type=int, required=True)
_parser.add_argument("--scope-type",  type=str, default="course",
                     choices=["course", "files"])
_parser.add_argument("--scope-value", type=str, default="")
_args = _parser.parse_args()

EPPO_USER_ID = _args.user_id
SESSION_ID   = _args.session_id
SCOPE_TYPE   = _args.scope_type
SCOPE_VALUE  = _args.scope_value

# Parsed lists for multi-value scopes
SCOPE_VALUES = [v.strip() for v in SCOPE_VALUE.split(",") if v.strip()]

# ---------------------------------------------------------------------------
# ORM base
# ---------------------------------------------------------------------------
_Base = declarative_base()

# ---------------------------------------------------------------------------
# DB bootstrap
# ---------------------------------------------------------------------------

def ensure_tables(db_url: str) -> None:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id         SERIAL PRIMARY KEY,
                email      VARCHAR NOT NULL UNIQUE,
                name       VARCHAR,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS courses (
                id          SERIAL PRIMARY KEY,
                name        VARCHAR NOT NULL UNIQUE,
                description TEXT,
                uploader_id INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS course_enrollments (
                user_id     INTEGER NOT NULL,
                course_id   INTEGER NOT NULL,
                enrolled_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, course_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS concepts (
                id         SERIAL PRIMARY KEY,
                course_id  INTEGER NOT NULL,
                name       VARCHAR NOT NULL,
                difficulty INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS concept_files (
                concept_id INTEGER NOT NULL,
                file_id    VARCHAR NOT NULL,
                PRIMARY KEY (concept_id, file_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                scope_type  VARCHAR,
                scope_value VARCHAR,
                started_at  TIMESTAMP NOT NULL DEFAULT NOW(),
                ended_at    TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS student_pfa_state (
                user_id    INTEGER NOT NULL,
                concept_id INTEGER NOT NULL,
                succ_easy  FLOAT NOT NULL DEFAULT 0,
                succ_med   FLOAT NOT NULL DEFAULT 0,
                succ_hard  FLOAT NOT NULL DEFAULT 0,
                fail_easy  FLOAT NOT NULL DEFAULT 0,
                fail_med   FLOAT NOT NULL DEFAULT 0,
                fail_hard  FLOAT NOT NULL DEFAULT 0,
                bonus_easy FLOAT NOT NULL DEFAULT 0,
                bonus_med  FLOAT NOT NULL DEFAULT 0,
                bonus_hard FLOAT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, concept_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS session_interactions (
                id           SERIAL PRIMARY KEY,
                session_id   INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                concept_id   INTEGER NOT NULL,
                difficulty   VARCHAR(10) NOT NULL,
                correct      BOOLEAN NOT NULL,
                p_before     FLOAT NOT NULL,
                p_after      FLOAT NOT NULL,
                p_hard_after FLOAT NOT NULL,
                created_at   TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))
        conn.commit()
    print("[db] All tables verified.")


# ---------------------------------------------------------------------------
# Concept pool — supports multiple courses or multiple files
# ---------------------------------------------------------------------------

def _load_concept_pool(db_url: str, user_id: int,
                       scope_type: str, scope_values: list[str]):
    """
    Load concepts based on scope.

    scope_type="course"  scope_values=["algorithms","data structures"]
        → concepts from ALL listed courses the user is enrolled in

    scope_type="files"   scope_values=["uuid-1","uuid-2","uuid-3"]
        → concepts linked to ANY of the listed files via concept_files

    Returns:
        global_concepts        list[str]
        global_llm_diff        list[int]
        global_concept_ids     list[int]
        course_concept_indices dict[str, list[int]]  — for reference/logging
    """
    engine = create_engine(db_url)
    with Session(engine) as session:

        if scope_type == "files" and scope_values:
            try:
                rows = session.execute(text("""
                    SELECT DISTINCT c.id, c.name, c.difficulty, co.name
                    FROM   concepts c
                    JOIN   courses  co ON co.id = c.course_id
                    JOIN   concept_files cf ON cf.concept_id = c.id
                    WHERE  cf.file_id = ANY(:ids)
                    ORDER  BY co.name, c.id
                """), {"ids": scope_values}).fetchall()
            except Exception as e:
                print(f"[eppo] concept_files lookup failed ({e}), "
                      "falling back to full enrolled-course pool.",
                      file=sys.stderr)
                rows = None
        else:
            rows = None

        if rows is None:
            # Course scope (or fallback) — get enrolled courses
            enrolled_ids = [
                r[0] for r in session.execute(
                    text("SELECT course_id FROM course_enrollments "
                         "WHERE user_id = :uid"),
                    {"uid": user_id},
                )
            ]
            if not enrolled_ids:
                print(f"[eppo] WARNING: user {user_id} has no enrolled courses.",
                      file=sys.stderr)
                return [], [], [], {}

            if scope_type == "course" and scope_values:
                # Filter to only the selected courses
                # Normalise: "data structures" and "data_structures" both match
                normalised = [v.lower().replace("_", " ")
                              for v in scope_values]
                rows = session.execute(text("""
                    SELECT c.id, c.name, c.difficulty, co.name
                    FROM   concepts c
                    JOIN   courses  co ON co.id = c.course_id
                    WHERE  c.course_id = ANY(:ids)
                      AND  LOWER(REPLACE(co.name, '_', ' ')) = ANY(:cnames)
                    ORDER  BY co.name, c.id
                """), {"ids": enrolled_ids,
                       "cnames": normalised}).fetchall()
            else:
                # All enrolled courses
                rows = session.execute(text("""
                    SELECT c.id, c.name, c.difficulty, co.name
                    FROM   concepts c
                    JOIN   courses  co ON co.id = c.course_id
                    WHERE  c.course_id = ANY(:ids)
                    ORDER  BY co.name, c.id
                """), {"ids": enrolled_ids}).fetchall()

    global_concepts: list[str]   = []
    global_llm_diff: list[int]   = []
    global_concept_ids: list[int] = []
    course_concept_indices: dict[str, list[int]] = {}

    for concept_id, name, diff, course_name in rows:
        idx = len(global_concepts)
        global_concepts.append(name)
        global_llm_diff.append(int(diff))
        global_concept_ids.append(concept_id)
        key = course_name.lower().replace(" ", "_")
        course_concept_indices.setdefault(key, []).append(idx)

    return (global_concepts, global_llm_diff,
            global_concept_ids, course_concept_indices)


print(f"[eppo] Loading concept pool  user={EPPO_USER_ID} "
      f"scope={SCOPE_TYPE}:[{SCOPE_VALUE}] ...")
(GLOBAL_CONCEPTS, GLOBAL_LLM_DIFF,
 GLOBAL_CONCEPT_IDS, COURSE_CONCEPT_INDICES) = _load_concept_pool(
    CONCEPT_DB_URL, EPPO_USER_ID, SCOPE_TYPE, SCOPE_VALUES)

N_GLOBAL = len(GLOBAL_CONCEPTS)
print(f"[eppo] Pool: {N_GLOBAL} concepts across "
      f"{len(COURSE_CONCEPT_INDICES)} courses: "
      f"{list(COURSE_CONCEPT_INDICES.keys())}")

if N_GLOBAL == 0:
    print("ERROR: No concepts found. Run concept_extractor first.",
          file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# PFA persistence
# ---------------------------------------------------------------------------

def load_pfa_history(db_url: str, user_id: int) -> dict | None:
    engine = create_engine(db_url)
    with Session(engine) as session:
        rows = session.execute(text("""
            SELECT concept_id,
                   succ_easy, succ_med, succ_hard,
                   fail_easy, fail_med, fail_hard,
                   bonus_easy, bonus_med, bonus_hard
            FROM   student_pfa_state
            WHERE  user_id = :uid
        """), {"uid": user_id}).fetchall()

    if not rows:
        return None

    id_to_idx = {cid: i for i, cid in enumerate(GLOBAL_CONCEPT_IDS)}
    successes = np.zeros((N_GLOBAL, 3), dtype=np.float32)
    failures  = np.zeros((N_GLOBAL, 3), dtype=np.float32)
    bonuses   = np.zeros((N_GLOBAL, 3), dtype=np.float32)

    loaded = 0
    for (cid, se, sm, sh, fe, fm, fh, be, bm, bh) in rows:
        idx = id_to_idx.get(cid)
        if idx is None:
            continue
        successes[idx] = [se, sm, sh]
        failures[idx]  = [fe, fm, fh]
        bonuses[idx]   = [be, bm, bh]
        loaded += 1

    print(f"[pfa] Loaded history for {loaded} concepts.")
    return {"successes": successes, "failures": failures, "bonuses": bonuses}


def save_pfa_history(db_url: str, user_id: int, tracker) -> None:
    engine = create_engine(db_url)
    now = datetime.utcnow()
    with Session(engine) as session:
        for idx, cid in enumerate(GLOBAL_CONCEPT_IDS):
            se, sm, sh = tracker.successes[idx].tolist()
            fe, fm, fh = tracker.failures[idx].tolist()
            be, bm, bh = tracker.propagation_bonus[idx].tolist()
            session.execute(text("""
                INSERT INTO student_pfa_state
                    (user_id, concept_id,
                     succ_easy, succ_med, succ_hard,
                     fail_easy, fail_med, fail_hard,
                     bonus_easy, bonus_med, bonus_hard,
                     updated_at)
                VALUES (:uid, :cid,
                        :se, :sm, :sh, :fe, :fm, :fh,
                        :be, :bm, :bh, :now)
                ON CONFLICT (user_id, concept_id) DO UPDATE SET
                    succ_easy  = EXCLUDED.succ_easy,
                    succ_med   = EXCLUDED.succ_med,
                    succ_hard  = EXCLUDED.succ_hard,
                    fail_easy  = EXCLUDED.fail_easy,
                    fail_med   = EXCLUDED.fail_med,
                    fail_hard  = EXCLUDED.fail_hard,
                    bonus_easy = EXCLUDED.bonus_easy,
                    bonus_med  = EXCLUDED.bonus_med,
                    bonus_hard = EXCLUDED.bonus_hard,
                    updated_at = EXCLUDED.updated_at
            """), dict(uid=user_id, cid=cid,
                       se=se, sm=sm, sh=sh,
                       fe=fe, fm=fm, fh=fh,
                       be=be, bm=bm, bh=bh, now=now))
        session.commit()
    print(f"[pfa] Saved state for {len(GLOBAL_CONCEPT_IDS)} concepts.")


def log_interaction(db_url: str, session_id: int, user_id: int,
                    concept_id: int, difficulty: str, correct: bool,
                    p_before: float, p_after: float,
                    p_hard_after: float) -> None:
    if session_id == 0:
        return
    engine = create_engine(db_url)
    with Session(engine) as session:
        session.execute(text("""
            INSERT INTO session_interactions
                (session_id, user_id, concept_id, difficulty,
                 correct, p_before, p_after, p_hard_after, created_at)
            VALUES
                (:sid, :uid, :cid, :diff,
                 :correct, :pb, :pa, :ph, :now)
        """), dict(sid=session_id, uid=user_id, cid=concept_id,
                   diff=difficulty, correct=correct,
                   pb=p_before, pa=p_after, ph=p_hard_after,
                   now=datetime.utcnow()))
        session.commit()


def mark_session_ended(db_url: str, session_id: int) -> None:
    if session_id == 0:
        return
    engine = create_engine(db_url)
    with Session(engine) as session:
        session.execute(text("""
            UPDATE sessions SET ended_at = NOW() WHERE id = :sid
        """), {"sid": session_id})
        session.commit()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class Config:
    N_LEVELS   = 3
    LEVEL_NAMES = ["Easy", "Medium", "Hard"]
    GAMMA_LEVEL = np.array([0.0330, 0.1494, 0.8884])
    RHO_LEVEL   = np.array([0.1444, 0.3433, 0.2331])
    BETA_LEVEL  = np.array([1.4333, 1.0389, 0.4271])
    LLM_BETA_SCALE = -0.4
    LLM_BETA_MID   = 3.0
    PFA_TOP_K  = 5
    PFA_ALPHA  = 0.04
    SIM_THRESHOLD  = 0.45
    MAX_STEPS      = 60
    CONCEPT_CAP    = 10
    IMPROVEMENT_PCT    = 0.07
    SESSION_DONE_BONUS = 10.0
    MASTERY_THRESHOLD  = 0.65
    EMBED_MODEL = "BAAI/bge-base-en-v1.5"
    EMBED_DIM   = 768
    STATE_DIM   = 19
    SCORER_IN   = 22
    HIDDEN_DIM  = 64
    ITEM_DIFFICULTY = np.array([0.0, 1.0, 2.2])
    HARD_FLOOR  = 0.40
    P_ONE_COURSE = 0.50
    DEVICE = DEVICE

cfg = Config()

# ---------------------------------------------------------------------------
# Embeddings + similarity graph
# ---------------------------------------------------------------------------
print(f"Loading {cfg.EMBED_MODEL} ...")
embed_model = SentenceTransformer(cfg.EMBED_MODEL)
print(f"Embedding {N_GLOBAL} concepts...")
global_embeddings = embed_model.encode(
    GLOBAL_CONCEPTS,
    normalize_embeddings=True,
    show_progress_bar=True,
    batch_size=64,
).astype(np.float32)

global_sim_matrix = global_embeddings @ global_embeddings.T

global_neighbours = []
for i in range(N_GLOBAL):
    s = global_sim_matrix[i].copy()
    s[i] = -1
    mask = s >= cfg.SIM_THRESHOLD
    top  = (np.where(mask)[0][np.argsort(-s[mask])[:cfg.PFA_TOP_K]]
            if mask.sum() > 0 else np.array([np.argmax(s)]))
    global_neighbours.append(top)

print(f"Embedding shape: {global_embeddings.shape}")


# ---------------------------------------------------------------------------
# PFA Tracker
# ---------------------------------------------------------------------------
def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -15, 15)))


class PFATracker:
    def __init__(self, cfg):
        self.cfg = cfg
        N, L = N_GLOBAL, cfg.N_LEVELS
        self.gamma_level  = cfg.GAMMA_LEVEL.copy()
        self.rho_level    = cfg.RHO_LEVEL.copy()
        self.beta_level   = cfg.BETA_LEVEL.copy()
        self.beta_concept = np.array(
            [(d - cfg.LLM_BETA_MID) * cfg.LLM_BETA_SCALE
             for d in GLOBAL_LLM_DIFF], dtype=np.float32)
        self.successes         = np.zeros((N, L), dtype=np.float32)
        self.failures          = np.zeros((N, L), dtype=np.float32)
        self.propagation_bonus = np.zeros((N, L), dtype=np.float32)
        self.session_indices         = []
        self.session_mastered_before = set()
        self.session_mastered_now    = set()
        self.apr_start  = 0.0
        self.apr_target = 0.0
        self.action_history = {}

    def reset_global(self, prior_history=None):
        N, L = N_GLOBAL, self.cfg.N_LEVELS
        if prior_history is None:
            self.successes         = np.zeros((N, L), dtype=np.float32)
            self.failures          = np.zeros((N, L), dtype=np.float32)
            self.propagation_bonus = np.zeros((N, L), dtype=np.float32)
        else:
            self.successes         = prior_history["successes"].copy()
            self.failures          = prior_history["failures"].copy()
            self.propagation_bonus = prior_history["bonuses"].copy()

    def start_session(self, session_indices):
        self.session_indices  = list(session_indices)
        self.action_history   = {}
        self.session_mastered_now = set()

        all_p        = self.predict_all_global()
        p_hard_start = all_p[self.session_indices, 2]
        raw_weights  = 1.0 - p_hard_start
        self.session_weights = raw_weights / raw_weights.sum()

        mean_p_hard       = float(p_hard_start.mean())
        difficulty_factor = float(np.clip(mean_p_hard / 0.65, 0.50, 1.0))
        effective_pct     = self.cfg.IMPROVEMENT_PCT * difficulty_factor

        self.wapr_start  = self.compute_session_wapr()
        self.wapr_target = min(0.97, self.wapr_start * (1.0 + effective_pct))
        self.apr_start   = self.compute_session_apr()
        self.apr_target  = min(0.97, self.apr_start *
                               (1.0 + self.cfg.IMPROVEMENT_PCT))

        self.session_mastered_before = {
            ci for ci in self.session_indices
            if self.predict(ci, 2) > self.cfg.MASTERY_THRESHOLD
        }
        return {
            "n_session_concepts": len(self.session_indices),
            "already_mastered":   len(self.session_mastered_before),
            "apr_start":          self.apr_start,
            "apr_target":         self.apr_target,
            "wapr_start":         self.wapr_start,
            "wapr_target":        self.wapr_target,
        }

    def predict(self, ci, level):
        k = level
        z = (self.beta_concept[ci] + self.beta_level[k]
             + self.gamma_level[k] * np.log1p(self.successes[ci, k])
             - self.rho_level[k]   * np.log1p(self.failures[ci, k])
             + self.propagation_bonus[ci, k])
        return float(sigmoid(z))

    def predict_all_global(self):
        z = (self.beta_concept[:, None] + self.beta_level[None, :]
             + self.gamma_level[None, :] * np.log1p(self.successes)
             - self.rho_level[None, :]   * np.log1p(self.failures)
             + self.propagation_bonus)
        return sigmoid(z)

    def compute_session_apr(self):
        return float(self.predict_all_global()[self.session_indices].mean())

    def compute_session_wapr(self):
        all_p  = self.predict_all_global()
        sess_p = all_p[self.session_indices]
        return float((self.session_weights * sess_p.mean(axis=1)).sum())

    def compute_global_apr(self):
        """APR across ALL concepts in pool — true student level."""
        return float(self.predict_all_global().mean())

    def compute_apr_per_course(self) -> dict[str, float]:
        """APR broken down per course — useful for multi-course sessions."""
        all_p = self.predict_all_global()
        return {
            course: float(all_p[indices].mean())
            for course, indices in COURSE_CONCEPT_INDICES.items()
        }

    def goal_met(self):
        return self.compute_session_wapr() >= self.wapr_target

    def count_newly_mastered(self):
        return len(self.session_mastered_now)

    def update(self, ci, level, correct):
        k = level
        p_before = self.predict(ci, k)
        if correct:
            self.successes[ci, k] += 1.0
        else:
            self.failures[ci, k]  += 1.0
        p_after = self.predict(ci, k)
        p_hard  = self.predict(ci, 2)
        was_mastered = (ci in self.session_mastered_before
                        or ci in self.session_mastered_now)
        if p_hard > self.cfg.MASTERY_THRESHOLD and not was_mastered:
            self.session_mastered_now.add(ci)
        delta = np.clip(p_after - p_before, -0.1, 0.1)
        if abs(delta) > 1e-6:
            sims = global_sim_matrix[ci]
            mask = sims >= self.cfg.SIM_THRESHOLD
            mask[ci] = False
            for j in np.where(mask)[0]:
                sim = sims[j]
                for lvl in range(k + 1):
                    self.propagation_bonus[j, lvl] += (
                        self.cfg.PFA_ALPHA * sim / (lvl + 1) * delta)
        return p_before, p_after

    def get_state_features(self, ci):
        all_p    = self.predict_all_global()
        sess_p   = all_p[self.session_indices]
        sess_s   = self.successes[self.session_indices]
        sess_f   = self.failures[self.session_indices]
        sess_int = sess_s.sum(axis=1) + sess_f.sum(axis=1)

        mean_p_all  = float(sess_p.mean())
        std_p_all   = float(sess_p.std())
        mean_p_easy = float(sess_p[:, 0].mean())
        mean_p_med  = float(sess_p[:, 1].mean())
        mean_p_hard = float(sess_p[:, 2].mean())
        frac_unexp  = float((sess_int == 0).mean())
        log_s_tot   = float(np.log1p(sess_s.sum()))
        log_f_tot   = float(np.log1p(sess_f.sum()))
        p_easy = float(all_p[ci, 0])
        p_med  = float(all_p[ci, 1])
        p_hard = float(all_p[ci, 2])
        log_s_c = float(np.log1p(self.successes[ci].sum()))
        log_f_c = float(np.log1p(self.failures[ci].sum()))
        global_int = self.successes.sum(axis=1) + self.failures.sum(axis=1)
        practiced  = global_int > 0
        max_sim    = float(global_sim_matrix[ci][practiced].max()) \
            if practiced.any() else 0.0
        sess_p_hard  = all_p[self.session_indices, 2]
        rank_in_sess = float((sess_p_hard < p_hard).sum()) / \
            max(1, len(self.session_indices) - 1)
        sess_int_ci    = float(self.successes[ci].sum() +
                                self.failures[ci].sum())
        steps_assigned = float(np.log1p(sess_int_ci) /
                                np.log1p(self.cfg.MAX_STEPS))
        streak_proxy   = float(np.tanh(
            self.successes[ci].sum() - self.failures[ci].sum()))
        mastered_mask  = np.zeros(N_GLOBAL, dtype=bool)
        for mc in (self.session_mastered_now | self.session_mastered_before):
            mastered_mask[mc] = True
        sim_to_mastered = float(
            global_sim_matrix[ci][mastered_mask].mean()
        ) if mastered_mask.any() else 0.0
        try:
            local_i     = self.session_indices.index(ci)
            wapr_weight = float(self.session_weights[local_i])
        except (ValueError, IndexError):
            wapr_weight = 1.0 / max(1, len(self.session_indices))

        return np.array([
            mean_p_all, std_p_all,
            mean_p_easy, mean_p_med, mean_p_hard,
            frac_unexp, log_s_tot, log_f_tot,
            p_easy, p_med, p_hard,
            log_s_c, log_f_c, max_sim,
            rank_in_sess, steps_assigned, streak_proxy,
            sim_to_mastered, wapr_weight,
        ], dtype=np.float32)

    def get_history(self):
        return {
            "successes": self.successes.copy(),
            "failures":  self.failures.copy(),
            "bonuses":   self.propagation_bonus.copy(),
        }


# ---------------------------------------------------------------------------
# Pre-selection
# ---------------------------------------------------------------------------

def preselect_session_concepts(tracker, candidate_indices, cap, rng,
                                priority_indices=None):
    candidates = list(candidate_indices)
    priority   = list(priority_indices) if priority_indices else []
    if len(candidates) <= cap:
        return candidates
    scores   = np.array([tracker.predict(ci, 2) for ci in candidates])
    diff_sc  = np.array([GLOBAL_LLM_DIFF[ci] for ci in candidates])
    jitter   = rng.uniform(0, 1e-4, size=len(candidates))
    sort_key = scores - diff_sc * 1e-3 + jitter
    ranked   = [candidates[i] for i in np.argsort(sort_key)]
    selected = [ci for ci in priority if ci in set(candidates)][:cap]
    selected_set = set(selected)
    rem = cap - len(selected)
    for ci in ranked:
        if rem <= 0:
            break
        if ci not in selected_set:
            selected.append(ci)
            selected_set.add(ci)
            rem -= 1
    return selected


# ---------------------------------------------------------------------------
# Actor
# ---------------------------------------------------------------------------

class EPPOActor(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.scorer = nn.Sequential(
            nn.Linear(cfg.SCORER_IN, cfg.HIDDEN_DIM), nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM, cfg.HIDDEN_DIM // 2), nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM // 2, 1),
        )

    def get_policy(self, tracker, session_indices, cfg):
        N_s   = len(session_indices)
        L     = cfg.N_LEVELS
        feats = np.stack([tracker.get_state_features(ci)
                          for ci in session_indices])
        ft = torch.tensor(feats, dtype=torch.float32).to(DEVICE)
        do = torch.eye(L, device=DEVICE)
        fe = ft.repeat_interleave(L, dim=0)
        de = do.repeat(N_s, 1)
        x  = torch.cat([fe, de], dim=1)
        logits = self.scorer(x).squeeze(-1)
        return Categorical(logits=logits), logits


def load_actor(model_path: str) -> EPPOActor:
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}", file=sys.stderr)
        sys.exit(1)
    actor = EPPOActor(cfg).to(DEVICE)
    ckpt  = torch.load(model_path, map_location=DEVICE)
    if isinstance(ckpt, dict) and "actor" in ckpt:
        actor.load_state_dict(ckpt["actor"])
        print(f"Loaded actor+critic checkpoint: {model_path}")
    else:
        actor.load_state_dict(ckpt)
        print(f"Loaded actor-only checkpoint: {model_path}")
    actor.eval()
    return actor


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_send_question(topic: str, difficulty: str) -> None:
    resp = requests.post(QUESTION_API_URL,
                         json={"topic": topic, "difficulty": difficulty},
                         timeout=30)
    resp.raise_for_status()


def api_get_answer() -> bool:
    resp = requests.get(ANSWER_API_URL, timeout=60)
    resp.raise_for_status()
    return bool(resp.json()["correct"])


# ---------------------------------------------------------------------------
# Session loop
# ---------------------------------------------------------------------------

def run_session(
    actor: EPPOActor,
    tracker: PFATracker,
    candidate_indices: list[int],
    rng: np.random.Generator,
    priority_indices: list[int] | None = None,
    verbose: bool = True,
) -> dict:
    sess_idx = preselect_session_concepts(
        tracker, candidate_indices, cfg.CONCEPT_CAP, rng, priority_indices)
    info = tracker.start_session(sess_idx)

    if verbose:
        print(f"\n{'='*70}")
        print(f"SESSION  user={EPPO_USER_ID}  "
              f"scope={SCOPE_TYPE}:[{SCOPE_VALUE}]")
        print(f"  Concepts      : {info['n_session_concepts']}  "
              f"(mastered before: {info['already_mastered']})")
        print(f"  APR  goal     : {info['apr_start']:.4f} → "
              f"{info['apr_target']:.4f}")
        print(f"  WAPR goal     : {info['wapr_start']:.4f} → "
              f"{info['wapr_target']:.4f}")
        print(f"  Global APR    : {tracker.compute_global_apr():.4f}")
        apr_per = tracker.compute_apr_per_course()
        for course, apr in apr_per.items():
            print(f"    {course}: APR={apr:.4f}")
        print(f"{'='*70}")
        print(f"{'Step':>4} {'Concept':<35} {'Course':<20} "
              f"{'Diff':>6} {'Correct':>7} {'P(Hard)':>8}")
        print("-" * 85)

    # Build reverse index: global_concept_idx → course name for logging
    idx_to_course = {}
    for course, indices in COURSE_CONCEPT_INDICES.items():
        for idx in indices:
            idx_to_course[idx] = course

    buf_ref_levels = []

    for step in range(cfg.MAX_STEPS):
        with torch.no_grad():
            dist, logits = actor.get_policy(tracker, sess_idx, cfg)

        n_hard_so_far = buf_ref_levels.count(2)
        hard_fraction = n_hard_so_far / max(1, step)
        if step > 3 and hard_fraction < cfg.HARD_FLOOR:
            best_local = logits[2::3].argmax().item()
            flat = best_local * cfg.N_LEVELS + 2
        else:
            flat = dist.sample().item()

        local_ci        = flat // cfg.N_LEVELS
        level           = flat % cfg.N_LEVELS
        buf_ref_levels.append(level)
        global_ci       = sess_idx[local_ci]
        db_concept_id   = GLOBAL_CONCEPT_IDS[global_ci]
        concept_name    = GLOBAL_CONCEPTS[global_ci]
        difficulty_name = cfg.LEVEL_NAMES[level]
        course_label    = idx_to_course.get(global_ci, "?")

        api_send_question(concept_name, difficulty_name)
        correct = api_get_answer()

        p_before, p_after = tracker.update(global_ci, level, int(correct))
        p_hard_now = tracker.predict(global_ci, 2)

        log_interaction(
            CONCEPT_DB_URL, SESSION_ID, EPPO_USER_ID,
            db_concept_id, difficulty_name,
            correct, p_before, p_after, p_hard_now,
        )

        if verbose:
            print(f"{step+1:>4} {concept_name:<35} {course_label:<20} "
                  f"{difficulty_name:>6} {'✓' if correct else '✗':>7} "
                  f"{p_hard_now:>8.3f}")

        if tracker.goal_met():
            if verbose:
                print(f"\n  Goal met at step {step + 1}!")
            break

    apr_final  = tracker.compute_session_apr()
    wapr_final = tracker.compute_session_wapr()
    global_apr = tracker.compute_global_apr()
    apr_per    = tracker.compute_apr_per_course()
    n_mastered = tracker.count_newly_mastered()

    if verbose:
        print(f"\n  Final session APR  : {apr_final:.4f}  "
              f"(start: {info['apr_start']:.4f})")
        print(f"  Final session WAPR : {wapr_final:.4f}")
        print(f"  Global APR         : {global_apr:.4f}")
        print(f"  Per-course APR     :")
        for course, apr in apr_per.items():
            print(f"    {course}: {apr:.4f}")
        print(f"  Goal               : "
              f"{'MET ✓' if tracker.goal_met() else 'NOT MET ✗'}")
        print(f"  Newly mastered     : {n_mastered}")

    return {
        "apr_start":      info["apr_start"],
        "apr_final":      apr_final,
        "wapr_final":     wapr_final,
        "global_apr":     global_apr,
        "apr_per_course": apr_per,
        "goal_met":       tracker.goal_met(),
        "steps":          step + 1,
        "newly_mastered": n_mastered,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ensure_tables(CONCEPT_DB_URL)
    actor = load_actor(MODEL_PATH)

    tracker = PFATracker(cfg)
    history = load_pfa_history(CONCEPT_DB_URL, EPPO_USER_ID)
    if history:
        tracker.reset_global(prior_history=history)
        print(f"[pfa] Resumed student. "
              f"Global APR = {tracker.compute_global_apr():.4f}")
        print(f"[pfa] Per-course APR: {tracker.compute_apr_per_course()}")
    else:
        tracker.reset_global()
        print("[pfa] New student — starting fresh.")

    candidate_indices = list(range(N_GLOBAL))
    rng    = np.random.default_rng(42)
    result = run_session(
        actor=actor,
        tracker=tracker,
        candidate_indices=candidate_indices,
        rng=rng,
        verbose=True,
    )

    save_pfa_history(CONCEPT_DB_URL, EPPO_USER_ID, tracker)
    mark_session_ended(CONCEPT_DB_URL, SESSION_ID)
    print("\nSession result:", result)