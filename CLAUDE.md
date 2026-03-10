# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Setup

This project uses **uv** for dependency management. Always use `uv run` (not `source .venv/bin/activate && python`) and `uv pip` (not bare `pip`) for all operations.

```bash
# Create and sync the venv (installs all deps from pyproject.toml + uv.lock)
uv sync

# Or with dev extras (includes black, isort)
uv sync --extra dev

# Install additional packages (ALWAYS use uv pip, never bare pip)
uv pip install <package>
```

## Running

Entry point is Hydra-based. Solver selection uses Hydra config groups (`solver=name`). **Always use `uv run`.**

```bash
# Default run (random solver, 16 envs, 100 episodes)
uv run python -m ps_bed.run

# Cube stacking solver (env requirements set by configs/solver/stack_cubes.yaml)
uv run python -m ps_bed.run solver=stack_cubes

# N-cube stacking with extra env kwargs (+ prefix required for new keys)
uv run python -m ps_bed.run solver=stack_cubes env.env_id=StackNCube-v1 +env.extra_kwargs.num_cubes=3

# Common overrides
uv run python -m ps_bed.run solver=stack_cubes env.env_id=StackCubeDistractor-v1
uv run python -m ps_bed.run env.record_video=true run.num_episodes=10
uv run python -m ps_bed.run seed=123 logging.use_wandb=true
```

Hydra writes timestamped output dirs under `outputs/`. Videos go to `videos/`.

## Formatting

```bash
uv run black ps_bed/
uv run isort ps_bed/
```

No tests exist in this repo.

## Architecture

**ps_bed** is a robotics research testbed for evaluating solvers on ManiSkill3 cube-stacking tasks.

### Core Flow

`ps_bed/run.py` is the entry point (`@hydra.main`). It dispatches based on `cfg.run.solver`:
- `"random"` → `run_random()` — vectorized env (`ManiSkillVectorEnv`), samples random actions
- Any other value → `run_solver()` — looks up the solver in `SOLVER_REGISTRY`, creates a single env, runs episode loop

Hydra's DictConfig is passed directly to functions (no dataclass reconstruction).

### Solver Registry (pluggable architecture)

Solvers are registered in `ps_bed/solvers/__init__.py` via `SOLVER_REGISTRY` (maps solver names to `"module:ClassName"` strings). Adding a new solver requires:
1. Create `ps_bed/solvers/my_solver.py` inheriting `BaseSolver`, implement `solve()`
2. Add one line to `SOLVER_REGISTRY`
3. Create `configs/solver/my_solver.yaml` with env requirements (`# @package _global_`)
4. Run: `python -m ps_bed.run solver=my_solver env.env_id=MyEnv-v1`

No changes to `run.py`, `env.py`, or `config.py` needed. Env-specific kwargs use `+env.extra_kwargs.key=value`.

### Key Modules

- **`config.py`** — Hydra-compatible dataclasses (`Config`, `EnvConfig`, `LoggingConfig`, `RunConfig`). `EnvConfig.extra_kwargs` passes arbitrary kwargs to `gym.make()`.
- **`env.py`** — Two factory functions:
  - `make_env()` — vectorized env wrapped with `ManiSkillVectorEnv` (for RL policies)
  - `make_single_env()` — raw gym env with `sim_backend="cpu"` (required by motion planner)
- **`skills/motion.py`** — Low-level mplib helpers: `setup_planner()`, `move_to_pose()`, `actuate_gripper()`, `follow_path()`, `sapien_to_mplib_pose()`. `move_to_pose()` tries `plan_screw()` first, then falls back to `plan_pose()` (OMPL RRTConnect) for obstacle avoidance.
- **`skills/primitives.py`** — Reusable `pick()` and `place()` functions with `PickResult`/`PlaceResult` dataclasses.
- **`solvers/base.py`** — `BaseSolver` ABC with `solve()`.
- **`solvers/stack_cubes.py`** — `StackCubesSolver` — unified N-cube stacking (registered as `stack_cubes`).
- **`envs/stack_cube_distractor.py`** — Custom env `StackCubeDistractor-v1` extending `StackCubeEnv` with a blue distractor cube.
- **`logger.py`** — Optional WandB logging wrapper.

### Critical Constraints (mplib / ManiSkill)

- **mplib 0.2.x API**: Uses `mplib.pymp.Pose` objects (not numpy arrays) for `set_base_pose()`, `plan_screw()`, etc.
- **SAPIEN poses are batched**: Even with `num_envs=1`, pose tensors have shape `(1, 3)` / `(1, 4)` — must `.flatten()` before passing to mplib.
- **Motion planner requires**: `num_envs=1`, `sim_backend="cpu"`, `pd_joint_pos` control mode, no `ManiSkillVectorEnv` wrapper.
- **Video recording with planner**: Must use `save_on_reset=False` on `RecordEpisode` and call `env.flush_video()` manually.
- **numpy < 2.0** required by mplib 0.2.1.
