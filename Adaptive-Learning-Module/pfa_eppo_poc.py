"""
PFA + EPPO Adaptive Learning — Complete POC
============================================
Full flow: PFA knowledge tracer → EPPO recommender → evaluation
Small concept set, Kaggle T4 compatible, ~25 min end-to-end.

Architecture
------------
  RealisticStudent  →  PFATracker  →  EPPOAgent  →  action (concept, bloom_level)
       ↑                    ↑               |
       └────────────────────┴───── reward ←─┘

Sections
--------
  A. Config
  B. PFA knowledge tracer
  C. Realistic student simulator
  D. EPPO agent (actor-critic)
  E. Reward function  (ALPN-style)
  F. Rollout buffer + GAE + PPO update
  G. Pre-validation: 8-test suite on PFA alone
  H. EPPO training loop (two-phase: PFA warm-up → freeze → EPPO)
  I. Evaluation: policy comparison (EPPO vs random vs greedy)
  J. Demo session (step-by-step trace)
  K. Diagnostic plots
"""

# ─── Imports ──────────────────────────────────────────────────────────────────
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Categorical
from collections import defaultdict, deque
import random
import copy
import os
import warnings
warnings.filterwarnings("ignore")

# ─── A. Config ────────────────────────────────────────────────────────────────

class Config:
    # ── Concept set (small, 8 CE concepts for POC) ──
    CONCEPTS = [
        "binary search tree",
        "linked list",
        "sorting algorithms",
        "dynamic programming",
        "process scheduling",
        "memory management",
        "TCP IP basics",
        "recursion",
    ]
    N_CONCEPTS   = len(CONCEPTS)
    BLOOM_LEVELS = 6          # Bloom's taxonomy L1..L6
    N_ACTIONS    = N_CONCEPTS * BLOOM_LEVELS   # 48

    # ── PFA hyperparameters ──
    PFA_TOP_K    = 3          # similarity neighbours for propagation
    PFA_ALPHA    = 0.05       # propagation strength
    # Level difficulty priors (aligned to student IRT curve)
    BETA_LEVEL   = np.array([ 0.0, -0.4, -0.9, -1.5, -2.1, -2.9])
    GAMMA_LEVEL  = np.array([ 0.40,  0.36,  0.32,  0.28,  0.24,  0.20])
    RHO_LEVEL    = np.array([ 0.28,  0.33,  0.38,  0.43,  0.50,  0.58])

    # ── Student simulator ──
    SLIP         = 0.08
    GUESS        = 0.15
    LEARN_RATE   = 0.04
    FORGET_RATE  = 0.005
    TRANSFER_ALPHA = 0.30

    # ── EPPO ──
    STATE_DIM    = N_CONCEPTS * 4   # per-concept: [mean_mastery, max_level, variance, attempted]
    HIDDEN_DIM   = 128
    LR_ACTOR     = 3e-4
    LR_CRITIC    = 3e-4
    GAMMA        = 0.99
    GAE_LAMBDA   = 0.95
    CLIP_EPS     = 0.20
    ENTROPY_COEF = 0.015
    VALUE_COEF   = 0.50
    PPO_EPOCHS   = 4
    GRAD_CLIP    = 0.50

    # ── Training ──
    WARMUP_EPISODES  = 300    # random episodes to warm PFA before freezing
    N_EPISODES       = 1500   # EPPO training episodes
    MAX_STEPS        = 35     # interactions per session
    BETA_APR         = 0.72   # learning goal (average pass rate)
    MIN_COVERAGE     = True   # must visit every concept at least once
    LOG_EVERY        = 100
    SAVE_EVERY       = 500

    # ── Reward weights ──
    W_MASTERY    = 1.0        # mastery gain weight
    W_FIT        = 0.40       # difficulty fit penalty weight
    W_DIV        = 0.08       # diversity penalty weight
    MAX_SAME_CONCEPT = 3      # consecutive same-concept cap

    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ─── B. PFA Knowledge Tracer ──────────────────────────────────────────────────

class PFATracker:
    """
    Performance Factor Analysis with sentence-embedding similarity graph.

    predict(concept, level) → P(correct) ∈ (0,1)
    update(concept, level, correct) → updates counts + propagates to neighbours
    get_state_vector(cfg) → fixed-size feature vector for EPPO
    """

    def __init__(self, concepts, cfg: Config, sim_matrix=None):
        self.concepts    = concepts
        self.cfg         = cfg
        self.num_levels  = cfg.BLOOM_LEVELS
        self.top_k       = cfg.PFA_TOP_K
        self.alpha       = cfg.PFA_ALPHA
        self.num_concepts = len(concepts)
        self.idx = {c: i for i, c in enumerate(concepts)}

        # Observation counts — only real interactions write here
        self.successes = np.zeros((self.num_concepts, self.num_levels))
        self.failures  = np.zeros((self.num_concepts, self.num_levels))
        # Propagation bonus — separate from raw counts (no ghost counts)
        self.propagation_bonus = np.zeros((self.num_concepts, self.num_levels))

        # Concept bias prior (fixed seed → deterministic)
        rng = np.random.default_rng(42)
        self.beta_concept = rng.uniform(-0.3, 0.3, self.num_concepts)

        # Similarity graph
        if sim_matrix is not None:
            self.sim_matrix = sim_matrix
            self._build_neighbors()
        else:
            self._build_similarity_graph()

        # Track which concepts have been attempted (for state vector)
        self.attempted = np.zeros(self.num_concepts, dtype=bool)

    def _build_similarity_graph(self):
        print("Building similarity graph (sentence-transformers)...")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("BAAI/bge-base-en-v1.5")
        emb = model.encode(self.concepts, normalize_embeddings=True)
        self.sim_matrix = emb @ emb.T
        self._build_neighbors()
        print(f"  Graph built. Top-3 neighbours of '{self.concepts[0]}':")
        for j in self.neighbors[0]:
            print(f"    {self.concepts[j]}  sim={self.sim_matrix[0,j]:.3f}")

    def _build_neighbors(self):
        self.neighbors = []
        for i in range(self.num_concepts):
            sims = self.sim_matrix[i]
            ranked = np.argsort(-sims)
            ranked = [j for j in ranked if j != i]
            self.neighbors.append(ranked[:self.top_k])

    # ── Prediction ──
    def predict(self, concept, level):
        """Return P(correct) for concept at Bloom level (1-indexed)."""
        i = self.idx[concept]
        k = level - 1
        cfg = self.cfg
        z = (
            self.beta_concept[i]
            + cfg.BETA_LEVEL[k]
            + cfg.GAMMA_LEVEL[k] * np.log1p(self.successes[i, k])
            - cfg.RHO_LEVEL[k]   * np.log1p(self.failures[i, k])
            + self.propagation_bonus[i, k]
        )
        # Lower-level scaffold
        if k > 0:
            z += 0.25 * (
                cfg.GAMMA_LEVEL[k-1] * np.log1p(self.successes[i, k-1])
                - cfg.RHO_LEVEL[k-1] * np.log1p(self.failures[i, k-1])
            )
        return float(1 / (1 + np.exp(-z)))

    def predict_idx(self, concept_idx, level):
        return self.predict(self.concepts[concept_idx], level)

    # ── Update ──
    def update(self, concept, level, correct):
        """Record one interaction and propagate to neighbours."""
        i = self.idx[concept]
        k = level - 1
        self.attempted[i] = True

        old_p = self.predict(concept, level)
        if correct:
            self.successes[i, k] += 1
        else:
            self.failures[i, k]  += 1
        new_p = self.predict(concept, level)

        delta = np.clip(new_p - old_p, -0.10, 0.10)

        for j in self.neighbors[i]:
            sim = self.sim_matrix[i, j]
            for lvl in range(k + 1):
                weight = self.alpha * sim / (lvl + 1)
                self.propagation_bonus[j, lvl] += weight * delta

    def update_idx(self, concept_idx, level, correct):
        self.update(self.concepts[concept_idx], level, correct)

    # ── State vector for EPPO (fixed size regardless of N_concepts) ──
    def get_state_vector(self) -> np.ndarray:
        """
        Fixed-size state: 4 features per concept.
          [0] mean mastery across Bloom levels
          [1] highest level where P > 0.60  (normalised 0..1)
          [2] variance across Bloom levels
          [3] 1 if attempted, else 0
        Shape: (N_CONCEPTS * 4,)
        """
        feats = []
        for i, c in enumerate(self.concepts):
            probs = np.array([self.predict(c, l+1) for l in range(self.num_levels)])
            mean_m   = float(probs.mean())
            max_lvl  = max((l for l in range(self.num_levels) if probs[l] > 0.60),
                           default=-1)
            norm_lvl = (max_lvl + 1) / self.num_levels
            variance = float(probs.var())
            attempted = float(self.attempted[i])
            feats.extend([mean_m, norm_lvl, variance, attempted])
        return np.array(feats, dtype=np.float32)

    def get_mastery_matrix(self) -> np.ndarray:
        """Full (N_concepts, N_levels) mastery probability matrix."""
        M = np.zeros((self.num_concepts, self.num_levels))
        for i, c in enumerate(self.concepts):
            for k in range(self.num_levels):
                M[i, k] = self.predict(c, k+1)
        return M

    def get_mean_mastery(self) -> float:
        """Scalar summary: average P(correct) across all concept × L1 cells."""
        return float(np.mean([self.predict(c, 1) for c in self.concepts]))

    def reset(self):
        """Reset to cold-start (new student)."""
        self.successes[:]          = 0
        self.failures[:]           = 0
        self.propagation_bonus[:]  = 0
        self.attempted[:]          = False


# ─── C. Realistic Student Simulator ──────────────────────────────────────────

class RealisticStudent:
    """
    3PL IRT student with per-concept × per-level ability, forgetting,
    slip/guess, and concept transfer via the PFA similarity matrix.
    """

    def __init__(self, concepts, sim_matrix, rng, cfg: Config):
        self.concepts        = concepts
        self.sim_matrix      = sim_matrix
        self.rng             = rng
        self.slip            = cfg.SLIP
        self.guess           = cfg.GUESS
        self.learn_rate      = cfg.LEARN_RATE
        self.forget_rate     = cfg.FORGET_RATE
        self.transfer_alpha  = cfg.TRANSFER_ALPHA

        num_c = len(concepts)
        base  = rng.uniform(-1.5, 0.5, size=num_c)
        level_offsets = np.array([1.0, 0.6, 0.2, -0.2, -0.7, -1.3])
        self.ability = base[:, None] + level_offsets[None, :]   # (C, 6)

        self.item_difficulty = np.array([0.0, 0.5, 1.0, 1.5, 2.2, 3.0])
        self.last_attempt = defaultdict(lambda: 0)
        self.t = 0

    @classmethod
    def from_archetype(cls, concepts, sim_matrix, rng, cfg, archetype="mixed"):
        """Sample a student with a specific prior ability distribution."""
        s = cls(concepts, sim_matrix, rng, cfg)
        num_c = len(concepts)
        if archetype == "beginner":
            base = rng.uniform(-1.8, -0.5, size=num_c)
        elif archetype == "intermediate":
            base = rng.uniform(-0.8, 0.3, size=num_c)
        elif archetype == "advanced":
            base = rng.uniform(-0.2, 1.0, size=num_c)
        else:  # mixed
            base = rng.uniform(-1.5, 0.5, size=num_c)
        level_offsets = np.array([1.0, 0.6, 0.2, -0.2, -0.7, -1.3])
        s.ability = base[:, None] + level_offsets[None, :]
        return s

    def _apply_forgetting(self, concept_idx, k):
        key = (concept_idx, k)
        elapsed = self.t - self.last_attempt[key]
        if elapsed > 0:
            decay = self.forget_rate * np.sqrt(elapsed)
            self.ability[concept_idx, k] = max(
                self.ability[concept_idx, k] - decay, -3.0)

    def answer(self, concept_idx, level):
        """
        Returns (correct: bool, true_p: float, p_know: float)
        level is 1-indexed Bloom level.
        """
        self.t += 1
        k = level - 1
        self._apply_forgetting(concept_idx, k)

        logit  = self.ability[concept_idx, k] - self.item_difficulty[k]
        p_know = float(1 / (1 + np.exp(-logit)))
        true_p = self.guess + (1 - self.slip - self.guess) * p_know

        correct = bool(self.rng.random() < true_p)
        self.last_attempt[(concept_idx, k)] = self.t
        return correct, true_p, p_know

    def learn(self, concept_idx, level, correct):
        k = level - 1
        if correct:
            self.ability[concept_idx, k] += self.learn_rate
            if k > 0:
                self.ability[concept_idx, k-1] += self.learn_rate * 0.3
        else:
            self.ability[concept_idx, k] = max(
                self.ability[concept_idx, k] - self.learn_rate * 0.3, -3.0)

        # Concept transfer via similarity matrix
        for j, sim in enumerate(self.sim_matrix[concept_idx]):
            if j == concept_idx or sim < 0.50:
                continue
            # Apply forgetting to neighbour before transferring
            self._apply_forgetting(j, k)
            transfer = self.transfer_alpha * sim * self.learn_rate
            if correct:
                self.ability[j, k] += transfer


# ─── D. EPPO Agent ────────────────────────────────────────────────────────────

class EPPOAgent(nn.Module):
    """
    Entropy-enhanced PPO.

    State  : PFA state vector  (N_CONCEPTS * 4,)
    Action : concept_idx * BLOOM_LEVELS + (level-1)  → int in [0, N_ACTIONS)
    """

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg

        self.actor = nn.Sequential(
            nn.Linear(cfg.STATE_DIM, cfg.HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM, cfg.HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM, cfg.N_ACTIONS),
        )
        self.critic = nn.Sequential(
            nn.Linear(cfg.STATE_DIM, cfg.HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM, cfg.HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM, 1),
        )

    def get_action_mask(self, mastery_matrix: np.ndarray) -> torch.BoolTensor:
        """
        Competence ceiling mask.
        For each concept, allow: current_competence_level and one above.
        L1 (recall) is always allowed as a guaranteed fallback.
        """
        cfg = self.cfg
        mask = torch.zeros(cfg.N_ACTIONS, dtype=torch.bool)

        for c in range(cfg.N_CONCEPTS):
            # Highest Bloom level where mastery > 0.55
            current = 0
            for k in range(cfg.BLOOM_LEVELS):
                if mastery_matrix[c, k] > 0.55:
                    current = k
            # Allow current and one above
            for k in range(cfg.BLOOM_LEVELS):
                if k <= current + 1:
                    mask[c * cfg.BLOOM_LEVELS + k] = True
            # L1 always available
            mask[c * cfg.BLOOM_LEVELS + 0] = True

        return mask

    def select_action(self, state: np.ndarray, mastery_matrix: np.ndarray):
        state_t = torch.FloatTensor(state).to(self.cfg.DEVICE)
        logits  = self.actor(state_t)

        mask = self.get_action_mask(mastery_matrix).to(self.cfg.DEVICE)
        logits = logits.masked_fill(~mask, float('-inf'))

        dist    = Categorical(logits=logits)
        action  = dist.sample()
        return (
            action.item(),
            dist.log_prob(action).item(),
            dist.entropy().item(),
            self.critic(state_t).item(),
        )

    def evaluate(self, states, actions):
        logits    = self.actor(states).clamp(min=-1e9)
        values    = self.critic(states).squeeze(1)
        dist      = Categorical(logits=logits)
        log_probs = dist.log_prob(actions)
        entropy   = dist.entropy()
        return log_probs, values, entropy


# ─── E. Reward Function ───────────────────────────────────────────────────────

def compute_reward(
    mastery_before : np.ndarray,   # (N_concepts, N_levels)
    mastery_after  : np.ndarray,
    concept_idx    : int,
    level          : int,          # 1-indexed
    correct        : bool,
    action_history : list,
    cfg            : Config,
) -> float:
    """
    Three-term reward (ALPN-inspired):

    R1 — mastery gain:   rewards improvement in average L1 mastery (APR).
                         Correct answers scale by remaining distance to goal.
    R2 — difficulty fit: penalises choosing a level too far from the student's
                         current competence (both too easy and too hard).
    R3 — diversity:      penalises repeating the same (concept, level) action.
    """
    k = level - 1
    C = cfg.N_CONCEPTS

    # R1 — APR gain
    apr_before = float(np.mean(mastery_before[:, 0]))
    apr_after  = float(np.mean(mastery_after[:, 0]))
    gain = apr_after - apr_before
    dist_to_goal = max(cfg.BETA_APR - apr_after, 1e-6)

    if correct:
        R1 = cfg.W_MASTERY * (gain * C) / dist_to_goal
    else:
        R1 = cfg.W_MASTERY * gain * C

    # Clamp to prevent extreme values
    R1 = float(np.clip(R1, -5.0, 10.0))

    # R2 — difficulty fit penalty
    current_k = 0
    for kk in range(cfg.BLOOM_LEVELS):
        if mastery_before[concept_idx, kk] > 0.55:
            current_k = kk
    ideal_k = min(current_k + 1, cfg.BLOOM_LEVELS - 1)
    mismatch = abs(k - ideal_k)
    # Being too easy penalised more than too hard (encourages challenge)
    dir_weight = 1.2 if k < ideal_k else 0.6
    R2 = -cfg.W_FIT * mismatch * dir_weight

    # R3 — diversity penalty
    action = concept_idx * cfg.BLOOM_LEVELS + k
    n_rep  = action_history.count(action)
    R3 = -cfg.W_DIV * n_rep if correct else 0.0

    return float(R1 + R2 + R3)


# ─── F. Rollout Buffer + GAE + PPO Update ────────────────────────────────────

class RolloutBuffer:
    def __init__(self):
        self.states    = []
        self.actions   = []
        self.log_probs = []
        self.rewards   = []
        self.values    = []
        self.entropies = []
        self.dones     = []

    def store(self, s, a, lp, r, v, e, d):
        self.states.append(s);    self.actions.append(a)
        self.log_probs.append(lp); self.rewards.append(r)
        self.values.append(v);    self.entropies.append(e)
        self.dones.append(d)

    def clear(self):  self.__init__()
    def __len__(self): return len(self.states)

    def get_tensors(self, device):
        return (
            torch.FloatTensor(np.array(self.states)).to(device),
            torch.LongTensor(self.actions).to(device),
            torch.FloatTensor(self.log_probs).to(device),
            torch.FloatTensor(self.rewards).to(device),
            torch.FloatTensor(self.values).to(device),
            torch.FloatTensor(self.entropies).to(device),
            torch.FloatTensor(self.dones).to(device),
        )


def compute_gae(rewards, values, dones, gamma, lam):
    advantages = []
    gae = 0.0
    next_val = 0.0
    for t in reversed(range(len(rewards))):
        delta = rewards[t] + gamma * next_val * (1 - dones[t]) - values[t]
        gae   = delta + gamma * lam * (1 - dones[t]) * gae
        advantages.insert(0, gae)
        next_val = values[t]
    advantages = torch.FloatTensor(advantages)
    returns    = advantages + torch.FloatTensor(values)
    return advantages, returns


def ppo_update(agent, buffer, actor_opt, critic_opt, cfg):
    states, actions, old_lp, rewards, values, stored_ent, dones = \
        buffer.get_tensors(cfg.DEVICE)

    advantages, returns = compute_gae(
        rewards.cpu().numpy(), values.cpu().numpy(),
        dones.cpu().numpy(), cfg.GAMMA, cfg.GAE_LAMBDA,
    )
    advantages = advantages.to(cfg.DEVICE)
    returns    = returns.to(cfg.DEVICE)
    if advantages.numel() > 1:
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    total_al = total_cl = total_ent = 0.0
    for _ in range(cfg.PPO_EPOCHS):
        new_lp, new_vals, cur_ent = agent.evaluate(states, actions)
        ratio  = torch.exp(new_lp - old_lp.detach())
        surr1  = ratio * advantages
        surr2  = torch.clamp(ratio, 1-cfg.CLIP_EPS, 1+cfg.CLIP_EPS) * advantages
        a_loss = -torch.min(surr1, surr2).mean()
        c_loss = nn.MSELoss()(new_vals, returns)
        # EPPO: use stored entropy (maintains early exploration signal)
        ent_bonus = stored_ent.mean()
        loss = a_loss + cfg.VALUE_COEF * c_loss - cfg.ENTROPY_COEF * ent_bonus

        actor_opt.zero_grad(); critic_opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(agent.parameters(), cfg.GRAD_CLIP)
        actor_opt.step(); critic_opt.step()

        total_al  += a_loss.item()
        total_cl  += c_loss.item()
        total_ent += ent_bonus.item()

    n = cfg.PPO_EPOCHS
    return total_al/n, total_cl/n, total_ent/n


# ─── G. PFA Pre-validation (8-test suite) ────────────────────────────────────

def _sigmoid(x): return 1 / (1 + np.exp(-x))

def run_pfa_validation(cfg: Config, sim_matrix: np.ndarray, rng):
    """Runs all 8 diagnostic tests on a fresh PFA tracker."""
    print("\n" + "="*55)
    print("  PFA VALIDATION (8 tests)")
    print("="*55)
    probe = cfg.CONCEPTS[0]
    results = {}

    def fresh():
        t = PFATracker(cfg.CONCEPTS, cfg, sim_matrix=sim_matrix)
        return t

    def make_student(tracker):
        return RealisticStudent(cfg.CONCEPTS, sim_matrix, rng, cfg)

    # ── Test 1: Always correct → monotone rise ──
    t = fresh()
    s = make_student(t)
    preds = []
    for _ in range(60):
        preds.append(t.predict(probe, 1))
        t.update(probe, 1, True)
        s.learn(t.idx[probe], 1, True)
    drops = sum(1 for a,b in zip(preds, preds[1:]) if b < a - 1e-9)
    gain  = preds[-1] - preds[0]
    t1_ok = (drops == 0 and gain > 0.05 and preds[-1] <= 1.0)
    print(f"  T1 always-correct:   start={preds[0]:.3f} end={preds[-1]:.3f} "
          f"gain={gain:+.3f}  {'PASS' if t1_ok else 'FAIL'}")
    results["t1"] = t1_ok

    # ── Test 2: Always wrong → monotone drop ──
    t = fresh(); s = make_student(t)
    preds = []
    for _ in range(60):
        preds.append(t.predict(probe, 1))
        t.update(probe, 1, False)
        s.learn(t.idx[probe], 1, False)
    rises = sum(1 for a,b in zip(preds, preds[1:]) if b > a + 1e-9)
    drop  = preds[0] - preds[-1]
    t2_ok = (rises == 0 and drop > 0.05 and preds[-1] >= 0.0)
    print(f"  T2 always-wrong:     start={preds[0]:.3f} end={preds[-1]:.3f} "
          f"drop={drop:+.3f}  {'PASS' if t2_ok else 'FAIL'}")
    results["t2"] = t2_ok

    # ── Test 3: Bloom level ordering ──
    t = fresh(); s = make_student(t)
    ci = t.idx[probe]
    for k in range(cfg.BLOOM_LEVELS):
        for _ in range(40):
            t.update(probe, k+1, True)
            s.learn(ci, k+1, True)
    final_preds = [t.predict(probe, l+1) for l in range(cfg.BLOOM_LEVELS)]
    t3_ok = all(a >= b for a, b in zip(final_preds, final_preds[1:]))
    print(f"  T3 bloom ordering:   preds={[f'{p:.2f}' for p in final_preds]}  "
          f"{'PASS' if t3_ok else 'FAIL'}")
    results["t3"] = t3_ok

    # ── Test 4: Calibration (ECE) ──
    from sklearn.metrics import roc_auc_score
    t = fresh(); s = make_student(t)
    y_true, y_pred = [], []
    for _ in range(1500):
        c_name = rng.choice(cfg.CONCEPTS)
        ci     = t.idx[c_name]
        lvl    = int(rng.integers(1, cfg.BLOOM_LEVELS+1))
        correct, true_p, _ = s.answer(ci, lvl)
        y_pred.append(t.predict(c_name, lvl))
        y_true.append(int(correct))
        t.update(c_name, lvl, correct)
        s.learn(ci, lvl, correct)
    y_true = np.array(y_true); y_pred = np.array(y_pred)
    # ECE
    ece = 0.0
    for i in range(10):
        lo, hi = i/10, (i+1)/10
        mask = (y_pred >= lo) & (y_pred < hi)
        if mask.sum() > 0:
            ece += (mask.sum()/len(y_pred)) * abs(y_true[mask].mean() - y_pred[mask].mean())
    auc = roc_auc_score(y_true, y_pred)
    t4_ok = ece < 0.10
    print(f"  T4 calibration:      ECE={ece:.4f} AUC={auc:.3f}  "
          f"{'PASS' if t4_ok else 'FAIL (ECE>=0.10)'}")
    results["ece"] = ece; results["auc"] = auc; results["t4"] = t4_ok

    # ── Test 5: Steps to mastery ──
    t = fresh(); s = make_student(t)
    ci = t.idx[probe]
    crossed = None
    for step in range(200):
        if t.predict(probe, 1) >= 0.80:
            crossed = step
            break
        t.update(probe, 1, True)
        s.learn(ci, 1, True)
    t5_ok = crossed is not None and 10 <= crossed <= 70
    print(f"  T5 steps-to-mastery: crossed 80% at step {crossed}  "
          f"{'PASS' if t5_ok else 'FAIL (tune gamma_level)'}")
    results["t5"] = t5_ok

    # ── Test 6: Propagation ordering ──
    t = fresh(); s = make_student(t)
    ci = t.idx[probe]
    sims = t.sim_matrix[ci]
    ranked = [j for j in np.argsort(-sims) if j != ci]
    near_idx, far_idx = ranked[0], ranked[-1]
    before_near = t.predict_idx(near_idx, 1)
    before_far  = t.predict_idx(far_idx,  1)
    for _ in range(30):
        t.update(probe, 1, True)
        s.learn(ci, 1, True)
    delta_near = t.predict_idx(near_idx, 1) - before_near
    delta_far  = t.predict_idx(far_idx,  1) - before_far
    ghost_ok   = (t.successes[near_idx, 0] == 0 and t.failures[near_idx, 0] == 0)
    t6_ok      = (delta_near > delta_far) and ghost_ok
    print(f"  T6 propagation:      Δnear={delta_near:+.4f} Δfar={delta_far:+.4f} "
          f"ghost_ok={ghost_ok}  {'PASS' if t6_ok else 'FAIL'}")
    results["t6"] = t6_ok

    # ── Test 7: Ghost counts ──
    t = fresh(); s = make_student(t)
    ci = t.idx[probe]
    others = [c for c in cfg.CONCEPTS if c != probe]
    baseline_s = {c: t.successes[t.idx[c]].copy() for c in others}
    baseline_f = {c: t.failures[t.idx[c]].copy()  for c in others}
    for _ in range(50):
        t.update(probe, 1, True)
        s.learn(ci, 1, True)
    ghost = any(
        not (np.allclose(baseline_s[c], t.successes[t.idx[c]]) and
             np.allclose(baseline_f[c], t.failures[t.idx[c]]))
        for c in others
    )
    t7_ok = not ghost
    print(f"  T7 ghost counts:     ghost_found={ghost}  "
          f"{'PASS' if t7_ok else 'FAIL — propagation corrupted raw counts'}")
    results["t7"] = t7_ok

    # ── Test 8: Recovery ──
    t = fresh(); s = make_student(t)
    ci = t.idx[probe]
    for _ in range(25):
        t.update(probe, 1, True);  s.learn(ci, 1, True)
    peak = t.predict(probe, 1)
    for _ in range(25):
        t.update(probe, 1, False); s.learn(ci, 1, False)
    trough = t.predict(probe, 1)
    for _ in range(25):
        t.update(probe, 1, True);  s.learn(ci, 1, True)
    recovery = t.predict(probe, 1)
    ratio = (recovery - trough) / max(peak - trough, 1e-6)
    t8_ok = ratio > 0.70
    print(f"  T8 recovery:         peak={peak:.3f} trough={trough:.3f} "
          f"recovery={recovery:.3f} ratio={ratio:.1%}  "
          f"{'PASS' if t8_ok else 'FAIL (rho too aggressive)'}")
    results["t8"] = t8_ok

    # ── Summary ──
    n_pass = sum(results[k] for k in ["t1","t2","t3","t4","t5","t6","t7","t8"])
    print(f"\n  Result: {n_pass}/8 passed | ECE={results['ece']:.4f} AUC={results['auc']:.3f}")
    print("="*55)
    return results


# ─── H. Training Loop ────────────────────────────────────────────────────────

def train(cfg: Config, save_dir="checkpoints"):
    os.makedirs(save_dir, exist_ok=True)
    rng = np.random.default_rng(42)

    # Build similarity graph once — shared across all tracker instances
    print("Building PFA similarity graph...")
    dummy_tracker = PFATracker(cfg.CONCEPTS, cfg)
    sim_matrix    = dummy_tracker.sim_matrix

    # ── Phase 0: PFA validation ──
    val_rng = np.random.default_rng(99)
    val_results = run_pfa_validation(cfg, sim_matrix, val_rng)
    if val_results["ece"] >= 0.15:
        print("WARNING: ECE >= 0.15 — PFA calibration is poor. "
              "Consider tuning GAMMA_LEVEL/RHO_LEVEL before EPPO training.")

    # ── Phase 1: PFA warm-up (random interactions) ──
    print(f"\nPhase 1 — PFA warm-up ({cfg.WARMUP_EPISODES} random episodes)...")
    # Nothing to "train" in PFA — warm-up just confirms the tracker
    # handles diverse trajectories without instability.
    warm_tracker = PFATracker(cfg.CONCEPTS, cfg, sim_matrix=sim_matrix)
    warm_student = RealisticStudent.from_archetype(
        cfg.CONCEPTS, sim_matrix, rng, cfg, "mixed")
    for ep in range(cfg.WARMUP_EPISODES):
        warm_tracker.reset()
        warm_s = RealisticStudent.from_archetype(
            cfg.CONCEPTS, sim_matrix, rng, cfg, "mixed")
        for _ in range(cfg.MAX_STEPS):
            ci  = int(rng.integers(0, cfg.N_CONCEPTS))
            lvl = int(rng.integers(1, cfg.BLOOM_LEVELS+1))
            correct, _, _ = warm_s.answer(ci, lvl)
            warm_tracker.update_idx(ci, lvl, correct)
            warm_s.learn(ci, lvl, correct)
    print("  Warm-up complete.")

    # ── Phase 2: EPPO training against frozen PFA ──
    print(f"\nPhase 2 — EPPO training ({cfg.N_EPISODES} episodes) on {cfg.DEVICE}")
    print(f"  State dim: {cfg.STATE_DIM}  |  Actions: {cfg.N_ACTIONS}  "
          f"|  Goal APR: {cfg.BETA_APR}")
    print("-"*55)

    agent      = EPPOAgent(cfg).to(cfg.DEVICE)
    buffer     = RolloutBuffer()
    actor_opt  = optim.Adam(agent.actor.parameters(),  lr=cfg.LR_ACTOR)
    critic_opt = optim.Adam(agent.critic.parameters(), lr=cfg.LR_CRITIC)

    metrics = {
        "rewards": [], "aprs": [], "steps": [], "goals": [],
        "actor_loss": [], "critic_loss": [],
    }

    for episode in range(cfg.N_EPISODES):
        # Fresh tracker + student each episode
        tracker = PFATracker(cfg.CONCEPTS, cfg, sim_matrix=sim_matrix)
        archetype = rng.choice(["beginner", "intermediate", "advanced", "mixed"])
        student   = RealisticStudent.from_archetype(
            cfg.CONCEPTS, sim_matrix, rng, cfg, archetype)

        buffer.clear()
        action_hist       = []
        ep_reward         = 0.0
        concepts_covered  = set()
        same_streak       = 0
        last_ci           = -1

        for step in range(cfg.MAX_STEPS):
            mastery   = tracker.get_mastery_matrix()
            state     = tracker.get_state_vector()
            apr       = float(np.mean(mastery[:, 0]))

            # Termination check
            all_covered  = len(concepts_covered) >= cfg.N_CONCEPTS
            can_terminate = (not cfg.MIN_COVERAGE) or all_covered
            if apr >= cfg.BETA_APR and can_terminate:
                break

            action, log_prob, entropy, value = agent.select_action(state, mastery)
            ci  = action // cfg.BLOOM_LEVELS
            lvl = action  % cfg.BLOOM_LEVELS + 1   # 1-indexed

            # Consecutive-concept guard
            if ci == last_ci:
                same_streak += 1
            else:
                same_streak = 1
            last_ci = ci

            if same_streak > cfg.MAX_SAME_CONCEPT:
                uncovered = [c for c in range(cfg.N_CONCEPTS) if c not in concepts_covered]
                if uncovered:
                    ci = int(rng.choice(uncovered))
                else:
                    weakest = int(np.argmin(mastery[:, 0]))
                    ci = weakest
                action      = ci * cfg.BLOOM_LEVELS + (lvl - 1)
                same_streak = 1
                last_ci     = ci

            action_hist.append(action)
            concepts_covered.add(ci)

            mastery_before         = mastery.copy()
            correct, true_p, p_know = student.answer(ci, lvl)
            tracker.update_idx(ci, lvl, correct)
            student.learn(ci, lvl, correct)
            mastery_after = tracker.get_mastery_matrix()

            reward = compute_reward(
                mastery_before, mastery_after,
                ci, lvl, correct, action_hist, cfg,
            )
            ep_reward += reward

            done = (step == cfg.MAX_STEPS - 1) or (
                float(np.mean(mastery_after[:, 0])) >= cfg.BETA_APR and can_terminate
            )
            buffer.store(state, action, log_prob, reward, value, entropy, float(done))
            if done:
                break

        # PPO update
        if len(buffer) > 0:
            al, cl, ent = ppo_update(agent, buffer, actor_opt, critic_opt, cfg)
        else:
            al = cl = ent = 0.0

        final_apr   = float(np.mean(tracker.get_mastery_matrix()[:, 0]))
        goal_reached = final_apr >= cfg.BETA_APR

        metrics["rewards"].append(ep_reward)
        metrics["aprs"].append(final_apr)
        metrics["steps"].append(len(action_hist))
        metrics["goals"].append(goal_reached)
        metrics["actor_loss"].append(al)
        metrics["critic_loss"].append(cl)

        if (episode + 1) % cfg.LOG_EVERY == 0:
            sl = slice(-cfg.LOG_EVERY, None)
            print(
                f"  Ep {episode+1:4d} | "
                f"Reward={np.mean(metrics['rewards'][sl]):+.2f} | "
                f"APR={np.mean(metrics['aprs'][sl]):.3f} | "
                f"Goal%={np.mean(metrics['goals'][sl])*100:.1f}% | "
                f"Steps={np.mean(metrics['steps'][sl]):.1f} | "
                f"Covered={len(concepts_covered)}/{cfg.N_CONCEPTS}"
            )

        if (episode + 1) % cfg.SAVE_EVERY == 0:
            torch.save({"agent": agent.state_dict(), "episode": episode+1,
                        "metrics": metrics},
                       os.path.join(save_dir, f"ckpt_{episode+1}.pt"))

    torch.save({"agent": agent.state_dict(), "episode": cfg.N_EPISODES,
                "metrics": metrics, "cfg": vars(cfg)},
               os.path.join(save_dir, "final.pt"))
    print("\nTraining complete.")
    return agent, sim_matrix, metrics


# ─── I. Policy Evaluation ────────────────────────────────────────────────────

def _run_episode_policy(policy_fn, cfg, sim_matrix, rng, n_students=200):
    """Run N students through a policy, return summary dict."""
    aprs, steps, goals = [], [], []
    diff_counts = np.zeros(cfg.BLOOM_LEVELS)

    for _ in range(n_students):
        tracker  = PFATracker(cfg.CONCEPTS, cfg, sim_matrix=sim_matrix)
        student  = RealisticStudent.from_archetype(
            cfg.CONCEPTS, sim_matrix, rng, cfg, "mixed")
        concepts_covered = set()

        for step in range(cfg.MAX_STEPS):
            mastery = tracker.get_mastery_matrix()
            apr     = float(np.mean(mastery[:, 0]))
            all_cov = len(concepts_covered) >= cfg.N_CONCEPTS
            if apr >= cfg.BETA_APR and ((not cfg.MIN_COVERAGE) or all_cov):
                break

            ci, lvl = policy_fn(tracker, mastery, rng, cfg)
            diff_counts[lvl-1] += 1
            concepts_covered.add(ci)

            correct, _, _ = student.answer(ci, lvl)
            tracker.update_idx(ci, lvl, correct)
            student.learn(ci, lvl, correct)

        final_apr = float(np.mean(tracker.get_mastery_matrix()[:, 0]))
        aprs.append(final_apr)
        steps.append(step + 1)
        goals.append(final_apr >= cfg.BETA_APR)

    return {
        "mean_apr":   float(np.mean(aprs)),
        "std_apr":    float(np.std(aprs)),
        "goal_rate":  float(np.mean(goals)) * 100,
        "mean_steps": float(np.mean(steps)),
        "diff_dist":  diff_counts / max(diff_counts.sum(), 1),
    }


def _eppo_policy(agent):
    def fn(tracker, mastery, rng, cfg):
        state = tracker.get_state_vector()
        with torch.no_grad():
            action, _, _, _ = agent.select_action(state, mastery)
        ci  = action // cfg.BLOOM_LEVELS
        lvl = action  % cfg.BLOOM_LEVELS + 1
        return ci, lvl
    return fn

def _random_policy(tracker, mastery, rng, cfg):
    ci  = int(rng.integers(0, cfg.N_CONCEPTS))
    lvl = int(rng.integers(1, cfg.BLOOM_LEVELS+1))
    return ci, lvl

def _greedy_policy(tracker, mastery, rng, cfg):
    """Always pick weakest concept at its ideal Bloom level."""
    weakest_ci = int(np.argmin(mastery[:, 0]))
    current_k  = max((k for k in range(cfg.BLOOM_LEVELS) if mastery[weakest_ci, k] > 0.55),
                     default=0)
    ideal_k    = min(current_k + 1, cfg.BLOOM_LEVELS - 1)
    return weakest_ci, ideal_k + 1


def evaluate_policies(agent, cfg, sim_matrix, n_students=200):
    rng = np.random.default_rng(77)
    agent.eval()

    print("\n" + "="*55)
    print("  POLICY COMPARISON")
    print("="*55)
    print(f"  Students per policy: {n_students} | Goal APR: {cfg.BETA_APR}")

    policies = {
        "EPPO":   _run_episode_policy(_eppo_policy(agent),  cfg, sim_matrix, rng, n_students),
        "Random": _run_episode_policy(_random_policy,       cfg, sim_matrix, rng, n_students),
        "Greedy": _run_episode_policy(_greedy_policy,       cfg, sim_matrix, rng, n_students),
    }

    W = 10
    print(f"\n  {'Metric':<22} {'EPPO':>{W}} {'Random':>{W}} {'Greedy':>{W}}")
    print("  " + "-"*52)
    for label, key, fmt in [
        ("Mean APR",    "mean_apr",   ".3f"),
        ("Std APR",     "std_apr",    ".3f"),
        ("Goal %",      "goal_rate",  ".1f"),
        ("Mean steps",  "mean_steps", ".1f"),
    ]:
        row = f"  {label:<22}"
        for p in ["EPPO", "Random", "Greedy"]:
            row += f" {policies[p][key]:>{W}{fmt}}"
        print(row)

    print(f"\n  {'Bloom distribution':<22}", end="")
    for p in ["EPPO", "Random", "Greedy"]:
        d = policies[p]["diff_dist"] * 100
        print(f" {'L1-L6: '+'/'.join(f'{v:.0f}' for v in d):>{W}}", end="")
    print()

    eppo  = policies["EPPO"]
    rnd   = policies["Random"]
    grdy  = policies["Greedy"]
    beats_random = eppo["mean_apr"] > rnd["mean_apr"]
    beats_greedy = eppo["mean_apr"] > grdy["mean_apr"] or eppo["mean_steps"] < grdy["mean_steps"]
    print(f"\n  vs Random: {'EPPO wins (+{:.3f} APR)'.format(eppo['mean_apr']-rnd['mean_apr']) if beats_random else 'Random wins — need more training'}")
    print(f"  vs Greedy: {'EPPO wins' if beats_greedy else 'Greedy wins — EPPO not converged yet'}")
    print("="*55)
    return policies


# ─── J. Demo Session ─────────────────────────────────────────────────────────

def run_demo(agent, cfg, sim_matrix, seed=123):
    """Print a step-by-step trace of one EPPO session."""
    rng     = np.random.default_rng(seed)
    tracker = PFATracker(cfg.CONCEPTS, cfg, sim_matrix=sim_matrix)
    student = RealisticStudent.from_archetype(
        cfg.CONCEPTS, sim_matrix, rng, cfg, "mixed")
    agent.eval()

    bloom_names = ["Recall", "Understand", "Apply", "Analyse", "Evaluate", "Create"]

    print("\n" + "="*72)
    print("  DEMO SESSION — step by step")
    print("="*72)
    print(f"  Goal: APR >= {cfg.BETA_APR}")
    print(f"\n  {'Step':>4}  {'Concept':<24} {'Level':<12} {'Mast':>6} {'Ans':>8} {'APR':>6}")
    print("  " + "-"*66)

    for step in range(cfg.MAX_STEPS):
        mastery = tracker.get_mastery_matrix()
        apr     = float(np.mean(mastery[:, 0]))
        if apr >= cfg.BETA_APR and len({
            s for s in range(step) if True}) >= 0:
            print(f"\n  Goal reached at step {step}!  Final APR = {apr:.3f}")
            break

        state = tracker.get_state_vector()
        with torch.no_grad():
            action, _, _, _ = agent.select_action(state, mastery)
        ci  = action // cfg.BLOOM_LEVELS
        lvl = action  % cfg.BLOOM_LEVELS + 1
        concept = cfg.CONCEPTS[ci]
        m_val   = mastery[ci, lvl-1]

        correct, true_p, p_know = student.answer(ci, lvl)
        tracker.update_idx(ci, lvl, correct)
        student.learn(ci, lvl, correct)

        ans_str = "CORRECT" if correct else "wrong  "
        print(f"  {step+1:>4}  {concept:<24} {bloom_names[lvl-1]:<12} "
              f"{m_val:>6.2f} {ans_str:>8} {apr:>6.3f}")

    print()
    mastery = tracker.get_mastery_matrix()
    print(f"  {'Concept':<24} {'L1':>5} {'L2':>5} {'L3':>5} {'L4':>5} {'L5':>5} {'L6':>5}  Progress")
    print("  " + "-"*70)
    for i, c in enumerate(cfg.CONCEPTS):
        vals = [mastery[i, k] for k in range(cfg.BLOOM_LEVELS)]
        bar  = "█" * int(vals[0] * 10) + "░" * (10 - int(vals[0] * 10))
        print(f"  {c:<24} " + " ".join(f"{v:>5.2f}" for v in vals) + f"  {bar}")


# ─── K. Diagnostic Plots ─────────────────────────────────────────────────────

def plot_training_curves(metrics, cfg, save_path="training_curves.png"):
    import matplotlib.pyplot as plt

    def smooth(x, w=50):
        if len(x) < w: return np.array(x)
        return np.convolve(x, np.ones(w)/w, mode='valid')

    fig, axes = plt.subplots(1, 4, figsize=(18, 4))

    axes[0].plot(smooth(metrics["aprs"]), color="steelblue", lw=2)
    axes[0].axhline(cfg.BETA_APR, color="red", ls="--", alpha=0.7, label=f"goal={cfg.BETA_APR}")
    axes[0].set_title("Average pass rate"); axes[0].set_ylim(0,1)
    axes[0].legend(); axes[0].grid(alpha=0.3)

    axes[1].plot(smooth(metrics["rewards"]), color="darkorange", lw=2)
    axes[1].set_title("Episode reward"); axes[1].grid(alpha=0.3)

    goal_rate = smooth([float(g) for g in metrics["goals"]])
    axes[2].plot(goal_rate * 100, color="green", lw=2)
    axes[2].set_title("Goal reached %"); axes[2].set_ylim(0,100)
    axes[2].grid(alpha=0.3)

    axes[3].plot(smooth(metrics["actor_loss"]), label="actor", lw=1.5)
    axes[3].plot(smooth(metrics["critic_loss"]), label="critic", lw=1.5)
    axes[3].set_title("PPO losses"); axes[3].legend(); axes[3].grid(alpha=0.3)

    for ax in axes:
        ax.set_xlabel("Episode")
    plt.tight_layout()
    plt.savefig(save_path, dpi=120)
    plt.show()
    print(f"Saved {save_path}")


def plot_policy_comparison(policies, cfg, save_path="policy_comparison.png"):
    import matplotlib.pyplot as plt

    labels = list(policies.keys())
    colors = ["steelblue", "tomato", "seagreen"]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))

    vals = [policies[p]["mean_apr"] for p in labels]
    axes[0].bar(labels, vals, color=colors)
    axes[0].axhline(cfg.BETA_APR, ls="--", color="black", alpha=0.5)
    axes[0].set_title("Mean final APR"); axes[0].set_ylim(0,1)

    vals = [policies[p]["goal_rate"] for p in labels]
    axes[1].bar(labels, vals, color=colors)
    axes[1].set_title("Goal reached %"); axes[1].set_ylim(0,100)

    vals = [policies[p]["mean_steps"] for p in labels]
    axes[2].bar(labels, vals, color=colors)
    axes[2].set_title("Mean steps to finish")

    plt.tight_layout()
    plt.savefig(save_path, dpi=120)
    plt.show()
    print(f"Saved {save_path}")


def plot_bloom_distribution(policies, cfg, save_path="bloom_dist.png"):
    import matplotlib.pyplot as plt
    bloom_names = ["L1\nRecall","L2\nUnderstand","L3\nApply",
                   "L4\nAnalyse","L5\nEvaluate","L6\nCreate"]
    x = np.arange(cfg.BLOOM_LEVELS)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    colors = ["steelblue", "tomato", "seagreen"]
    for ax, (p, col) in zip(axes, zip(policies.keys(), colors)):
        ax.bar(x, policies[p]["diff_dist"]*100, color=col, alpha=0.85)
        ax.set_title(f"{p} — Bloom distribution")
        ax.set_xticks(x); ax.set_xticklabels(bloom_names, fontsize=8)
        ax.set_ylabel("% of actions")
    plt.tight_layout()
    plt.savefig(save_path, dpi=120)
    plt.show()
    print(f"Saved {save_path}")


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = Config()

    print("=" * 55)
    print("  PFA + EPPO Adaptive Learning — POC")
    print("=" * 55)
    print(f"  Concepts  : {cfg.N_CONCEPTS}")
    print(f"  Actions   : {cfg.N_ACTIONS} ({cfg.N_CONCEPTS} concepts × {cfg.BLOOM_LEVELS} Bloom levels)")
    print(f"  State dim : {cfg.STATE_DIM}")
    print(f"  Device    : {cfg.DEVICE}")
    print()

    agent, sim_matrix, metrics = train(cfg, save_dir="checkpoints")

    policies = evaluate_policies(agent, cfg, sim_matrix, n_students=300)

    run_demo(agent, cfg, sim_matrix)

    plot_training_curves(metrics, cfg, "training_curves.png")
    plot_policy_comparison(policies, cfg, "policy_comparison.png")
    plot_bloom_distribution(policies, cfg, "bloom_dist.png")
