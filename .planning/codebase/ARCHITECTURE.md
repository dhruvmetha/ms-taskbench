# Architecture

**Analysis Date:** 2026-02-13

## Pattern Overview

**Overall:** Hydra-based robotics research testbed with dual-dispatch policy execution

**Key Characteristics:**
- Configuration-driven entry point using Hydra + OmegaConf
- Two distinct execution paths: vectorized random policy vs. motion-planned skill
- Separation between environment setup and policy logic
- Direct integration with ManiSkill3 simulation and mplib motion planning
- Optional WandB logging for experiment tracking

## Layers

**Configuration Layer:**
- Purpose: Define and manage all experiment parameters
- Location: `ps_bed/config.py`, `configs/default.yaml`
- Contains: Dataclass definitions for EnvConfig, LoggingConfig, RunConfig, and the unified Config
- Depends on: Hydra ConfigStore, OmegaConf
- Used by: Main entry point to instantiate runtime config objects

**Environment Abstraction Layer:**
- Purpose: Unified environment creation interface for different execution modes
- Location: `ps_bed/env.py`
- Contains: Two factory functions (`make_env()` and `make_single_env()`)
- Depends on: ManiSkill3, Gymnasium, ManiSkillVectorEnv, RecordEpisode
- Used by: Policy runners (random and pick-place) to initialize environments

**Policy Execution Layer:**
- Purpose: Define two distinct execution strategies
- Location: `ps_bed/run.py` (functions `run_random()` and `run_pick_place()`)
- Contains: Episode loops, action sampling, reward accumulation, metric collection
- Depends on: Environment factory functions, Logger, Skill implementations
- Used by: Main Hydra dispatcher

**Skill Implementation Layer:**
- Purpose: Encode robot behaviors as reusable motion-planned tasks
- Location: `ps_bed/skills/pick_place.py`
- Contains: PickPlaceSkill class with grasp planning, trajectory execution, and pose manipulation
- Depends on: mplib, SAPIEN physics engine, ManiSkill utilities for OBB and grasp computation
- Used by: `run_pick_place()` policy runner

**Custom Environment Layer:**
- Purpose: Extend ManiSkill base environments with custom task variants
- Location: `ps_bed/envs/stack_cube_distractor.py`
- Contains: StackCubeDistractorEnv with visual distractor cube
- Depends on: ManiSkill3 StackCubeEnv, SAPIEN, randomization utilities
- Used by: Gymnasium env registry; instantiated via `gym.make()`

**Logging Layer:**
- Purpose: Optional metrics collection and reporting
- Location: `ps_bed/logger.py`
- Contains: Logger wrapper around WandB
- Depends on: WandB (lazy import), Config
- Used by: Both policy runners and main dispatcher

## Data Flow

**Initialization Flow:**

1. User invokes `python -m ps_bed.run [key=value ...]`
2. Hydra decorator (`@hydra.main`) loads config from `configs/default.yaml` with CLI overrides
3. `main()` function converts OmegaConf dict to Config dataclass objects
4. `seed_everything()` initializes random seeds across numpy, torch, and Python
5. Logger instantiated (WandB init if enabled)

**Random Policy Flow:**

1. `make_env()` instantiated from EnvConfig
   - Creates ManiSkill env via `gym.make()` with specified num_envs (default 16)
   - Wraps with RecordEpisode if video recording enabled
   - Wraps with ManiSkillVectorEnv for vectorized execution
2. `run_random()` enters episode loop:
   - Maintains per-env episode returns, lengths, success flags
   - Each step: sample random action → execute → accumulate rewards
   - Track termination/truncation per environment
   - When environment episode completes: log metrics, reset per-env accumulators
   - Continue until total episodes_done reaches target
3. Summary computed: mean/std returns, mean length, success rate
4. Final metrics logged and WandB run finished

**Pick-Place Policy Flow:**

1. EnvConfig overridden: `control_mode="pd_joint_pos"`, `num_envs=1`, `sim_backend="cpu"`
2. `make_single_env()` instantiated with overrides
   - Creates raw gym env (NOT wrapped with ManiSkillVectorEnv)
   - Wraps with RecordEpisode if video enabled (with `save_on_reset=False`)
3. PickPlaceSkill instantiated (lazy import to avoid dependencies if not used)
4. `run_pick_place()` enters episode loop:
   - For each episode:
     - Optionally set `force_close_distractor` flag (alternates per episode)
     - Call `skill.solve(env, seed)` which:
       - Resets environment
       - Builds mplib.Planner from robot URDF
       - Computes grasp pose via OBB analysis and collision checks
       - Plans screw motions (reach → grasp → lift → align → place)
       - Executes planned path via joint position actions
       - Returns final step tuple (obs, reward, terminated, truncated, info)
     - Extract success from info dict
     - Manually flush video if recording enabled
     - Log success metric
5. Summary computed and reported

**State Management:**

- **Per-Step State:** Observation from environment step
- **Per-Episode State (Random Policy):** Accumulated return, length, success flag (vectorized per env)
- **Per-Episode State (Pick-Place Policy):** Final observation and success flag
- **Global State:** Logger instance, RNG seeds, Config object

## Key Abstractions

**Config Abstraction:**
- Purpose: Decouple parameter specification from code logic
- Examples: `ps_bed/config.py` (EnvConfig, RunConfig, LoggingConfig)
- Pattern: Frozen dataclasses with Hydra integration; resolved via OmegaConf

**Environment Factory Pattern:**
- Purpose: Hide environment setup complexity, switch between vectorized and single-env setups
- Examples: `make_env()` vs `make_single_env()` in `ps_bed/env.py`
- Pattern: Factory functions that compose wrappers based on config; both return gym.Env

**Policy Runner Pattern:**
- Purpose: Encapsulate distinct execution strategies as standalone functions
- Examples: `run_random()` and `run_pick_place()` in `ps_bed/run.py`
- Pattern: Accept Config + Logger, manage own episode loop, return consistent metrics

**Skill Abstraction:**
- Purpose: Encapsulate robot behaviors as callable solvers
- Examples: `PickPlaceSkill.solve()` in `ps_bed/skills/pick_place.py`
- Pattern: Stateless class with internal helper methods; main entry point is `solve(env, seed)`

**Pose Conversion Utility:**
- Purpose: Bridge between SAPIEN batched poses and mplib flat pose representation
- Examples: `_sapien_to_mplib_pose()` in `ps_bed/skills/pick_place.py`
- Pattern: Explicit conversion function that flattens and extracts position/quaternion

## Entry Points

**Command-Line Entry:**
- Location: `ps_bed/run.py` (Hydra `@hydra.main` on `main()` function)
- Triggers: `python -m ps_bed.run` or invoked via shell script
- Responsibilities: Parse CLI args via Hydra, instantiate config objects, seed RNG, dispatch to policy runner, collect and report summary

**Python Module Entry:**
- Location: Package structure allows `import ps_bed.config`, `from ps_bed.env import make_env`, etc.
- Triggers: Imported by external code
- Responsibilities: Provide reusable config definitions and environment factories

## Error Handling

**Strategy:** Defensive checks with warnings and retries in critical paths

**Patterns:**

- **Config Validation:** OmegaConf enforces type checking on dataclass fields
- **Motion Planning Retry:** `plan_screw()` retried once if first attempt fails (line 92-97 in pick_place.py); graceful degradation with -1 return
- **Grasp Pose Search:** Loop through candidate orientations, print warning if none valid (line 149)
- **Distractor Flag Check:** Graceful fallback if env doesn't support `force_close_distractor` flag (line 111)
- **Tensor to Numpy Conversion:** Explicit type conversion with `.cpu().numpy()` where needed; guards against torch.Tensor in metrics
- **Control Mode Assertion:** Planner asserts supported control modes at runtime (line 112-115)

## Cross-Cutting Concerns

**Logging:**
- Centralized via Logger wrapper class (`ps_bed/logger.py`)
- Optional WandB backend controlled by config flag
- Episode metrics logged per step, summary metrics at end
- Console output for progress tracking

**Validation:**
- Config dataclass fields are type-checked by OmegaConf
- Control mode validated in PickPlaceSkill.solve()
- Status checks on motion planning results

**Seeding:**
- Deterministic runs via `seed_everything()` function (line 13-18 in run.py)
- Seeds Python random, numpy, torch (CPU and CUDA if available)
- Per-episode seed offset in pick-place runner (config.seed + ep)

**Video Recording:**
- Conditional wrapping with RecordEpisode in both environment factories
- Different behavior per policy: auto-reset with ManiSkillVectorEnv vs. manual flush for single env
- Output directory `videos/` for all recorded episodes

---

*Architecture analysis: 2026-02-13*
