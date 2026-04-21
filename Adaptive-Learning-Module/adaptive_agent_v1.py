"""
Adaptive Learning Module — Basic Implementation
================================================
Phase 1: Fixed concept set, standard simpleKT (ID-based), EPPO with 3 difficulty levels.

This version is designed to:
  - Run fully on Colab free tier (T4 GPU or CPU)
  - Train in under 30 minutes
  - Prove the full loop: KT state -> EPPO decision -> reward -> update
  - Be easy to inspect and debug before scaling up

Scaling to dynamic concepts (Phase 2) only requires:
  - Replacing the concept ID embedding with a sentence encoder projection
  - Everything else (EPPO, reward, state, training loop) stays identical
"""

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Categorical
from collections import deque
import random
import copy
import os

# ─── Configuration ────────────────────────────────────────────────────────────

class Config:
    # Concept set — fixed small set for Phase 1
    # In Phase 2, these will be extracted dynamically from uploaded material
    CONCEPTS = [
        "arrays",
        "pointers",
        "linked lists",
        "binary search trees",
        "recursion",
        "sorting algorithms",
        "dynamic programming",
        "process scheduling",
        "memory management",
        "TCP IP basics",
    ]
    N_CONCEPTS      = len(CONCEPTS)   # 10

    # Difficulty levels
    DIFF_LEVELS     = 3               # 0=easy, 1=medium, 2=hard
    DIFF_NAMES      = ["easy", "medium", "hard"]

    # Action space: concept × difficulty
    N_ACTIONS       = N_CONCEPTS * DIFF_LEVELS   # 30

    # simpleKT
    KT_EMBED_DIM    = 64    # concept embedding dimension
    KT_HEADS        = 4     # transformer attention heads
    KT_LAYERS       = 2     # transformer encoder layers
    KT_DROPOUT      = 0.1
    KT_SEQ_LEN      = 20    # max interaction sequence length

    # EPPO
    STATE_DIM       = N_CONCEPTS * DIFF_LEVELS   # 30 — mastery per (concept, diff)
    HIDDEN_DIM      = 128
    LR_ACTOR        = 3e-4
    LR_CRITIC       = 3e-4
    GAMMA           = 0.99
    GAE_LAMBDA      = 0.95
    CLIP_EPS        = 0.2
    ENTROPY_COEF    = 0.01
    VALUE_COEF      = 0.5
    PPO_EPOCHS      = 4
    BUFFER_SIZE     = 512

    # Training
    N_EPISODES      = 1000   # enough to see convergence on small concept set
    MAX_STEPS       = 30     # max interactions per session
    BETA            = 0.75   # learning goal (APR threshold)
    SAVE_EVERY      = 100    # save checkpoint every N episodes
    LOG_EVERY       = 50     # print metrics every N episodes

    # Reward weights
    ALPHA           = 0.3    # cognitive gain weight
    GAMMA_FIT       = 0.15   # question fit penalty weight

    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ─── simpleKT Model ───────────────────────────────────────────────────────────

class SimpleKT(nn.Module):
    """
    Simplified simpleKT for Phase 1.

    Input per interaction: (concept_id, diff_level, correct)
    Encoded as: concept_embed + diff_embed + correct_embed  -> transformer
    Output: mastery probability per (concept, difficulty) pair

    In Phase 2: concept_embed lookup replaced by Linear(384, KT_EMBED_DIM)
    fed from a sentence transformer. Everything else unchanged.
    """

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        d = cfg.KT_EMBED_DIM

        # --- Input embeddings ---
        # Phase 1: standard lookup table, one row per concept
        # Phase 2: this gets replaced by sentence_encoder + Linear(384, d)
        self.concept_embed  = nn.Embedding(cfg.N_CONCEPTS, d)

        # Difficulty level embedding (3 levels) — stays in Phase 2
        self.diff_embed     = nn.Embedding(cfg.DIFF_LEVELS, d)

        # Correctness embedding (2 values) — stays in Phase 2
        self.correct_embed  = nn.Embedding(2, d)

        # --- Transformer encoder ---
        encoder_layer = nn.TransformerEncoderLayer(
            d_model    = d,
            nhead      = cfg.KT_HEADS,
            dim_feedforward = d * 4,
            dropout    = cfg.KT_DROPOUT,
            batch_first = True
        )
        self.transformer = nn.TransformerEncoder(
            encoder_layer,
            num_layers = cfg.KT_LAYERS
        )

        # --- Mastery predictor ---
        # Input: student state z_t (d) + target concept embed (d) + target diff embed (d)
        # Output: single mastery probability
        self.predictor = nn.Sequential(
            nn.Linear(d * 3, d),
            nn.ReLU(),
            nn.Linear(d, 1),
            nn.Sigmoid()
        )

    def forward(self, concept_ids, diff_levels, corrects):
        """
        Forward pass over an interaction sequence.

        Args:
            concept_ids : LongTensor (batch, seq_len)
            diff_levels : LongTensor (batch, seq_len)
            corrects    : LongTensor (batch, seq_len)

        Returns:
            mastery_matrix : FloatTensor (batch, N_CONCEPTS, DIFF_LEVELS)
        """
        c = self.concept_embed(concept_ids)    # (B, T, d)
        d = self.diff_embed(diff_levels)       # (B, T, d)
        r = self.correct_embed(corrects)       # (B, T, d)
        x = c + d + r                          # (B, T, d)

        # Causal mask — student can only attend to past interactions
        T = x.size(1)
        mask = nn.Transformer.generate_square_subsequent_mask(T).to(x.device)
        z = self.transformer(x, mask=mask, is_causal=True)   # (B, T, d)
        student_state = z[:, -1, :]                           # (B, d) — last step

        B = student_state.size(0)
        cfg = self.cfg

        # Query mastery for every (concept, difficulty) pair
        mastery = torch.zeros(B, cfg.N_CONCEPTS, cfg.DIFF_LEVELS, device=x.device)

        for j in range(cfg.N_CONCEPTS):
            c_vec = self.concept_embed(
                torch.full((B,), j, dtype=torch.long, device=x.device)
            )   # (B, d)

            for diff in range(cfg.DIFF_LEVELS):
                d_vec = self.diff_embed(
                    torch.full((B,), diff, dtype=torch.long, device=x.device)
                )   # (B, d)

                inp = torch.cat([student_state, c_vec, d_vec], dim=1)  # (B, 3d)
                mastery[:, j, diff] = self.predictor(inp).squeeze(1)

        return mastery   # (B, N_CONCEPTS, DIFF_LEVELS)

    def predict_single(self, history):
        """
        Inference for a single student given interaction history.

        Args:
            history: list of (concept_idx, diff_level, correct) tuples

        Returns:
            mastery_matrix: np.ndarray (N_CONCEPTS, DIFF_LEVELS)
        """
        cfg = self.cfg
        if not history:
            return np.full((cfg.N_CONCEPTS, cfg.DIFF_LEVELS), 0.5)

        device = next(self.parameters()).device

        concept_ids = torch.LongTensor([[h[0] for h in history]]).to(device)
        diff_levels = torch.LongTensor([[h[1] for h in history]]).to(device)
        corrects    = torch.LongTensor([[h[2] for h in history]]).to(device)

        # Truncate to max sequence length
        if concept_ids.shape[1] > cfg.KT_SEQ_LEN:
            concept_ids = concept_ids[:, -cfg.KT_SEQ_LEN:]
            diff_levels = diff_levels[:, -cfg.KT_SEQ_LEN:]
            corrects    = corrects[:, -cfg.KT_SEQ_LEN:]

        with torch.no_grad():
            mastery = self(concept_ids, diff_levels, corrects)

        return mastery[0].cpu().numpy()   # (N_CONCEPTS, DIFF_LEVELS)


# ─── EPPO Agent ───────────────────────────────────────────────────────────────

class EPPOAgent(nn.Module):
    """
    Entropy-enhanced Proximal Policy Optimization agent.

    State  : mastery_matrix flattened = (N_CONCEPTS * DIFF_LEVELS,) = 30-dim
    Action : (concept_idx, diff_level) encoded as concept_idx * 3 + diff_level
    """

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg

        # Actor network — outputs logits over all actions
        self.actor = nn.Sequential(
            nn.Linear(cfg.STATE_DIM, cfg.HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM, cfg.HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM, cfg.N_ACTIONS)
        )

        # Critic network — estimates state value
        self.critic = nn.Sequential(
            nn.Linear(cfg.STATE_DIM, cfg.HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM, cfg.HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(cfg.HIDDEN_DIM, 1)
        )

    def get_action_mask(self, mastery_matrix: np.ndarray) -> torch.BoolTensor:
        """
        Prevents EPPO from jumping more than 1 difficulty level above
        the student's current competence on each concept.

        Current competence = highest difficulty where mastery > 0.6
        Allowed = current and one above.
        """
        cfg = self.cfg
        mask = torch.zeros(cfg.N_ACTIONS, dtype=torch.bool)

        for j in range(cfg.N_CONCEPTS):
            # Find current competence level
            current = 0
            for d in range(cfg.DIFF_LEVELS):
                if mastery_matrix[j, d] > 0.6:
                    current = d

            # Allow current level and one above
            for d in range(cfg.DIFF_LEVELS):
                if abs(d - current) <= 1:
                    action = j * cfg.DIFF_LEVELS + d
                    mask[action] = True

        return mask

    def select_action(self, state: np.ndarray, mastery_matrix: np.ndarray):
        """
        Select action given current state.

        Returns:
            action       : int
            log_prob     : float
            entropy      : float
            value        : float
        """
        state_t = torch.FloatTensor(state).to(self.cfg.DEVICE)
        logits  = self.actor(state_t)

        # Apply action mask
        mask = self.get_action_mask(mastery_matrix).to(self.cfg.DEVICE)
        logits[~mask] = float('-inf')

        dist    = Categorical(logits=logits)
        action  = dist.sample()

        return (
            action.item(),
            dist.log_prob(action).item(),
            dist.entropy().item(),
            self.critic(state_t).item()
        )

    def evaluate(self, states, actions):
        """Used during PPO update to get new log probs and values.

        During collection, select_action() writes -inf into masked logits.
        Those states are stored in the buffer and replayed here. Categorical
        cannot handle -inf (log-sum-exp produces NaN). Clamping to a large
        finite negative keeps softmax numerically valid — masked actions still
        get ~0 probability, and the collected actions are already valid so
        the clamp does not change which action was taken.
        """
        logits = self.actor(states)
        logits = logits.clamp(min=-1e9)          # guard against -inf → NaN
        values = self.critic(states).squeeze(1)
        dist      = Categorical(logits=logits)
        log_probs = dist.log_prob(actions)
        entropy   = dist.entropy()
        return log_probs, values, entropy


# ─── Student State ────────────────────────────────────────────────────────────

class StudentState:
    """
    Holds the current state of one student session.
    """

    def __init__(self, cfg: Config, initial_mastery: np.ndarray = None):
        self.cfg     = cfg
        self.history = []   # list of (concept_idx, diff_level, correct)

        if initial_mastery is not None:
            self.mastery = initial_mastery.copy()
        else:
            # Uniform uncertainty as starting point
            self.mastery = np.full(
                (cfg.N_CONCEPTS, cfg.DIFF_LEVELS), 0.5
            )

    def update_from_kt(self, kt_model: SimpleKT):
        """Run KT model over full history to get updated mastery."""
        self.mastery = kt_model.predict_single(self.history)

    def get_state_vector(self) -> np.ndarray:
        """Flatten mastery matrix to EPPO state vector."""
        return self.mastery.flatten()   # (N_CONCEPTS * DIFF_LEVELS,)

    def get_apr(self) -> float:
        """Average pass rate = mean of easy mastery (most conservative)."""
        return float(np.mean(self.mastery[:, 0]))

    def get_weighted_apr(self) -> float:
        """Weighted APR: easy=0.5, medium=0.3, hard=0.2"""
        weights = np.array([0.5, 0.3, 0.2])
        return float(np.mean(self.mastery @ weights))


# ─── Simulation Environment ───────────────────────────────────────────────────

class SimulatedStudentEnv:
    """
    Simulates student answers for training EPPO.

    In production this is replaced by real student answers.
    The simulation models:
      - Student has a hidden true mastery per (concept, difficulty)
      - Correct answer probability depends on true mastery and question difficulty
      - Answering correctly increases mastery slightly
      - Answering incorrectly decreases mastery slightly
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def sample_student(self):
        """
        Sample a random student profile.
        Returns hidden true mastery: (N_CONCEPTS, DIFF_LEVELS)
        """
        cfg = self.cfg

        # Base mastery — varies per student archetype
        archetype = random.choice(["beginner", "intermediate", "advanced"])

        if archetype == "beginner":
            base = np.random.uniform(0.1, 0.4, cfg.N_CONCEPTS)
        elif archetype == "intermediate":
            base = np.random.uniform(0.3, 0.6, cfg.N_CONCEPTS)
        else:
            base = np.random.uniform(0.5, 0.8, cfg.N_CONCEPTS)

        # Mastery decreases as difficulty increases
        true_mastery = np.zeros((cfg.N_CONCEPTS, cfg.DIFF_LEVELS))
        for j in range(cfg.N_CONCEPTS):
            true_mastery[j, 0] = np.clip(base[j] + 0.15, 0, 1)         # easy
            true_mastery[j, 1] = np.clip(base[j], 0, 1)                 # medium
            true_mastery[j, 2] = np.clip(base[j] - 0.2, 0.05, 1)       # hard

        return true_mastery

    def answer(self, true_mastery: np.ndarray, concept_idx: int, diff_level: int):
        """
        Simulate student answering a question.

        Returns:
            correct: bool
            updated_true_mastery: np.ndarray (in-place update)
        """
        p = true_mastery[concept_idx, diff_level]

        # Add some noise to make it realistic
        p_noisy = np.clip(p + np.random.normal(0, 0.05), 0.05, 0.95)
        correct = int(np.random.random() < p_noisy)

        # Learning effect — answering updates true mastery
        lr = 0.04
        if correct:
            true_mastery[concept_idx, diff_level] = min(
                1.0, p + lr * (1 - p)
            )
            # Positive spillover to easier levels
            if diff_level > 0:
                true_mastery[concept_idx, diff_level - 1] = min(
                    1.0,
                    true_mastery[concept_idx, diff_level - 1] + lr * 0.3
                )
        else:
            true_mastery[concept_idx, diff_level] = max(
                0.0, p - lr * 0.5 * p
            )

        return correct


# ─── Reward Function ──────────────────────────────────────────────────────────

def compute_reward(
    mastery_before: np.ndarray,    # (N_CONCEPTS, DIFF_LEVELS)
    mastery_after:  np.ndarray,    # (N_CONCEPTS, DIFF_LEVELS)
    concept_idx:    int,
    diff_level:     int,
    correct:        bool,
    action_history: list,
    cfg:            Config
) -> float:
    """
    Four-term reward function.

    T1: Mastery gain       — rewards APR improvement (from ALPN paper)
    T2: Difficulty gain    — rewards improving at harder levels
    T3: Fit penalty        — penalizes choosing wrong difficulty
    T4: Diversity penalty  — penalizes repeating same (concept, difficulty)
    """
    J = cfg.N_CONCEPTS

    # --- T1: Mastery gain (ALPN paper Eq. 6) ---
    apr_before = float(np.mean(mastery_before[:, 0]))
    apr_after  = float(np.mean(mastery_after[:, 0]))
    LG = apr_after - apr_before
    dt = max(cfg.BETA - apr_after, 1e-6)

    if correct:
        T1 = (LG * J) / dt
    else:
        T1 = LG * J

    # --- T2: Difficulty progression gain ---
    m_before = mastery_before[concept_idx, diff_level]
    m_after  = mastery_after[concept_idx, diff_level]
    diff_gain = m_after - m_before
    # Hard questions worth more
    diff_weight = (diff_level + 1) / cfg.DIFF_LEVELS
    T2 = cfg.ALPHA * diff_gain * diff_weight

    # --- T3: Question fit penalty ---
    # Find student's current competence level on this concept
    current_d = 0
    for d in range(cfg.DIFF_LEVELS):
        if mastery_before[concept_idx, d] > 0.6:
            current_d = d
    ideal_d = min(current_d + 1, cfg.DIFF_LEVELS - 1)
    mismatch = abs(diff_level - ideal_d)

    # Being too easy is penalized more than being too hard
    if diff_level < ideal_d:
        dir_w = 1.0 + mastery_before[concept_idx, diff_level]
    else:
        dir_w = 0.5

    T3 = cfg.GAMMA_FIT * mismatch * dir_w

    # --- T4: Diversity penalty (ALPN paper Eq. 5) ---
    action = concept_idx * cfg.DIFF_LEVELS + diff_level
    n_repeats = action_history.count(action)
    d1 = cfg.BETA - apr_before
    lam = (max(d1, 0) * J) / cfg.MAX_STEPS
    T4 = lam * n_repeats if correct else 0.0

    return float(T1 + T2 - T3 - T4)


# ─── Replay Buffer ────────────────────────────────────────────────────────────

class RolloutBuffer:
    """Stores one episode of transitions for PPO update."""

    def __init__(self):
        self.states     = []
        self.actions    = []
        self.log_probs  = []
        self.rewards    = []
        self.values     = []
        self.entropies  = []   # EPPO: stored entropy from interaction time
        self.dones      = []

    def store(self, state, action, log_prob, reward, value, entropy, done):
        self.states.append(state)
        self.actions.append(action)
        self.log_probs.append(log_prob)
        self.rewards.append(reward)
        self.values.append(value)
        self.entropies.append(entropy)
        self.dones.append(done)

    def clear(self):
        self.__init__()

    def __len__(self):
        return len(self.states)

    def get_tensors(self, device):
        states    = torch.FloatTensor(np.array(self.states)).to(device)
        actions   = torch.LongTensor(self.actions).to(device)
        log_probs = torch.FloatTensor(self.log_probs).to(device)
        rewards   = torch.FloatTensor(self.rewards).to(device)
        values    = torch.FloatTensor(self.values).to(device)
        entropies = torch.FloatTensor(self.entropies).to(device)
        dones     = torch.FloatTensor(self.dones).to(device)
        return states, actions, log_probs, rewards, values, entropies, dones


# ─── PPO Update ───────────────────────────────────────────────────────────────

def compute_gae(rewards, values, dones, gamma, lam):
    """Generalized Advantage Estimation."""
    advantages = []
    gae = 0
    next_value = 0

    for t in reversed(range(len(rewards))):
        delta = rewards[t] + gamma * next_value * (1 - dones[t]) - values[t]
        gae   = delta + gamma * lam * (1 - dones[t]) * gae
        advantages.insert(0, gae)
        next_value = values[t]

    advantages = torch.FloatTensor(advantages)
    returns    = advantages + torch.FloatTensor(values)
    return advantages, returns


def ppo_update(agent, buffer, actor_opt, critic_opt, cfg):
    """
    EPPO update — uses stored entropy from buffer (not current policy entropy).
    This is the key modification vs vanilla PPO.
    """
    states, actions, old_log_probs, rewards, values, \
        stored_entropies, dones = buffer.get_tensors(cfg.DEVICE)

    advantages, returns = compute_gae(
        rewards.cpu().numpy(),
        values.cpu().numpy(),
        dones.cpu().numpy(),
        cfg.GAMMA,
        cfg.GAE_LAMBDA
    )
    advantages = advantages.to(cfg.DEVICE)
    returns    = returns.to(cfg.DEVICE)

    # Normalize advantages — skip when buffer has only 1 step (std undefined,
    # triggers UserWarning and returns NaN with degrees-of-freedom = 0)
    if advantages.numel() > 1:
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    total_actor_loss  = 0
    total_critic_loss = 0
    total_entropy     = 0

    for _ in range(cfg.PPO_EPOCHS):
        new_log_probs, new_values, current_entropy = agent.evaluate(
            states, actions
        )

        ratio = torch.exp(new_log_probs - old_log_probs.detach())

        # Clipped surrogate objective
        surr1 = ratio * advantages
        surr2 = torch.clamp(ratio, 1 - cfg.CLIP_EPS, 1 + cfg.CLIP_EPS) * advantages
        actor_loss = -torch.min(surr1, surr2).mean()

        # Value function loss
        critic_loss = nn.MSELoss()(new_values, returns)

        # EPPO entropy bonus — use STORED entropy from buffer, not current
        # This maintains high exploration from early training
        entropy_bonus = stored_entropies.mean()

        # Full objective
        loss = (
            actor_loss
            + cfg.VALUE_COEF  * critic_loss
            - cfg.ENTROPY_COEF * entropy_bonus
        )

        actor_opt.zero_grad()
        critic_opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(agent.parameters(), 0.5)
        actor_opt.step()
        critic_opt.step()

        total_actor_loss  += actor_loss.item()
        total_critic_loss += critic_loss.item()
        total_entropy     += entropy_bonus.item()

    n = cfg.PPO_EPOCHS
    return total_actor_loss/n, total_critic_loss/n, total_entropy/n


# ─── Training Loop ────────────────────────────────────────────────────────────

def train(cfg: Config, save_dir: str = "checkpoints"):
    """
    Full training loop.
    Trains both simpleKT and EPPO jointly in simulation.
    """
    os.makedirs(save_dir, exist_ok=True)

    # Models
    kt_model = SimpleKT(cfg).to(cfg.DEVICE)
    agent    = EPPOAgent(cfg).to(cfg.DEVICE)
    env      = SimulatedStudentEnv(cfg)
    buffer   = RolloutBuffer()

    # Optimizers
    kt_opt      = optim.Adam(kt_model.parameters(), lr=1e-3)
    actor_opt   = optim.Adam(agent.actor.parameters(),  lr=cfg.LR_ACTOR)
    critic_opt  = optim.Adam(agent.critic.parameters(), lr=cfg.LR_CRITIC)

    kt_criterion = nn.BCELoss()

    # Metrics
    episode_rewards  = []
    episode_lengths  = []
    episode_aprs     = []
    goal_reached     = []

    print(f"Training on: {cfg.DEVICE}")
    print(f"Concepts: {cfg.N_CONCEPTS}  |  Actions: {cfg.N_ACTIONS}  |  Episodes: {cfg.N_EPISODES}")
    print("-" * 60)

    for episode in range(cfg.N_EPISODES):

        # --- Sample a student ---
        true_mastery = env.sample_student()
        student      = StudentState(cfg)
        action_hist  = []
        ep_reward    = 0
        buffer.clear()

        for step in range(cfg.MAX_STEPS):

            # Get current state from KT model
            student.update_from_kt(kt_model)
            state = student.get_state_vector()
            apr   = student.get_apr()

            # Check if learning goal reached
            if apr >= cfg.BETA:
                break

            # EPPO selects action
            action, log_prob, entropy, value = agent.select_action(
                state, student.mastery
            )
            concept_idx = action // cfg.DIFF_LEVELS
            diff_level  = action  % cfg.DIFF_LEVELS
            action_hist.append(action)

            # Simulate student answer
            mastery_before = student.mastery.copy()
            correct        = env.answer(true_mastery, concept_idx, diff_level)

            # Add to KT history and update state
            student.history.append((concept_idx, diff_level, correct))
            student.update_from_kt(kt_model)

            # Compute reward
            reward = compute_reward(
                mastery_before, student.mastery,
                concept_idx, diff_level, correct,
                action_hist, cfg
            )
            ep_reward += reward

            # Check done
            done = (student.get_apr() >= cfg.BETA or
                    step == cfg.MAX_STEPS - 1)

            buffer.store(state, action, log_prob, reward, value, entropy, done)

            if done:
                break

        # --- Train simpleKT on this episode's interactions ---
        if len(student.history) >= 2:
            kt_loss = train_kt_step(kt_model, kt_opt, kt_criterion,
                                    student.history, cfg)
        else:
            kt_loss = 0.0

        # --- EPPO update ---
        if len(buffer) > 0:
            a_loss, c_loss, ent = ppo_update(
                agent, buffer, actor_opt, critic_opt, cfg
            )
        else:
            a_loss = c_loss = ent = 0.0

        # --- Logging ---
        final_apr     = student.get_apr()
        reached_goal  = final_apr >= cfg.BETA
        episode_rewards.append(ep_reward)
        episode_lengths.append(len(student.history))
        episode_aprs.append(final_apr)
        goal_reached.append(reached_goal)

        if (episode + 1) % cfg.LOG_EVERY == 0:
            recent = slice(-cfg.LOG_EVERY, None)
            print(
                f"Ep {episode+1:4d} | "
                f"Reward: {np.mean(episode_rewards[recent]):+.3f} | "
                f"APR: {np.mean(episode_aprs[recent]):.3f} | "
                f"Goal%: {np.mean(goal_reached[recent])*100:.1f}% | "
                f"Steps: {np.mean(episode_lengths[recent]):.1f} | "
                f"KT loss: {kt_loss:.4f}"
            )

        # --- Checkpoint ---
        if (episode + 1) % cfg.SAVE_EVERY == 0:
            torch.save({
                "kt_state":    kt_model.state_dict(),
                "eppo_state":  agent.state_dict(),
                "episode":     episode + 1,
                "rewards":     episode_rewards,
                "aprs":        episode_aprs,
            }, os.path.join(save_dir, f"checkpoint_{episode+1}.pt"))
            print(f"  -> Saved checkpoint at episode {episode+1}")

    # Final save
    torch.save({
        "kt_state":   kt_model.state_dict(),
        "eppo_state": agent.state_dict(),
        "episode":    cfg.N_EPISODES,
        "rewards":    episode_rewards,
        "aprs":       episode_aprs,
    }, os.path.join(save_dir, "final.pt"))

    print("\nTraining complete. Saved to", save_dir)
    return kt_model, agent, {
        "rewards": episode_rewards,
        "aprs":    episode_aprs,
        "lengths": episode_lengths,
        "goals":   goal_reached
    }


def train_kt_step(kt_model, optimizer, criterion, history, cfg):
    """
    Single gradient step on simpleKT using this episode's interactions.
    Trains the model to predict the NEXT answer given the interaction prefix.
    """
    if len(history) < 2:
        return 0.0

    device = next(kt_model.parameters()).device

    concept_ids = torch.LongTensor([[h[0] for h in history]]).to(device)
    diff_levels = torch.LongTensor([[h[1] for h in history]]).to(device)
    corrects    = torch.LongTensor([[h[2] for h in history]]).to(device)

    # Truncate
    if concept_ids.shape[1] > cfg.KT_SEQ_LEN:
        concept_ids = concept_ids[:, -cfg.KT_SEQ_LEN:]
        diff_levels = diff_levels[:, -cfg.KT_SEQ_LEN:]
        corrects    = corrects[:, -cfg.KT_SEQ_LEN:]

    kt_model.train()
    mastery_matrix = kt_model(concept_ids, diff_levels, corrects)
    # (1, N_CONCEPTS, DIFF_LEVELS)

    # Teacher-forcing: for each step t, predict correctness of answer t
    # given the interaction prefix 0..t-1 that was fed into the transformer.
    # Accumulate per-step losses into a list then stack — avoids the fragile
    # leaf-tensor pattern (torch.tensor(..., requires_grad=True) + inplace add)
    # which can silently break the gradient graph.
    T = len(history)
    losses = []

    for t in range(1, min(T, cfg.KT_SEQ_LEN)):
        c_idx = history[t][0]
        d_idx = history[t][1]
        label = torch.FloatTensor([history[t][2]]).to(device)
        pred  = mastery_matrix[0, c_idx, d_idx].unsqueeze(0)
        losses.append(criterion(pred, label))

    if losses:
        loss = torch.stack(losses).mean()
        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(kt_model.parameters(), 1.0)
        optimizer.step()
        return loss.item()

    return 0.0


# ─── Evaluation 1: KT Model Quality (AUC) ────────────────────────────────────

def evaluate_kt(kt_model, cfg, n_students=200):
    """
    Evaluates KT prediction quality using AUC and accuracy.

    Method:
      - For each simulated student, generate 20 random interactions
      - Use the first 10 as the history prefix to build the student state
      - Predict correctness for interactions 11-20
      - Compare predictions against actual outcomes

    Metrics:
      AUC      — standard KT benchmark metric. Random = 0.5, good > 0.70
      Accuracy — fraction of predictions correct when thresholded at 0.5
      ECE      — Expected Calibration Error: are the probabilities well-calibrated?
                 ECE near 0 means predicted 0.7 really means ~70% chance correct
    """
    try:
        from sklearn.metrics import roc_auc_score, accuracy_score
    except ImportError:
        print("sklearn not found — run: pip install scikit-learn")
        return {}

    env        = SimulatedStudentEnv(cfg)
    all_labels = []
    all_preds  = []

    kt_model.eval()

    for _ in range(n_students):
        true_mastery = env.sample_student()
        history      = []

        # Generate 20 random interactions (not EPPO — pure random exploration)
        for _ in range(20):
            c = np.random.randint(0, cfg.N_CONCEPTS)
            d = np.random.randint(0, cfg.DIFF_LEVELS)
            correct = env.answer(true_mastery, c, d)
            history.append((c, d, correct))

        # Split: first 10 build state, predict on 11-20
        split  = 10
        prefix = history[:split]
        suffix = history[split:]

        mastery = kt_model.predict_single(prefix)   # (N_CONCEPTS, DIFF_LEVELS)

        for c_idx, diff, actual_correct in suffix:
            all_preds.append(float(mastery[c_idx, diff]))
            all_labels.append(int(actual_correct))

    all_labels = np.array(all_labels)
    all_preds  = np.array(all_preds)

    auc  = roc_auc_score(all_labels, all_preds)
    acc  = accuracy_score(all_labels, (all_preds >= 0.5).astype(int))

    # Expected Calibration Error — split into 10 bins by predicted probability
    ece = _compute_ece(all_labels, all_preds, n_bins=10)

    print("\n" + "=" * 50)
    print("KT Model Evaluation")
    print("=" * 50)
    print(f"  Students evaluated : {n_students}")
    print(f"  Predictions made   : {len(all_labels)}")
    print(f"  True positive rate : {all_labels.mean():.3f}  (fraction actually correct)")
    print()
    print(f"  AUC      : {auc:.4f}   (random=0.50, acceptable>0.65, good>0.70)")
    print(f"  Accuracy : {acc:.4f}   (random≈0.50)")
    print(f"  ECE      : {ece:.4f}   (lower is better — 0 = perfectly calibrated)")
    print()

    # Interpret AUC
    if auc >= 0.75:
        verdict = "GOOD — KT model is tracking student knowledge reliably"
    elif auc >= 0.65:
        verdict = "ACCEPTABLE — KT model is working, more training may help"
    elif auc >= 0.55:
        verdict = "WEAK — KT model is barely above random, needs more training"
    else:
        verdict = "POOR — KT model is not learning, check training setup"
    print(f"  Verdict  : {verdict}")

    return {
        "auc":      auc,
        "accuracy": acc,
        "ece":      ece,
        "labels":   all_labels,
        "preds":    all_preds,
    }


def _compute_ece(labels, preds, n_bins=10):
    """Expected Calibration Error — measures if predicted probabilities are reliable."""
    bins      = np.linspace(0, 1, n_bins + 1)
    ece       = 0.0
    total     = len(labels)

    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask   = (preds >= lo) & (preds < hi)
        if mask.sum() == 0:
            continue
        bin_acc  = labels[mask].mean()
        bin_conf = preds[mask].mean()
        bin_size = mask.sum() / total
        ece     += bin_size * abs(bin_acc - bin_conf)

    return float(ece)


# ─── Evaluation 2: Policy Comparison (EPPO vs Baselines) ─────────────────────

def evaluate_policy(kt_model, agent, cfg, n_students=200):
    """
    Compares EPPO against two baselines on fresh simulated students.

    Baselines:
      Random      — picks concept and difficulty uniformly at random
      Greedy      — always picks the weakest concept at the ideal difficulty
                    (a strong hand-crafted heuristic — EPPO must beat this)

    Metrics per policy:
      Mean final APR    — how much of the material did the student cover?
      Goal reached %    — how often did the session reach APR >= beta?
      Mean steps        — how many interactions to reach the goal (lower = more efficient)?
      Difficulty dist   — what difficulty mix did the policy choose?
      Coverage per diff — mean mastery at each difficulty level at session end
    """
    env     = SimulatedStudentEnv(cfg)
    kt_model.eval()
    agent.eval()

    policies = {
        "eppo":   _run_eppo_policy,
        "random": _run_random_policy,
        "greedy": _run_greedy_policy,
    }

    results = {}

    for policy_name, policy_fn in policies.items():
        aprs         = []
        steps        = []
        goals        = []
        diff_counts  = np.zeros(cfg.DIFF_LEVELS)
        final_mastery_sum = np.zeros((cfg.N_CONCEPTS, cfg.DIFF_LEVELS))

        for _ in range(n_students):
            true_mastery = env.sample_student()
            student      = StudentState(cfg)

            student, diff_counts_ep = policy_fn(
                kt_model, agent, env, student, true_mastery, cfg
            )
            diff_counts += diff_counts_ep

            apr = student.get_apr()
            aprs.append(apr)
            steps.append(len(student.history))
            goals.append(apr >= cfg.BETA)
            final_mastery_sum += student.mastery

        mean_mastery = final_mastery_sum / n_students

        results[policy_name] = {
            "mean_apr":      np.mean(aprs),
            "std_apr":       np.std(aprs),
            "goal_rate":     np.mean(goals) * 100,
            "mean_steps":    np.mean(steps),
            "std_steps":     np.std(steps),
            "diff_dist":     diff_counts / max(diff_counts.sum(), 1),
            "mean_mastery":  mean_mastery,   # (N_CONCEPTS, DIFF_LEVELS)
        }

    _print_policy_comparison(results, cfg, n_students)
    return results


def _run_eppo_policy(kt_model, agent, env, student, true_mastery, cfg):
    """Run one session using the trained EPPO agent."""
    diff_counts = np.zeros(cfg.DIFF_LEVELS)

    for _ in range(cfg.MAX_STEPS):
        student.update_from_kt(kt_model)
        if student.get_apr() >= cfg.BETA:
            break
        with torch.no_grad():
            action, _, _, _ = agent.select_action(
                student.get_state_vector(), student.mastery
            )
        c = action // cfg.DIFF_LEVELS
        d = action  % cfg.DIFF_LEVELS
        diff_counts[d] += 1
        correct = env.answer(true_mastery, c, d)
        student.history.append((c, d, correct))

    return student, diff_counts


def _run_random_policy(kt_model, agent, env, student, true_mastery, cfg):
    """Run one session using uniformly random action selection."""
    diff_counts = np.zeros(cfg.DIFF_LEVELS)

    for _ in range(cfg.MAX_STEPS):
        student.update_from_kt(kt_model)
        if student.get_apr() >= cfg.BETA:
            break
        c = np.random.randint(0, cfg.N_CONCEPTS)
        d = np.random.randint(0, cfg.DIFF_LEVELS)
        diff_counts[d] += 1
        correct = env.answer(true_mastery, c, d)
        student.history.append((c, d, correct))

    return student, diff_counts


def _run_greedy_policy(kt_model, agent, env, student, true_mastery, cfg):
    """
    Greedy heuristic: always pick the weakest concept at the ideal difficulty.
    Ideal difficulty = one step above the student's current competence level.
    This is a strong baseline — EPPO must beat it to demonstrate value.
    """
    diff_counts = np.zeros(cfg.DIFF_LEVELS)

    for _ in range(cfg.MAX_STEPS):
        student.update_from_kt(kt_model)
        if student.get_apr() >= cfg.BETA:
            break

        # Pick weakest concept by easy mastery
        weakest_c = int(np.argmin(student.mastery[:, 0]))

        # Ideal difficulty: one above current competence
        current_d = 0
        for d in range(cfg.DIFF_LEVELS):
            if student.mastery[weakest_c, d] > 0.6:
                current_d = d
        ideal_d = min(current_d + 1, cfg.DIFF_LEVELS - 1)

        diff_counts[ideal_d] += 1
        correct = env.answer(true_mastery, weakest_c, ideal_d)
        student.history.append((weakest_c, ideal_d, correct))

    return student, diff_counts


def _print_policy_comparison(results, cfg, n_students):
    """Print formatted policy comparison table."""
    w = 14   # column width

    print("\n" + "=" * 62)
    print("Policy Comparison")
    print("=" * 62)
    print(f"  Students per policy: {n_students}")
    print(f"  Learning goal (β)  : {cfg.BETA}")
    print()

    header = f"  {'Metric':<24}" + "".join(f"{'EPPO':>{w}} {'Random':>{w}} {'Greedy':>{w}}")
    print(f"  {'Metric':<24} {'EPPO':>{w}} {'Random':>{w}} {'Greedy':>{w}}")
    print("  " + "-" * 60)

    metrics = [
        ("Mean final APR",   "mean_apr",   ".3f"),
        ("Std APR",          "std_apr",    ".3f"),
        ("Goal reached %",   "goal_rate",  ".1f"),
        ("Mean steps",       "mean_steps", ".1f"),
        ("Std steps",        "std_steps",  ".1f"),
    ]

    for label, key, fmt in metrics:
        row = f"  {label:<24}"
        for p in ["eppo", "random", "greedy"]:
            val = results[p][key]
            row += f" {val:>{w}{fmt}}"
        print(row)

    print()
    print(f"  {'Difficulty distribution':}")
    diff_header = f"  {'':24}"
    for p in ["eppo", "random", "greedy"]:
        diff_header += f" {'E/M/H':>{w}}"
    print(diff_header)
    print("  " + "-" * 60)

    row = f"  {'  Easy/Medium/Hard %':<24}"
    for p in ["eppo", "random", "greedy"]:
        d = results[p]["diff_dist"] * 100
        row += f"  {d[0]:.0f}/{d[1]:.0f}/{d[2]:.0f}".rjust(w)
    print(row)

    print()
    # Verdict
    eppo_apr    = results["eppo"]["mean_apr"]
    random_apr  = results["random"]["mean_apr"]
    greedy_apr  = results["greedy"]["mean_apr"]
    eppo_steps  = results["eppo"]["mean_steps"]
    greedy_steps= results["greedy"]["mean_steps"]

    beats_random = eppo_apr > random_apr
    beats_greedy = eppo_apr > greedy_apr or eppo_steps < greedy_steps

    print(f"  EPPO vs Random : {'EPPO wins (+{:.3f} APR)'.format(eppo_apr-random_apr) if beats_random else 'Random wins — EPPO needs more training'}")
    print(f"  EPPO vs Greedy : {'EPPO wins' if beats_greedy else 'Greedy wins — EPPO has not learned a better policy yet'}")

    if not beats_random:
        print()
        print("  NOTE: EPPO not beating random yet. Try:")
        print("    - Increase N_EPISODES to 2000")
        print("    - Increase GAMMA_FIT to 0.25 (stronger fit penalty)")
        print("    - Add pretrain_kt() before main training")


# ─── Evaluation 3: Per-concept Mastery Report ─────────────────────────────────

def evaluate_mastery_report(kt_model, agent, cfg, n_students=100):
    """
    Shows per-concept mastery breakdown at session end.
    Useful for understanding which concepts EPPO is covering well vs neglecting.
    """
    results = evaluate_policy(kt_model, agent, cfg, n_students=n_students)
    eppo_mastery = results["eppo"]["mean_mastery"]   # (N_CONCEPTS, DIFF_LEVELS)

    print("\n" + "=" * 62)
    print("Per-concept Mastery Report (EPPO policy)")
    print("=" * 62)
    print(f"  {'Concept':<28} {'Easy':>6} {'Medium':>8} {'Hard':>6}  {'Coverage'}")
    print("  " + "-" * 62)

    for j, name in enumerate(cfg.CONCEPTS):
        e = eppo_mastery[j, 0]
        m = eppo_mastery[j, 1]
        h = eppo_mastery[j, 2]

        # Coverage bar: blocks proportional to easy mastery
        bar_len = int(e * 10)
        bar     = "█" * bar_len + "░" * (10 - bar_len)

        print(f"  {name:<28} {e:>6.2f} {m:>8.2f} {h:>6.2f}  {bar}")

    print()
    print(f"  Mean easy mastery   : {eppo_mastery[:, 0].mean():.3f}")
    print(f"  Mean medium mastery : {eppo_mastery[:, 1].mean():.3f}")
    print(f"  Mean hard mastery   : {eppo_mastery[:, 2].mean():.3f}")
    print()
    print(f"  Well-covered (easy > 0.7) : {(eppo_mastery[:, 0] > 0.7).sum()}/{cfg.N_CONCEPTS} concepts")
    print(f"  Neglected   (easy < 0.5)  : {(eppo_mastery[:, 0] < 0.5).sum()}/{cfg.N_CONCEPTS} concepts")

    return results


# ─── Quick Demo ───────────────────────────────────────────────────────────────

def run_demo_session(kt_model, agent, cfg):
    """
    Run a single demo session and print what happens step by step.
    Shows exactly what EPPO is deciding at each step.
    """
    env          = SimulatedStudentEnv(cfg)
    true_mastery = env.sample_student()
    student      = StudentState(cfg)

    print("\n" + "=" * 72)
    print("Demo Session — step by step")
    print("=" * 72)
    print(f"  Goal: APR >= {cfg.BETA}")
    print()
    print(f"  {'Step':>4}  {'Concept':<26} {'Diff':<8} {'Mastery':>8} {'Answer':>8} {'APR':>6}")
    print("  " + "-" * 66)

    kt_model.eval()
    agent.eval()

    for step in range(cfg.MAX_STEPS):
        student.update_from_kt(kt_model)
        apr = student.get_apr()

        if apr >= cfg.BETA:
            print(f"\n  Goal reached at step {step}!  Final APR = {apr:.3f}")
            break

        with torch.no_grad():
            action, _, _, _ = agent.select_action(
                student.get_state_vector(), student.mastery
            )

        concept_idx      = action // cfg.DIFF_LEVELS
        diff_level       = action  % cfg.DIFF_LEVELS
        concept          = cfg.CONCEPTS[concept_idx]
        diff_name        = cfg.DIFF_NAMES[diff_level]
        mastery_at_level = student.mastery[concept_idx, diff_level]

        correct = env.answer(true_mastery, concept_idx, diff_level)
        student.history.append((concept_idx, diff_level, correct))

        answer_str = "CORRECT" if correct else "wrong  "
        print(
            f"  {step+1:>4}  {concept:<26} {diff_name:<8} "
            f"{mastery_at_level:>8.2f} {answer_str:>8} {apr:>6.3f}"
        )

    print()
    student.update_from_kt(kt_model)
    print(f"  {'Concept':<28} {'Easy':>6} {'Medium':>8} {'Hard':>6}")
    print("  " + "-" * 52)
    for j, name in enumerate(cfg.CONCEPTS):
        e, m, h = student.mastery[j]
        print(f"  {name:<28} {e:>6.2f} {m:>8.2f} {h:>6.2f}")


# ─── Full Evaluation Suite ────────────────────────────────────────────────────

def run_full_evaluation(kt_model, agent, cfg, n_students=200):
    """
    Runs all three evaluations in sequence and returns all results.
    Call this after training to get a complete picture of system performance.
    """
    print("\n" + "=" * 62)
    print("FULL EVALUATION SUITE")
    print("=" * 62)

    # 1. KT quality
    kt_results = evaluate_kt(kt_model, cfg, n_students=n_students)

    # 2. Policy comparison
    policy_results = evaluate_policy(kt_model, agent, cfg, n_students=n_students)

    # 3. Mastery report — uses already-computed policy results
    eppo_mastery = policy_results["eppo"]["mean_mastery"]
    print("\n" + "=" * 62)
    print("Per-concept Mastery Report (EPPO policy)")
    print("=" * 62)
    print(f"  {'Concept':<28} {'Easy':>6} {'Medium':>8} {'Hard':>6}  Coverage")
    print("  " + "-" * 62)
    for j, name in enumerate(cfg.CONCEPTS):
        e, m, h  = eppo_mastery[j]
        bar      = "█" * int(e * 10) + "░" * (10 - int(e * 10))
        print(f"  {name:<28} {e:>6.2f} {m:>8.2f} {h:>6.2f}  {bar}")

    print(f"\n  Well-covered (easy>0.7): {(eppo_mastery[:,0]>0.7).sum()}/{cfg.N_CONCEPTS}")
    print(f"  Neglected   (easy<0.5): {(eppo_mastery[:,0]<0.5).sum()}/{cfg.N_CONCEPTS}")

    # 4. Demo session
    run_demo_session(kt_model, agent, cfg)

    return {
        "kt":     kt_results,
        "policy": policy_results,
    }


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = Config()

    print("=== Adaptive Learning Module — Phase 1 ===")
    print(f"Concepts : {cfg.CONCEPTS}")
    print(f"Device   : {cfg.DEVICE}")
    print()

    # Train
    kt_model, agent, metrics = train(cfg, save_dir="checkpoints")

    # Full evaluation suite
    results = run_full_evaluation(kt_model, agent, cfg, n_students=200)
