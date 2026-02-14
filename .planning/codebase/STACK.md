# Technology Stack

**Analysis Date:** 2026-02-13

## Languages

**Primary:**
- Python 3.11+ - All application logic, robot simulation, motion planning, and configuration

## Runtime

**Environment:**
- Conda (conda environment at `/common/users/dm1487/envs/maniskill`)

**Package Manager:**
- pip
- Lockfile: Not detected (using pyproject.toml with version specifiers)

## Frameworks

**Core Simulation:**
- ManiSkill 3.0.0b22 - Robot manipulation simulator with SAPIEN physics engine, task environments, and vector environment wrapper

**Motion Planning:**
- mplib 0.2.1 - Motion planning library using manipulator path planning algorithms (replaces broken mplib 0.1.1)

**Configuration:**
- Hydra 1.3+ - Configuration management with YAML files and command-line overrides
- OmegaConf 2.3+ - Structured configs and object conversion

**Experiment Tracking:**
- Weights & Biases (wandb) - Optional experiment logging and metric tracking (enabled via `logging.use_wandb` config)

**RL Framework:**
- Gymnasium - Standardized gym interface for environments (ManiSkill wraps Gymnasium envs)

## Key Dependencies

**Critical:**
- numpy <2.0 (pinned by mplib 0.2.1) - Required for array operations; newer versions incompatible with mplib
- torch - Deep learning framework, used by ManiSkill for tensor operations and CUDA support
- sapien - Physics simulation library providing poses, actors, and scene management
- transforms3d - Euler angle to quaternion conversions for pose representations

**Infrastructure:**
- setuptools >=68.0 - Build system for packaging
- wheel - Wheel format packaging

## Configuration

**Environment:**
- Configuration via Hydra-compatible dataclasses in `ps_bed/config.py`
- YAML config file at `configs/default.yaml` with overridable sections for env, logging, and run settings
- Command-line overrides: `python -m ps_bed.run key=value nested.key=value`

**Build:**
- `pyproject.toml` - Project metadata, dependencies, and setuptools configuration
- Dev dependencies: `black` (formatting), `isort` (import sorting)

## Platform Requirements

**Development:**
- Python 3.11+
- Conda environment with access to ManiSkill packages
- CUDA-capable GPU recommended (CPU fallback available with `sim_backend="cpu"`)
- Linux OS (no Windows/macOS testing in current codebase)

**Production:**
- Deployment target: Research workstation or cluster with access to ManiSkill/SAPIEN GPU simulation
- Video output written to `videos/` directory
- Hydra writes timestamped experiment outputs to `outputs/` directory

## Critical Version Constraints

**numpy <2.0:**
- mplib 0.2.1 requires numpy <2.0; attempting numpy 2.0+ will cause compatibility issues
- Pinned at 1.26.4 in production environment

**mplib 0.2.1 (not 0.1.1):**
- mplib 0.1.1 (pinned by older ManiSkill) segfaults on planner creation
- Upgraded to 0.2.1 which requires API changes:
  - `set_base_pose()` takes `mplib.pymp.Pose`, not numpy array
  - `plan_screw()` goal is `mplib.pymp.Pose`, not numpy array
  - `plan_qpos_to_pose()` renamed to `plan_pose()`
  - `use_point_cloud` param removed from planning methods

---

*Stack analysis: 2026-02-13*
