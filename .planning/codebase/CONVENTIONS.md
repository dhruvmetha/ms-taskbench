# Coding Conventions

**Analysis Date:** 2025-02-13

## Naming Patterns

**Files:**
- Module files use lowercase with underscores: `pick_place.py`, `stack_cube_distractor.py`
- Package directories use lowercase: `ps_bed/`, `skills/`, `envs/`
- Entry point: `run.py` (main module)
- Configuration: `config.py`

**Functions:**
- Public functions use snake_case: `seed_everything()`, `run_random()`, `run_pick_place()`, `make_env()`, `make_single_env()`
- Private/internal functions prefix with single underscore: `_setup_planner()`, `_follow_path()`, `_actuate_gripper()`, `_move_to_pose_with_screw()`, `_sapien_to_mplib_pose()`
- Method prefix indicates scope: public methods like `solve()`, `log_episode()`, private methods like `_setup_planner()`, `_initialize_episode()`

**Variables:**
- Local variables use snake_case: `ep_returns`, `done_indices`, `current_qpos`, `gripper_state`
- Constants use UPPERCASE: `FINGER_LENGTH`, `GRIPPER_OPEN`, `GRIPPER_CLOSED`, `MOVE_GROUP`
- Boolean variables are prefixed with descriptive names: `has_distractor_flag`, `recording`, `ep_success_once`
- Loop indices use single letters or descriptive names: `i`, `idx`, `ep`

**Types:**
- Dataclass configs: `Config`, `EnvConfig`, `LoggingConfig`, `RunConfig`
- Class names use PascalCase: `PickPlaceSkill`, `Logger`, `StackCubeDistractorEnv`

## Code Style

**Formatting:**
- Tool: `black`
- Tool: `isort`
- Run with: `black ps_bed/` and `isort ps_bed/`
- Line length: black defaults (typically 88 characters)

**Linting:**
- No explicit linter config file found
- Code follows PEP 8 conventions implicitly

## Import Organization

**Order:**
1. Standard library imports: `random`, `dataclasses`, `hydra`
2. Third-party imports: `numpy`, `torch`, `sapien`, `omegaconf`, `gymnasium`, `transforms3d`, `mplib`
3. Relative local imports: `from ps_bed.config import Config`, `from ps_bed.env import make_env`

**Path Aliases:**
- Uses absolute imports: `from ps_bed.config import Config` (not relative)
- Registers modules with decorators: `@register_env("StackCubeDistractor-v1", max_episode_steps=50)` in `ps_bed/envs/stack_cube_distractor.py`
- Special noqa comments for side-effect imports: `import ps_bed.envs  # noqa: F401 — register custom envs`

## Error Handling

**Patterns:**
- Explicit ValueError with descriptive message: `raise ValueError(f"Unknown policy: {policy!r}. Choose 'random' or 'pick_place'.")`
- Assertions for preconditions: `assert env.unwrapped.control_mode in ["pd_joint_pos", "pd_joint_pos_vel"], f"Unsupported control mode: {env.unwrapped.control_mode}"`
- Return sentinel values for soft failures: `return -1` when planning fails in `_move_to_pose_with_screw()`
- Check status strings from planners: `if result["status"] != "Success"` with retry logic
- Print warnings for recoverable issues: `print(f"Screw plan failed: {result['status']}")` and `print("Warning: failed to find a valid grasp pose")`

## Logging

**Framework:** `print()` for standard console output

**Patterns:**
- Episode progress: `print(f"[Episode {episodes_done}/{target_episodes}]  return={ep_ret:.2f}  len={ep_len}  success={ep_succ}")`
- Summary output: `print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")`
- Status messages: `print(f"[Episode {ep}/{target_episodes}]{close_tag}  success={success}  cumulative_rate={rate:.2f}")`
- Optional WandB logging via `Logger` class: `logger.log_episode(metrics, step=step)`

## Comments

**When to Comment:**
- Module-level docstrings for files: `"""StackCube with an extra blue distractor cube on the table."""`
- Implementation notes for complex logic: `# Alternate close/far placement for distractor envs`
- Inline comments for non-obvious indices: `qpos = result["position"][min(i, n_step - 1)]`
- State change clarification: `# Reach`, `# Grasp`, `# Lift`, `# Stack on cubeB`, `# Release`

**JSDoc/TSDoc:**
- Not used (Python project)
- Uses triple-quoted docstrings for classes and functions

## Comments Style

**Docstrings:**
- Use triple-quoted strings `"""docstring"""` for modules, classes, and functions
- Include parameter descriptions in docstring body
- One-line docstrings for simple functions: `"""Thin wrapper around WandB for episode logging."""`
- Multi-line docstrings for complex methods with parameter and return descriptions

**Examples from codebase:**

Class docstring:
```python
"""StackCube-v1 with an additional blue cube as a visual distractor.

The task and success criteria are identical to StackCube-v1 — stack the
red cube on the green cube.  The blue cube simply sits on the table.

Set ``force_close_distractor=True`` to place the blue cube right next
to cubeA (for testing planner robustness).
"""
```

Function docstring:
```python
"""Run a full grasp-lift-stack sequence on a *single* raw gym env.

The env must use ``pd_joint_pos`` control mode and ``num_envs=1``.
Returns the last ``(obs, reward, terminated, truncated, info)`` tuple.
"""
```

## Function Design

**Size:** Functions are compact, averaging 15-30 lines for utility functions, up to 50 lines for coordination methods like `solve()`

**Parameters:**
- Explicit parameter types with annotations: `def run_random(config: Config, logger: Logger):`
- Default parameters for optional behavior: `def _follow_path(self, env, result, gripper_state, refine_steps=0):`
- Keyword-only arguments used implicitly via defaults

**Return Values:**
- Tuple returns for multi-valued results: `return obs, reward, terminated, truncated, info`
- Single-value returns for status: `return -1` for planning failures
- Dict returns for configuration: dataclasses return dicts via `__dict__` attribute
- No return statement implicitly returns `None` for state-modifying methods

## Module Design

**Exports:**
- `ps_bed/run.py` exports `main()` for Hydra entry point and helper functions `run_random()`, `run_pick_place()`, `seed_everything()`
- `ps_bed/env.py` exports `make_env()` and `make_single_env()` factory functions
- `ps_bed/config.py` exports dataclasses: `Config`, `EnvConfig`, `LoggingConfig`, `RunConfig`
- `ps_bed/skills/pick_place.py` exports `PickPlaceSkill` class and helper function `_sapien_to_mplib_pose()`
- `ps_bed/logger.py` exports `Logger` class

**Barrel Files:**
- `ps_bed/__init__.py` is empty (no re-exports)
- `ps_bed/envs/__init__.py` triggers environment registration via side-effect import: `import ps_bed.envs.stack_cube_distractor  # noqa: F401`
- `ps_bed/skills/__init__.py` is empty

## Type Annotations

**Usage:**
- Function parameters annotated: `def run_random(config: Config, logger: Logger):`
- Return types annotated: `def main(cfg: Config) -> None:`
- Helper functions fully annotated: `def _sapien_to_mplib_pose(pose: sapien.Pose) -> mplib.pymp.Pose:`
- Dataclass fields do not require type hints (inferred from dataclass decorator)

## Style Preferences

**String formatting:**
- F-strings for dynamic output: `f"[Episode {episodes_done}/{target_episodes}]  return={ep_ret:.2f}  len={ep_len}  success={ep_succ}"`
- Percentage formatting for numerical output: `f"{rate:.2f}"` for floats

**Conditionals:**
- Ternary operators for simple assignments: `close_tag = " [CLOSE]" if (ep % 2 == 0) else " [FAR]"`
- Early returns/exits: `if res == -1: continue`
- Compound conditions with parentheses for clarity: `if episodes_done % 20 == 0 or episodes_done == target_episodes:`

**Numpy/PyTorch conversions:**
- Explicit type conversions for numpy arrays: `if isinstance(rewards, torch.Tensor): rewards = rewards.cpu().numpy()`
- Flatten batched tensors before passing to mplib: `np.asarray(pose.p, dtype=np.float64).flatten()[:3]`

---

*Convention analysis: 2025-02-13*
