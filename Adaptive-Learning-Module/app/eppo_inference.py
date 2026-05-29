"""
EPPO Local Inference
====================
Extracted from full-session-evalution.ipynb (Cells 1-6, 8 only).
Replaces the simulated student with two real API calls:
  - POST /generate  -> sends {topic, difficulty} to question generation module
  - GET  /answer    -> gets {correct: bool} back from the answer checker

The global concept pool is loaded at startup from the Adaptive-Learning-Module
PostgreSQL database.  Configure the connection and user in .env:

  CONCEPT_DB_URL=postgresql://user:pass@host:5432/adaptive_db
  EPPO_USER_ID=1

Run:
    python eppo_inference.py

Dependencies (install once):
    pip install torch sentence-transformers numpy requests sqlalchemy psycopg2-binary python-dotenv
"""

import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from dotenv import load_dotenv
from torch.distributions import Categorical
from sentence_transformers import SentenceTransformer
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine, text
from sqlalchemy.orm import declarative_base, relationship, Session
import warnings
import os
import requests

# Load .env from the same directory as this script
load_dotenv(Path(__file__).parent / ".env")

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# CONFIG — edit API URLs and model path here
# ---------------------------------------------------------------------------
QUESTION_API_URL = "http://localhost:5000/generate"   # POST {topic, difficulty}
ANSWER_API_URL   = "http://localhost:5000/answer"     # GET  -> {correct: bool}
MODEL_PATH       = os.path.join(os.path.dirname(__file__), "models", "eppo_ep2500.pt")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {DEVICE}")

# ---------------------------------------------------------------------------
# CELL 2: Global Concept Pool  (loaded from database)
# ---------------------------------------------------------------------------

# ── SQLAlchemy models (read-only, lightweight) ───────────────────────────────
_Base = declarative_base()


class _CourseEnrollment(_Base):
    __tablename__ = "course_enrollments"
    user_id   = Column(Integer, ForeignKey("courses.id"), primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"), primary_key=True)


class _Course(_Base):
    __tablename__ = "courses"
    id       = Column(Integer, primary_key=True)
    name     = Column(String, nullable=False)
    concepts = relationship("_Concept", back_populates="course",
                            order_by="_Concept.id")


class _Concept(_Base):
    __tablename__ = "concepts"
    id         = Column(Integer, primary_key=True)
    course_id  = Column(Integer, ForeignKey("courses.id"), nullable=False)
    name       = Column(String, nullable=False)
    difficulty = Column(Integer, nullable=False)
    course     = relationship("_Course", back_populates="concepts")


def _load_concept_pool_from_db(
    db_url: str,
    user_id: int,
) -> tuple[list[str], list[int], dict[str, list[int]]]:
    """
    Query all courses the user is enrolled in and fetch their concepts.

    Returns:
        global_concepts      — flat list of concept names
        global_llm_diff      — parallel list of difficulty integers (1-5)
        course_concept_indices — {course_name: [global_indices]}
    """
    engine = create_engine(db_url)
    with Session(engine) as session:
        # Courses the user is enrolled in
        enrolled_course_ids = [
            row[0]
            for row in session.execute(
                text("SELECT course_id FROM course_enrollments WHERE user_id = :uid"),
                {"uid": user_id},
            )
        ]

        if not enrolled_course_ids:
            print(f"[eppo] WARNING: user_id={user_id} has no enrolled courses. "
                  "Concept pool will be empty.", file=sys.stderr)
            return [], [], {}

        courses = (
            session.query(_Course)
            .filter(_Course.id.in_(enrolled_course_ids))
            .order_by(_Course.id)
            .all()
        )

        global_concepts: list[str] = []
        global_llm_diff: list[int] = []
        course_concept_indices: dict[str, list[int]] = {}

        for course in courses:
            idxs: list[int] = []
            for concept in course.concepts:
                global_concepts.append(concept.name)
                global_llm_diff.append(int(concept.difficulty))
                idxs.append(len(global_concepts) - 1)
            # Use a filesystem-safe version of the course name as the key
            key = course.name.lower().replace(" ", "_")
            course_concept_indices[key] = idxs

        session.expunge_all()

    return global_concepts, global_llm_diff, course_concept_indices


# ── Load from DB at startup ───────────────────────────────────────────────────
_CONCEPT_DB_URL = os.environ.get("CONCEPT_DB_URL", "").strip()
_EPPO_USER_ID   = int(os.environ.get("EPPO_USER_ID", "0") or "0")

if not _CONCEPT_DB_URL:
    print("ERROR: CONCEPT_DB_URL is not set in .env", file=sys.stderr)
    sys.exit(1)
if not _EPPO_USER_ID:
    print("ERROR: EPPO_USER_ID is not set in .env", file=sys.stderr)
    sys.exit(1)

print(f"[eppo] Loading concept pool for user_id={_EPPO_USER_ID} from DB...")
GLOBAL_CONCEPTS, GLOBAL_LLM_DIFF, COURSE_CONCEPT_INDICES = _load_concept_pool_from_db(
    _CONCEPT_DB_URL, _EPPO_USER_ID
)

N_GLOBAL = len(GLOBAL_CONCEPTS)
print(f"[eppo] Global pool: {N_GLOBAL} concepts across "
      f"{len(COURSE_CONCEPT_INDICES)} courses: "
      f"{list(COURSE_CONCEPT_INDICES.keys())}")

if N_GLOBAL == 0:
    print("ERROR: No concepts found. Upload concepts first with concept_extractor.py.",
          file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# CELL 3: Config
# ---------------------------------------------------------------------------
class Config:
    N_LEVELS = 3
    LEVEL_NAMES = ['Easy', 'Medium', 'Hard']
    GAMMA_LEVEL = np.array([0.0330, 0.1494, 0.8884])
    RHO_LEVEL   = np.array([0.1444, 0.3433, 0.2331])
    BETA_LEVEL  = np.array([1.4333, 1.0389, 0.4271])
    LLM_BETA_SCALE = -0.4
    LLM_BETA_MID   = 3.0
    PFA_TOP_K = 5
    PFA_ALPHA = 0.04
    SIM_THRESHOLD = 0.45
    MAX_STEPS = 60
    CONCEPT_CAP = 10
    IMPROVEMENT_PCT    = 0.07
    SESSION_DONE_BONUS = 10.0
    MASTERY_THRESHOLD  = 0.65
    EMBED_MODEL = 'BAAI/bge-base-en-v1.5'
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
# CELL 4: Embeddings + Global Similarity Graph
# ---------------------------------------------------------------------------
print(f"Loading {cfg.EMBED_MODEL} (downloads ~438MB on first run)...")
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
    if mask.sum() == 0:
        top = np.array([np.argmax(s)])
    else:
        top = np.where(mask)[0][np.argsort(-s[mask])[:cfg.PFA_TOP_K]]
    global_neighbours.append(top)

print(f"Embedding shape: {global_embeddings.shape}")

# ---------------------------------------------------------------------------
# CELL 5: PFA Tracker
# ---------------------------------------------------------------------------
def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -15, 15)))


class PFATracker:
    def __init__(self, cfg):
        self.cfg = cfg
        N, L = N_GLOBAL, cfg.N_LEVELS
        self.gamma_level = cfg.GAMMA_LEVEL.copy()
        self.rho_level   = cfg.RHO_LEVEL.copy()
        self.beta_level  = cfg.BETA_LEVEL.copy()
        self.beta_concept = np.array(
            [(d - cfg.LLM_BETA_MID) * cfg.LLM_BETA_SCALE for d in GLOBAL_LLM_DIFF],
            dtype=np.float32,
        )
        self.successes = np.zeros((N, L), dtype=np.float32)
        self.failures  = np.zeros((N, L), dtype=np.float32)
        self.propagation_bonus = np.zeros((N, L), dtype=np.float32)
        self.session_indices = []
        self.session_mastered_before = set()
        self.session_mastered_now    = set()
        self.apr_start = 0.0
        self.apr_target = 0.0
        self.action_history = {}

    def reset_global(self, prior_history=None):
        N, L = N_GLOBAL, self.cfg.N_LEVELS
        if prior_history is None:
            self.successes = np.zeros((N, L), dtype=np.float32)
            self.failures  = np.zeros((N, L), dtype=np.float32)
            self.propagation_bonus = np.zeros((N, L), dtype=np.float32)
        else:
            self.successes = prior_history['successes'].copy()
            self.failures  = prior_history['failures'].copy()
            self.propagation_bonus = prior_history['bonuses'].copy()

    def start_session(self, session_indices):
        self.session_indices = list(session_indices)
        self.action_history  = {}
        self.session_mastered_now = set()

        all_p_start  = self.predict_all_global()
        p_hard_start = all_p_start[self.session_indices, 2]
        raw_weights  = 1.0 - p_hard_start
        total_w = raw_weights.sum()
        self.session_weights = raw_weights / total_w

        mean_p_hard_sess = float(all_p_start[self.session_indices, 2].mean())
        difficulty_factor = float(np.clip(mean_p_hard_sess / 0.65, 0.50, 1.0))
        effective_pct     = self.cfg.IMPROVEMENT_PCT * difficulty_factor

        self.wapr_start  = self.compute_session_wapr()
        self.wapr_target = min(0.97, self.wapr_start * (1.0 + effective_pct))
        self.wapr_improvement_needed = self.wapr_target - self.wapr_start
        self.effective_improvement_pct = effective_pct

        self.apr_start  = self.compute_session_apr()
        self.apr_target = min(0.97, self.apr_start * (1.0 + self.cfg.IMPROVEMENT_PCT))
        self.apr_improvement_needed = self.apr_target - self.apr_start

        self.session_mastered_before = {
            ci for ci in self.session_indices
            if self.predict(ci, 2) > self.cfg.MASTERY_THRESHOLD
        }

        return {
            'n_session_concepts': len(self.session_indices),
            'already_mastered':   len(self.session_mastered_before),
            'apr_start':          self.apr_start,
            'apr_target':         self.apr_target,
            'wapr_start':         self.wapr_start,
            'wapr_target':        self.wapr_target,
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
        all_p = self.predict_all_global()
        return float(all_p[self.session_indices].mean())

    def compute_session_wapr(self):
        all_p  = self.predict_all_global()
        sess_p = all_p[self.session_indices]
        mean_p = sess_p.mean(axis=1)
        return float((self.session_weights * mean_p).sum())

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
        was_mastered = (ci in self.session_mastered_before or ci in self.session_mastered_now)
        if p_hard > self.cfg.MASTERY_THRESHOLD and not was_mastered:
            self.session_mastered_now.add(ci)
        delta = np.clip(p_after - p_before, -0.1, 0.1)
        if abs(delta) > 1e-6:
            sims = global_sim_matrix[ci]
            mask = (sims >= self.cfg.SIM_THRESHOLD)
            mask[ci] = False
            for j in np.where(mask)[0]:
                sim = sims[j]
                for lvl in range(k + 1):
                    self.propagation_bonus[j, lvl] += (
                        self.cfg.PFA_ALPHA * sim / (lvl + 1) * delta
                    )
        return p_before, p_after

    def get_state_features(self, ci):
        all_p  = self.predict_all_global()
        sess_p = all_p[self.session_indices]
        sess_s = self.successes[self.session_indices]
        sess_f = self.failures[self.session_indices]
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
        practiced  = (global_int > 0)
        max_sim    = float(global_sim_matrix[ci][practiced].max()) if practiced.any() else 0.0

        sess_p_hard = all_p[self.session_indices, 2]
        n_weaker    = float((sess_p_hard < p_hard).sum())
        rank_in_sess = n_weaker / max(1, len(self.session_indices) - 1)

        sess_int_ci   = float(self.successes[ci].sum() + self.failures[ci].sum())
        steps_assigned = float(np.log1p(sess_int_ci) / np.log1p(self.cfg.MAX_STEPS))

        streak_proxy = float(np.tanh(self.successes[ci].sum() - self.failures[ci].sum()))

        mastered_mask = np.zeros(N_GLOBAL, dtype=bool)
        for mc in (self.session_mastered_now | self.session_mastered_before):
            mastered_mask[mc] = True
        sim_to_mastered = float(
            global_sim_matrix[ci][mastered_mask].mean()
        ) if mastered_mask.any() else 0.0

        if hasattr(self, 'session_weights') and len(self.session_indices) > 0:
            try:
                local_i    = self.session_indices.index(ci)
                wapr_weight = float(self.session_weights[local_i])
            except (ValueError, IndexError):
                wapr_weight = 1.0 / max(1, len(self.session_indices))
        else:
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

    def get_critic_state(self):
        feats = np.stack([self.get_state_features(ci) for ci in self.session_indices])
        return feats.mean(axis=0)

    def get_history(self):
        """Serialize tracker state for persistence between sessions."""
        return {
            'successes': self.successes.copy(),
            'failures':  self.failures.copy(),
            'bonuses':   self.propagation_bonus.copy(),
        }


# ---------------------------------------------------------------------------
# CELL 6: Session Pre-Selection
# ---------------------------------------------------------------------------
def preselect_session_concepts(tracker, candidate_indices, cap, rng, priority_indices=None):
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
# CELL 8: Actor Network
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
        N_s = len(session_indices)
        L   = cfg.N_LEVELS
        feats = np.stack([tracker.get_state_features(ci) for ci in session_indices])
        ft = torch.tensor(feats, dtype=torch.float32).to(DEVICE)
        do = torch.eye(L, device=DEVICE)
        fe = ft.repeat_interleave(L, dim=0)
        de = do.repeat(N_s, 1)
        x  = torch.cat([fe, de], dim=1)
        logits = self.scorer(x).squeeze(-1)
        return Categorical(logits=logits), logits


def load_actor(model_path: str) -> EPPOActor:
    actor = EPPOActor(cfg).to(DEVICE)
    ckpt  = torch.load(model_path, map_location=DEVICE)
    if isinstance(ckpt, dict) and 'actor' in ckpt:
        actor.load_state_dict(ckpt['actor'])
        print(f"Loaded actor+critic checkpoint: {model_path}")
    else:
        actor.load_state_dict(ckpt)
        print(f"Loaded actor-only checkpoint: {model_path}")
    actor.eval()
    return actor


# ---------------------------------------------------------------------------
# API helpers  (replace with your real API calls)
# ---------------------------------------------------------------------------
def api_send_question(topic: str, difficulty: str) -> None:
    """
    POST {topic, difficulty} to the question generation module.
    The module generates and presents the question to the student.
    """
    payload = {"topic": topic, "difficulty": difficulty}
    resp = requests.post(QUESTION_API_URL, json=payload, timeout=30)
    resp.raise_for_status()


def api_get_answer() -> bool:
    """
    GET the student's answer result from the answer API.
    Returns True if the student answered correctly.
    """
    resp = requests.get(ANSWER_API_URL, timeout=60)
    resp.raise_for_status()
    return bool(resp.json()["correct"])


# ---------------------------------------------------------------------------
# Main inference loop
# ---------------------------------------------------------------------------
def run_session(
    actor: EPPOActor,
    tracker: PFATracker,
    course_name: str,
    rng: np.random.Generator,
    priority_indices=None,
    verbose: bool = True,
):
    """
    Run one adaptive learning session for a student.

    Args:
        actor:            Loaded EPPO actor.
        tracker:          PFATracker (holds cross-session student state).
        course_name:      One of the keys in COURSES (e.g. 'algorithms').
        rng:              NumPy random generator.
        priority_indices: Global concept indices to prioritise (unmet goals from last session).
        verbose:          Print step-by-step trace.

    Returns:
        dict with session stats (apr_start, apr_final, goal_met, steps, newly_mastered).
    """
    candidate_indices = COURSE_CONCEPT_INDICES[course_name]
    sess_idx = preselect_session_concepts(
        tracker, candidate_indices, cfg.CONCEPT_CAP, rng, priority_indices
    )
    info = tracker.start_session(sess_idx)

    if verbose:
        print(f"\n{'='*70}")
        print(f"SESSION: {course_name.upper()}")
        print(f"  Concepts in scope : {info['n_session_concepts']}  "
              f"(already mastered: {info['already_mastered']})")
        print(f"  APR goal          : {info['apr_start']:.4f} → {info['apr_target']:.4f}")
        print(f"  WAPR goal         : {info['wapr_start']:.4f} → {info['wapr_target']:.4f}")
        print(f"{'='*70}")
        print(f"{'Step':>4} {'Concept':<35} {'Diff':>6} {'Correct':>7} {'P(Hard)':>8}")
        print("-" * 65)

    buf_ref_levels = []

    for step in range(cfg.MAX_STEPS):
        # -- Actor selects (concept, difficulty) --
        with torch.no_grad():
            dist, logits = actor.get_policy(tracker, sess_idx, cfg)

        # Hard floor: if Hard fraction < HARD_FLOOR, force a Hard pick
        n_hard_so_far  = buf_ref_levels.count(2)
        hard_fraction  = n_hard_so_far / max(1, step)
        if step > 3 and hard_fraction < cfg.HARD_FLOOR:
            hard_logits = logits[2::3]
            best_local  = hard_logits.argmax().item()
            flat        = best_local * cfg.N_LEVELS + 2
        else:
            flat = dist.sample().item()

        local_ci  = flat // cfg.N_LEVELS
        level     = flat % cfg.N_LEVELS
        buf_ref_levels.append(level)
        global_ci = sess_idx[local_ci]

        concept_name   = GLOBAL_CONCEPTS[global_ci]
        difficulty_name = cfg.LEVEL_NAMES[level]

        # -- Send to question generation API --
        api_send_question(concept_name, difficulty_name)

        # -- Get student answer from API --
        correct = api_get_answer()

        # -- Update PFA state --
        p_before, p_after = tracker.update(global_ci, level, int(correct))
        p_hard_now = tracker.predict(global_ci, 2)

        if verbose:
            print(f"{step+1:>4} {concept_name:<35} {difficulty_name:>6} "
                  f"{'✓' if correct else '✗':>7} {p_hard_now:>8.3f}")

        # -- Check goal --
        if tracker.goal_met():
            if verbose:
                print(f"\n  → GOAL MET at step {step + 1}!")
            break

    apr_final  = tracker.compute_session_apr()
    wapr_final = tracker.compute_session_wapr()
    n_mastered = tracker.count_newly_mastered()

    if verbose:
        print(f"\n  Final APR : {apr_final:.4f}  (start: {info['apr_start']:.4f})")
        print(f"  Goal      : {'MET ✓' if tracker.goal_met() else 'NOT MET ✗'}")
        print(f"  Mastered  : {n_mastered} new concepts")

    return {
        'apr_start':       info['apr_start'],
        'apr_final':       apr_final,
        'wapr_final':      wapr_final,
        'goal_met':        tracker.goal_met(),
        'steps':           step + 1,
        'newly_mastered':  n_mastered,
        'pfa_history':     tracker.get_history(),   # persist this between sessions
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    actor   = load_actor(MODEL_PATH)
    tracker = PFATracker(cfg)
    tracker.reset_global()          # fresh student; load prior history here if resuming

    rng = np.random.default_rng(42)
    # Pick the first enrolled course automatically, or set by name
    course_name = list(COURSE_CONCEPT_INDICES.keys())[0]
    print(f"Running session on course: '{course_name}'")

    result = run_session(
        actor,
        tracker,
        course_name=course_name,
        rng=rng,
        verbose=True,
    )

    print("\nSession result:", result)
