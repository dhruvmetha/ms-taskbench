# Codebase Structure

**Analysis Date:** 2026-02-13

## Directory Layout

```
program_synthesis_bed/
├── ps_bed/                    # Main package
│   ├── __init__.py           # Package init (empty)
│   ├── run.py                # Hydra entry point, policy dispatch
│   ├── config.py             # Configuration dataclasses
│   ├── env.py                # Environment factories
│   ├── logger.py             # WandB logging wrapper
│   ├── envs/                 # Custom environments
│   │   ├── __init__.py       # Imports custom env for registration
│   │   └── stack_cube_distractor.py  # StackCubeDistractor-v1 env
│   └── skills/               # Robot skill implementations
│       ├── __init__.py       # Empty
│       └── pick_place.py     # Motion-planned grasp/place skill
├── configs/                  # Hydra configuration files
│   └── default.yaml         # Default experiment config
├── scripts/                  # Convenience scripts
│   └── run.sh               # Shell wrapper with example overrides
├── outputs/                 # Hydra output directory (generated)
│   └── [timestamp]/         # Per-run output with .hydra/ metadata
├── videos/                  # Video recordings (generated)
├── .planning/               # GSD planning documentation
│   └── codebase/           # Codebase analysis documents
├── pyproject.toml           # Package metadata, dependencies
├── CLAUDE.md               # Development guide
└── README (inferred)        # Project documentation
```

## Directory Purposes

**ps_bed/:**
- Purpose: Main package containing all source code
- Contains: Policy runners, config, environment setup, skills, custom environments
- Key files: `run.py` (entry), `config.py` (config schema), `env.py` (env factories)

**ps_bed/envs/:**
- Purpose: Custom ManiSkill environment extensions
- Contains: Task variants that inherit from ManiSkill base environments
- Key files: `stack_cube_distractor.py` (task with visual distractor)

**ps_bed/skills/:**
- Purpose: Reusable robot behaviors implemented as skill solvers
- Contains: Motion planning, trajectory execution, task composition
- Key files: `pick_place.py` (grasp-lift-place motion planner)

**configs/:**
- Purpose: Hydra configuration files
- Contains: YAML default config and overrides
- Key files: `default.yaml` (experiment defaults)

**scripts/:**
- Purpose: Convenience wrappers for common execution patterns
- Contains: Shell scripts with documented usage examples
- Key files: `run.sh` (default runner with example overrides)

**outputs/:**
- Purpose: Generated run outputs managed by Hydra
- Contains: Timestamped subdirectories, each with `.hydra/` metadata directory
- Generated: Yes
- Committed: No (should be in .gitignore)

**videos/:**
- Purpose: Recorded episode videos
- Contains: MP4 files when `env.record_video=true`
- Generated: Yes
- Committed: No

**.planning/codebase/:**
- Purpose: GSD codebase analysis documentation
- Contains: ARCHITECTURE.md, STRUCTURE.md, and other analysis docs
- Generated: Yes (by GSD mapper)
- Committed: Yes (for reference)

## Key File Locations

**Entry Points:**
- `ps_bed/run.py`: Main Hydra entry point with `@hydra.main` decorator and `main()` function
- `scripts/run.sh`: Shell wrapper invoking `python -m ps_bed.run`

**Configuration:**
- `ps_bed/config.py`: Dataclass definitions (EnvConfig, LoggingConfig, RunConfig, Config)
- `configs/default.yaml`: Default parameter values for all config sections

**Environment Setup:**
- `ps_bed/env.py`: `make_env()` for vectorized runs, `make_single_env()` for motion planning

**Policy Logic:**
- `ps_bed/run.py`: `run_random()` for random policy, `run_pick_place()` for motion planning
- `ps_bed/skills/pick_place.py`: PickPlaceSkill implementation

**Utilities:**
- `ps_bed/logger.py`: Logger class wrapping WandB
- `ps_bed/skills/pick_place.py`: `_sapien_to_mplib_pose()` conversion helper

**Custom Environments:**
- `ps_bed/envs/stack_cube_distractor.py`: StackCubeDistractor-v1 with blue distractor cube
- `ps_bed/envs/__init__.py`: Imports custom env to trigger registration

## Naming Conventions

**Files:**
- `snake_case.py` for modules (e.g., `pick_place.py`, `stack_cube_distractor.py`)
- `config.yaml` for Hydra YAML files
- `run.py` for entry points

**Directories:**
- `snake_case/` for packages (e.g., `ps_bed/`, `envs/`, `skills/`)
- All lowercase

**Classes:**
- `PascalCase` for classes (e.g., `PickPlaceSkill`, `StackCubeDistractorEnv`, `Logger`, `Config`)

**Functions:**
- `snake_case()` for functions (e.g., `run_random()`, `make_env()`, `seed_everything()`)
- Helper functions prefixed with `_` when private (e.g., `_setup_planner()`, `_sapien_to_mplib_pose()`)

**Constants:**
- `UPPER_CASE` for class constants (e.g., `FINGER_LENGTH`, `GRIPPER_OPEN`, `MOVE_GROUP`)

**Config Fields:**
- `snake_case` for config keys (e.g., `env_id`, `control_mode`, `record_video`)

## Where to Add New Code

**New Policy Runner:**
1. Add function `run_policy_name(config: Config, logger: Logger)` in `ps_bed/run.py`
2. Import any required skills from `ps_bed/skills/`
3. Maintain consistent return signature: `(all_returns, all_lengths, all_successes)`
4. Add elif clause in `main()` to dispatch when `config.run.policy == "policy_name"`
5. Add corresponding config option documentation in `CLAUDE.md`

**New Skill:**
1. Create file `ps_bed/skills/skill_name.py`
2. Implement class `SkillNameSkill` with `solve(env, seed=None)` entry point
3. Return final step tuple: `(obs, reward, terminated, truncated, info)`
4. Import in policy runner that will use it

**New Custom Environment:**
1. Create file `ps_bed/envs/task_name.py`
2. Subclass appropriate ManiSkill base env (e.g., `StackCubeEnv`)
3. Use `@register_env()` decorator to register with Gymnasium
4. Import in `ps_bed/envs/__init__.py` to trigger registration
5. Reference by registered name in config: `env.env_id="TaskName-v1"`

**New Configuration Option:**
1. Add field to appropriate dataclass in `ps_bed/config.py` with type and default
2. Mirror changes in `configs/default.yaml`
3. Update `CLAUDE.md` with usage examples
4. Ensure OmegaConf type checking by using proper type hints

**Utilities and Helpers:**
- Shared utility functions: `ps_bed/utils/` (create if needed)
- Pose conversions: `ps_bed/skills/pick_place.py` or new `ps_bed/utils/poses.py`
- Grasp computations: Defer to ManiSkill utilities or create `ps_bed/skills/grasping.py`

**Tests:**
- No tests currently in repository
- If adding tests, create `tests/` directory parallel to `ps_bed/`
- Name files as `test_*.py` or `*_test.py`
- Import test utilities if needed

## Special Directories

**outputs/:**
- Purpose: Hydra-generated run metadata and logs
- Contents: Timestamped subdirectories (YYYY-MM-DD/HH-MM-SS format) containing `.hydra/` with config snapshots
- Generated: Yes (by Hydra during each run)
- Committed: No

**videos/:**
- Purpose: Episode video recordings from simulation
- Contents: MP4 video files named per ManiSkill's RecordEpisode wrapper conventions
- Generated: Yes (when `env.record_video=true`)
- Committed: No

**.planning/codebase/:**
- Purpose: GSD mapper analysis documents
- Contents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md (as generated)
- Generated: Yes (by GSD mapper agent)
- Committed: Yes

**ps_bed.egg-info/:**
- Purpose: Package installation metadata (build artifact)
- Generated: Yes (by pip install -e .)
- Committed: No

## File Organization Principles

**By Responsibility:**
- Entry/dispatch logic: `run.py`
- Configuration schema: `config.py`
- Environment setup: `env.py`
- Logging: `logger.py`
- Task implementation: `envs/` and `skills/`

**By Execution Mode:**
- Vectorized random: handled by `run_random()` with `make_env()` and ManiSkillVectorEnv
- Single-env planning: handled by `run_pick_place()` with `make_single_env()` and motion planning

**By Dependency Scope:**
- Configuration (no external deps): `config.py`
- Env factories (ManiSkill, Gymnasium): `env.py`
- Policies (Environment, Logger): `run.py`
- Skills (mplib, SAPIEN): `skills/`
- Customs envs (ManiSkill): `envs/`
- Logging (WandB, optional): `logger.py`

---

*Structure analysis: 2026-02-13*
