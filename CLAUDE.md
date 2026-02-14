# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Setup

```bash
# Activate the project environment
conda activate /common/users/dm1487/envs/maniskill

# Install package in dev mode
pip install -e .
pip install -e ".[dev]"   # includes black, isort
```

## Running

Entry point is Hydra-based. All config overrides use dotted key=value syntax.

```bash
# Default run (random policy, 16 envs, 100 episodes)
python -m ps_bed.run

# Pick-place motion planner (forces num_envs=1, pd_joint_pos internally)
python -m ps_bed.run run.policy=pick_place

# Common overrides
python -m ps_bed.run env.env_id=StackCubeDistractor-v1 run.policy=pick_place
python -m ps_bed.run env.record_video=true run.num_episodes=10
python -m ps_bed.run seed=123 logging.use_wandb=true
```

Hydra writes timestamped output dirs under `outputs/`. Videos go to `videos/`.

## Formatting

```bash
black ps_bed/
isort ps_bed/
```

No tests exist in this repo.

## Architecture

**ps_bed** is a robotics research testbed for evaluating policies on ManiSkill3 cube-stacking tasks.

### Core Flow

`ps_bed/run.py` is the entry point (`@hydra.main`). It dispatches to one of two policy runners:
- `run_random()` — vectorized env (`ManiSkillVectorEnv`), samples random actions
- `run_pick_place()` — single raw gym env, uses `PickPlaceSkill` motion planner

### Key Modules

- **`config.py`** — Hydra-compatible dataclasses (`Config`, `EnvConfig`, `LoggingConfig`, `RunConfig`). Mirrors `configs/default.yaml`.
- **`env.py`** — Two factory functions:
  - `make_env()` — vectorized env wrapped with `ManiSkillVectorEnv` (for RL policies)
  - `make_single_env()` — raw gym env with `sim_backend="cpu"` (required by motion planner)
- **`skills/pick_place.py`** — `PickPlaceSkill` class that uses mplib 0.2.x to plan and execute grasp-lift-stack sequences. Builds an `mplib.Planner` from the robot URDF each episode.
- **`envs/stack_cube_distractor.py`** — Custom env `StackCubeDistractor-v1` extending `StackCubeEnv` with a blue distractor cube.
- **`logger.py`** — Optional WandB logging wrapper.

### Critical Constraints (mplib / ManiSkill)

- **mplib 0.2.x API**: Uses `mplib.pymp.Pose` objects (not numpy arrays) for `set_base_pose()`, `plan_screw()`, etc.
- **SAPIEN poses are batched**: Even with `num_envs=1`, pose tensors have shape `(1, 3)` / `(1, 4)` — must `.flatten()` before passing to mplib.
- **Motion planner requires**: `num_envs=1`, `sim_backend="cpu"`, `pd_joint_pos` control mode, no `ManiSkillVectorEnv` wrapper.
- **Video recording with planner**: Must use `save_on_reset=False` on `RecordEpisode` and call `env.flush_video()` manually.
- **numpy < 2.0** required by mplib 0.2.1.
