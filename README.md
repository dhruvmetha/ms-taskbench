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

## Tasks

### StackNCube

Stack N cubes into a tower. `cube_0` (green) is always the base — the solver picks the remaining cubes in random order and stacks them on top.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `env.num_cubes` | 3 | Number of cubes (2-6) |
| `env.reward_mode` | sparse | `sparse` or `normalized_dense` |

**Solver:** `stack_cubes` — uses sequential pick-place with screw-based motion planning. Automatically records demos to `data/success/` and `data/failure/` in HDF5 format with full state trajectories and skill program traces.

```bash
# Stack 3 cubes (default)
uv run python -m taskbench.run solver=stack_cubes

# Stack 5 cubes, 50 episodes, with video
uv run python -m taskbench.run solver=stack_cubes env.num_cubes=5 run.num_episodes=50 env.record_video=true
```

**Replay:** Re-execute a recorded demo's skill program on a fresh env with the same seed:

```bash
uv run python -m taskbench.run solver=replay run.solver_kwargs.demo_path=data/success/episode_seed45.hdf5
```

## Usage

All commands use `uv run` — no manual venv activation needed.

```bash
# Random baseline (16 parallel envs, 100 episodes)
uv run python -m taskbench.run

# Collect 10 demos with the stack_cubes solver
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
