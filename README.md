# taskbench

A robotics research testbed for evaluating solvers on ManiSkill3 manipulation tasks. Provides composable skill primitives (pick, place, push), HDF5 demonstration recording with skill program traces, and a pluggable solver system.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/dhruvmetha/ms-taskbench.git
cd ms-taskbench
uv sync
```

## Usage

All commands use `uv run` — no manual venv activation needed.

```bash
# Random baseline (16 parallel envs, 100 episodes)
uv run python -m taskbench.run

# Stack 3 cubes using motion planner
uv run python -m taskbench.run solver=stack_cubes

# Stack 5 cubes with video recording
uv run python -m taskbench.run solver=stack_cubes env.num_cubes=5 env.record_video=true

# Collect 10 demos
uv run python -m taskbench.run solver=stack_cubes run.num_episodes=10

# Replay a recorded demo
uv run python -m taskbench.run solver=replay run.solver_kwargs.demo_path=data/success/episode_seed45.hdf5
```

Demos are saved to `data/success/` and `data/failure/`. Videos go to `videos/`.

## Common overrides

```bash
env.num_cubes=N          # number of cubes (default: 3)
env.record_video=true    # save videos
run.num_episodes=N       # number of episodes
seed=123                 # random seed
logging.use_wandb=true   # enable WandB logging
```

## Project structure

```
configs/              # Hydra YAML configs (single source of truth)
  default.yaml        # base config
  solver/             # per-solver overrides
taskbench/
  run.py              # entry point (@hydra.main)
  solver.py           # BaseSolver, @register_solver, auto-discovery
  recorder.py         # HDF5 state + program recorder
  envs/               # ManiSkill3 environments
  skills/             # composable primitives (pick, place, push)
  solvers/            # solver implementations
```

## Adding a new solver

1. Create `taskbench/solvers/my_solver.py` with `@register_solver("my_solver")`
2. Create `configs/solver/my_solver.yaml` with env requirements
3. Run: `uv run python -m taskbench.run solver=my_solver`

No edits to core files needed — solvers are auto-discovered.

## Dev

```bash
uv sync --extra dev
uv run black taskbench/
uv run isort taskbench/
```
