# External Integrations

**Analysis Date:** 2026-02-13

## APIs & External Services

**Experiment Tracking:**
- Weights & Biases (WandB) - Optional cloud experiment logging and visualization
  - SDK/Client: `wandb` package
  - Auth: Not required if `logging.use_wandb=false` (default); when enabled, uses WandB CLI authentication
  - Integration point: `ps_bed/logger.py` lines 13-21
  - Configuration: `ps_bed/config.py` LoggingConfig with `project="ps_bed"` and `group="stackcube"`

**No Direct External APIs:**
- All robot simulation is self-contained via ManiSkill/SAPIEN
- No HTTP requests or remote service calls
- No third-party cloud services required for basic execution

## Data Storage

**Databases:**
- None detected - Project is stateless simulation; no persistent data store

**File Storage:**
- Local filesystem only
  - Videos: `videos/` directory (written by `RecordEpisode` wrapper in `ps_bed/env.py` lines 26-32, 60-68)
  - Experiment outputs: `outputs/` directory (managed by Hydra)
  - No cloud storage integration

**Caching:**
- None detected

## Authentication & Identity

**Auth Provider:**
- Optional WandB authentication only
  - Implementation: Lazy import in `ps_bed/logger.py` lines 11, 25, 31
  - Uses system WandB CLI credentials (no API key parameter in code)
  - Disabled by default (`logging.use_wandb=false` in `configs/default.yaml`)

## Monitoring & Observability

**Error Tracking:**
- None detected - No error tracking service integration

**Logs:**
- Console/stdout only
  - Print statements in `ps_bed/run.py` lines 81, 148 for episode progress
  - Optional WandB logging via `logger.log_episode()` and `logger.log_summary()` in `ps_bed/logger.py`
  - Hydra logs written to timestamped `outputs/` directories

## CI/CD & Deployment

**Hosting:**
- Research/Local - No deployment infrastructure; runs on local machines or research clusters

**CI Pipeline:**
- None detected

**Environment Configuration:**
- Hydra config overrides via CLI: `python -m ps_bed.run env.env_id=StackCubeDistractor-v1`
- No environment variables used for configuration; all config in YAML + CLI overrides
- No `.env` files required

## Robot & Simulation Integration Points

**ManiSkill Environment Factory:**
- Location: `ps_bed/env.py`
- Vectorized env: `make_env()` creates `ManiSkillVectorEnv` wrapped environments for parallel RL policy evaluation
- Single env: `make_single_env()` creates raw Gymnasium env for motion planner (requires `sim_backend="cpu"`, `num_envs=1`, `pd_joint_pos` control mode)
- Task environments supported: `StackCube-v1` (default), `StackCubeDistractor-v1` (custom)

**Custom Environment Registration:**
- Location: `ps_bed/envs/stack_cube_distractor.py` lines 13, 26-84
- Registered as `StackCubeDistractor-v1` via `@register_env()` decorator
- Extends ManiSkill's `StackCubeEnv` with blue distractor cube
- Imported implicitly by `ps_bed/env.py` line 6 (registers env on module load)

**Motion Planning Integration:**
- mplib motion planner: `ps_bed/skills/pick_place.py`
- Accesses raw SAPIEN robot state: `env.unwrapped.agent` (lines 30, 71, 85)
- Requires robot URDF + SRDF: Built from `agent.urdf_path` (line 37-38)
- SAPIEN Pose conversions: `_sapien_to_mplib_pose()` helper handles batched tensor flattening (lines 12-16)
- Link/joint names extracted from SAPIEN robot object (lines 33-34)

## Control Modes & Constraints

**Vectorized Policy Evaluation (random or RL):**
- Control mode: `pd_ee_delta_pose` (default, configurable)
- Observation mode: `state` (default, configurable)
- Reward mode: `normalized_dense` (default, configurable)
- Multi-env execution via `ManiSkillVectorEnv` for parallel simulation
- Environment: `StackCube-v1` by default

**Motion Planner (Pick-Place):**
- Control mode: FORCED to `pd_joint_pos` or `pd_joint_pos_vel` in `ps_bed/run.py` lines 97-98
- Observation mode: `state` (inherited from config)
- Single environment: `num_envs=1` (forced in line 98)
- Backend: `sim_backend="cpu"` (required for planner, set in `ps_bed/env.py` line 56)
- Video recording requires `save_on_reset=False` and manual `flush_video()` calls (line 65, 133)

---

*Integration audit: 2026-02-13*
