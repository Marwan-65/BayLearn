"""Stability check for a saved EPPO checkpoint.

Usage:
  python evaluate_checkpoint.py --ckpt eppo_best.pt --n 1000 --fast

This script loads a checkpoint into the EPPO agent defined in
`pfa_eppo_poc.py` and runs the deterministic (argmax) policy evaluation
over many simulated students to compute Goal% and other summary metrics.
It is robust to different checkpoint formats and can run a fast mode that
avoids downloading sentence-transformers by using a synthetic similarity
matrix.
"""
import argparse
import json
import os
import sys
import numpy as np
import torch

# Import the environment and utilities from the repo
from pfa_eppo_poc import Config, EPPOAgent, PFATracker, evaluate_policies


def tolerant_load(agent: torch.nn.Module, path: str, device: torch.device):
    ckpt = torch.load(path, map_location=device)
    # If the checkpoint is a torch.nn.Module instance (pickled model), try its state_dict
    try:
        import torch.nn as nn
        if isinstance(ckpt, nn.Module):
            agent.load_state_dict(ckpt.state_dict())
            return True
    except Exception:
        pass
    # If it's a full state_dict for the module
    try:
        agent.load_state_dict(ckpt)
        return True
    except Exception:
        pass

    # Try nested keys common in checkpoints
    candidates = [
        'model_state_dict', 'state_dict', 'actor_state_dict', 'actor',
        'agent_state_dict', 'policy_state_dict'
    ]
    for k in candidates:
        if isinstance(ckpt, dict) and k in ckpt:
            sub = ckpt[k]
            try:
                agent.load_state_dict(sub)
                return True
            except Exception:
                # try loading actor/critic separately
                try:
                    if hasattr(agent, 'actor') and 'actor' in sub:
                        agent.actor.load_state_dict(sub.get('actor'))
                    if hasattr(agent, 'critic') and 'critic' in sub:
                        agent.critic.load_state_dict(sub.get('critic'))
                    return True
                except Exception:
                    continue

    # If checkpoint looks like actor-only state dict, try loading into agent.actor
    if isinstance(ckpt, dict):
        # Detect if keys use a different top-level prefix (e.g., 'scorer.0.weight')
        keys = list(ckpt.keys())
        if keys and isinstance(keys[0], str):
            top = keys[0].split('.')[0]
            # If agent has a matching attribute, try to load into that submodule
            if hasattr(agent, top):
                try:
                    submod = getattr(agent, top)
                    if hasattr(submod, 'load_state_dict'):
                        submod.load_state_dict(ckpt)
                        return True
                except Exception:
                    pass
            # If agent has 'actor' and the checkpoint uses a different prefix, remap keys -> actor.*
            if hasattr(agent, 'actor') and top != 'actor':
                try:
                    new = {('actor.' + '.'.join(k.split('.')[1:]) if k.startswith(top + '.') else k): v for k, v in ckpt.items()}
                    agent.actor.load_state_dict(new)
                    return True
                except Exception:
                    pass
        # Fallback: try loading the dict directly into agent.actor if present
        try:
            if hasattr(agent, 'actor'):
                agent.actor.load_state_dict(ckpt)
                return True
        except Exception:
            pass

    return False


def build_sim_matrix(cfg: Config, fast: bool, seed: int = 42):
    if fast:
        rng = np.random.default_rng(seed)
        emb = rng.normal(size=(cfg.N_CONCEPTS, 64))
        # cosine-sim style
        emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        sim = emb @ emb.T
        return sim
    # full build via PFATracker (may require sentence-transformers)
    tracker = PFATracker(cfg.CONCEPTS, cfg)
    return tracker.sim_matrix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ckpt', type=str, default='eppo_best.pt')
    parser.add_argument('--n', type=int, default=1000, help='Students per policy')
    parser.add_argument('--seed', type=int, default=77)
    parser.add_argument('--fast', action='store_true', help='Skip heavy embedding build')
    parser.add_argument('--out', type=str, default='evaluate_results.json')
    args = parser.parse_args()

    cfg = Config()
    device = cfg.DEVICE

    agent = EPPOAgent(cfg).to(device)

    if not os.path.exists(args.ckpt):
        print(f'Checkpoint not found: {args.ckpt}', file=sys.stderr)
        sys.exit(2)

    ok = tolerant_load(agent, args.ckpt, device)
    if not ok:
        print('Failed to load checkpoint into agent (tried common formats).', file=sys.stderr)
        sys.exit(3)

    sim_matrix = build_sim_matrix(cfg, fast=args.fast, seed=args.seed)

    policies = evaluate_policies(agent, cfg, sim_matrix, n_students=args.n)

    out = {
        'ckpt': os.path.basename(args.ckpt),
        'n_students': args.n,
        'fast_sim_matrix': bool(args.fast),
        'policies': policies,
    }

    with open(args.out, 'w') as f:
        json.dump(out, f, indent=2)

    print(f'Wrote results to {args.out}')


if __name__ == '__main__':
    main()
