# Codebase Concerns

**Analysis Date:** 2026-02-13

## Tech Debt

**mplib 0.2.x API Dependency & Fragility:**
- Issue: Motion planner relies on mplib 0.2.1 which has breaking API changes from the standard ManiSkill integration (0.1.1). The system uses direct `mplib.Planner` instantiation instead of ManiSkill's `PandaArmMotionPlanningSolver` wrapper, which is broken with mplib 0.2.x.
- Files: `ps_bed/skills/pick_place.py`
- Impact: Any attempt to upgrade mplib or use the standard ManiSkill motion planner will require significant refactoring. The code is tightly coupled to mplib 0.2.1's specific API (e.g., `mplib.pymp.Pose` objects, renamed methods like `plan_qpos_to_pose` → `plan_pose`). Upgrading numpy beyond 1.26.4 will break mplib 0.2.1.
- Fix approach: Either pin mplib/numpy versions permanently, or migrate to a more stable motion planning abstraction that doesn't depend on internal mplib APIs.

**SAPIEN Tensor Batching Workaround:**
- Issue: SAPIEN poses are always batched (shape `(1, 3)` / `(1, 4)`) even with `num_envs=1`. Code has multiple manual `.flatten()` and `[0]` indexing operations to work around this.
- Files: `ps_bed/skills/pick_place.py` lines 14, 72, 85, 125, 168; `ps_bed/run.py` various tensor conversions
- Impact: Fragile tensor indexing scattered throughout the codebase. Easy to introduce off-by-one errors when refactoring. Makes code harder to follow.
- Fix approach: Create a helper utility module `ps_bed/utils/tensor_utils.py` with functions like `flatten_pose()`, `extract_first_env()` to centralize tensor handling and document the batching assumption.

**Inconsistent Tensor Type Handling:**
- Issue: Code frequently checks `isinstance(x, torch.Tensor)` and converts to numpy, but this pattern is repeated in multiple places without abstraction.
- Files: `ps_bed/run.py` lines 44-58, 126-129; `ps_bed/skills/pick_place.py` lines 72, 85, 125, 168
- Impact: If the underlying framework changes tensor return types (e.g., from torch to numpy-native), multiple locations need updates. Type handling is a cross-cutting concern with no centralized point.
- Fix approach: Create a conversion utility module or use type stubs to enforce consistent return types at boundaries.

**Error Handling via Magic Return Value:**
- Issue: `_move_to_pose_with_screw()` in `ps_bed/skills/pick_place.py` returns `-1` to signal planning failure (line 100), but the caller uses bare equality check without semantic clarity.
- Files: `ps_bed/skills/pick_place.py` lines 100, 144
- Impact: The `-1` return value is a silent failure mode. If the function ever legitimately returns something other than a tuple (which it shouldn't), this will go undetected. No exception is raised, so the skill continues with undefined behavior.
- Fix approach: Raise a proper exception (`MotionPlanningError`) or use a Result type that explicitly distinguishes success/failure states.

## Known Bugs

**Unhandled Motion Planning Failure:**
- Symptoms: When `plan_screw()` fails twice in a row (lines 98-100), the function logs a warning and returns `-1` instead of raising an exception. The caller checks `if res == -1: continue` (line 144), silently skipping to the next grasp orientation without feedback.
- Files: `ps_bed/skills/pick_place.py` lines 91-100, 144
- Trigger: Run `python -m ps_bed.run run.policy=pick_place` with a complex distractor setup or tight workspace that causes planning to fail.
- Workaround: Increase `max_episode_steps` in config to allow more retry attempts, or disable distractor feature with `env.unwrapped.force_close_distractor=False`.
- Root cause: The else clause on the for loop (lines 148-149) only prints a warning if all grasp angles fail; the skill then proceeds with the last grasp_pose even if no collision-free orientation was found.

**Video Recording Manual Flush Requirement:**
- Symptoms: When recording video with motion planner (`env.record_video=true`), videos may be incomplete if `env.flush_video()` is not called after each episode.
- Files: `ps_bed/run.py` lines 132-133; `ps_bed/env.py` line 65
- Trigger: Run with `run.policy=pick_place env.record_video=true` and check that all videos have complete frames.
- Workaround: Ensure `RecordEpisode` is created with `save_on_reset=False` and `env.flush_video()` is called manually (already done in code).
- Root cause: `save_on_reset=False` is necessary because motion planner doesn't trigger resets between episodes (it calls reset once, then manually steps); ManiSkill's auto-reset in `ManiSkillVectorEnv` can't be used with motion planners.

## Security Considerations

**No Input Validation on Environment IDs:**
- Risk: `env_id` from config is passed directly to `gym.make()` without validation. A malicious or mistyped config could instantiate arbitrary ManiSkill environments.
- Files: `ps_bed/env.py` lines 15-16, 48-49; `ps_bed/config.py` line 8
- Current mitigation: Hydra validation ensures env_id is a string, but no whitelist of valid environments.
- Recommendations: Add enum or regex validation to `EnvConfig` to restrict to known safe environments (e.g., `Literal["StackCube-v1", "StackCubeDistractor-v1"]`).

**Unvalidated WandB Integration:**
- Risk: WandB project/group names and configuration are passed through without sanitization. If `logging.use_wandb=true` with user-supplied config, could expose internal parameters to public projects.
- Files: `ps_bed/logger.py` lines 13-21
- Current mitigation: Hardcoded defaults in `ps_bed/config.py` (project="ps_bed", group="stackcube"), but can be overridden at CLI.
- Recommendations: Document that `logging.project` and `logging.group` should never contain secrets, add a check to reject project names matching patterns that look like API keys.

## Performance Bottlenecks

**Planner Recreation Per Episode:**
- Problem: `_setup_planner()` creates a new `mplib.Planner` object from scratch for every episode (line 117 in `solve()`), rebuilding link/joint lists and loading URDF each time.
- Files: `ps_bed/skills/pick_place.py` line 117
- Cause: No caching or planner reuse across episodes. URDF loading and mplib initialization have non-trivial overhead.
- Improvement path: Create a `PickPlaceSkill.__init__()` that accepts an env as a parameter, cache the planner as `self.planner`, and reset it between episodes instead of recreating. Measure speedup with `time.perf_counter()`.

**No Motion Plan Caching:**
- Problem: Each call to `plan_screw()` recomputes the trajectory from scratch, even for similar poses.
- Files: `ps_bed/skills/pick_place.py` lines 86-97
- Cause: Motion planner is called once per motion primitive (reach, grasp, lift, stack, release) without attempting to batch or cache plans.
- Improvement path: If using the planner for many similar queries, consider implementing a trajectory cache based on (start_qpos, goal_pose) hash. Measure wall-clock time per episode.

**Double Planning in Grasp Search:**
- Problem: For each candidate grasp orientation, `_move_to_pose_with_screw()` is called with `dry_run=True` to validate, then called again with `dry_run=False` to execute. This doubles planning time.
- Files: `ps_bed/skills/pick_place.py` lines 143, 156
- Cause: Validation and execution are separate steps. Could be merged.
- Improvement path: Refactor to plan once, validate result status, and execute if valid. Measure total time for grasp search phase.

## Fragile Areas

**Motion Planner Environment Assumptions:**
- Files: `ps_bed/skills/pick_place.py` lines 105-115
- Why fragile: The `solve()` method has hard-coded assumptions about the environment:
  - Must have `control_mode` in `["pd_joint_pos", "pd_joint_pos_vel"]`
  - Must have `num_envs=1`
  - Must have raw gym interface (no `ManiSkillVectorEnv` wrapper)
  - Must have `agent`, `agent.robot`, `agent.urdf_path`, `agent.tcp` attributes
  - These assumptions are only validated at runtime with assertions (lines 112-115), not enforced at type or configuration level.
- Safe modification: Before calling `PickPlaceSkill.solve()`, ensure config is set with `env_cfg.control_mode = "pd_joint_pos"` and `env_cfg.num_envs = 1`. Use `make_single_env()` factory function. Add comprehensive docstring with environment requirements.
- Test coverage: No integration tests verify that motion planner works with different control modes or environment variants.

**Grasp Pose Search with Fallthrough:**
- Files: `ps_bed/skills/pick_place.py` lines 136-149
- Why fragile: The for-else loop attempts 4 grasp orientations (angles array line 137-139) and silently continues with the original grasp_pose if all fail. This is a silent degradation — the skill proceeds with an unvalidated grasp.
- Safe modification: If the else clause triggers (all angles fail), raise an exception or log a critical error instead of proceeding. Add retry logic with different approaching vectors.
- Test coverage: No test case for scenarios where all grasp orientations are in collision.

**Distractor Environment Coupling:**
- Files: `ps_bed/run.py` lines 111, 115-116, 145-146; `ps_bed/envs/stack_cube_distractor.py` lines 24, 69-73
- Why fragile: The run loop checks `hasattr(env.unwrapped, "force_close_distractor")` to detect if the environment supports distractor configuration, then sets it based on episode parity (line 116). This is fragile duck-typing with no interface definition.
- Safe modification: Create an abstract base class or protocol that defines distractor-capable environments, and check against that instead of using `hasattr()`.
- Test coverage: No test verifies that the distractor flag is actually being set or has the intended effect.

## Scaling Limits

**Vectorized Environment Limit:**
- Current capacity: Default `num_envs=16` (config.py line 12); tested up to 16 parallel environments
- Limit: Beyond ~64 envs, memory usage grows linearly with environment count. SAPIEN simulation becomes the bottleneck (not the policy).
- Scaling path: For higher throughput, increase `num_envs` and monitor GPU memory. The random policy is compute-trivial; the bottleneck is ManiSkill's physics simulation. If higher throughput is needed, consider using `sim_backend="cuda"` and enabling batched sim.

**Motion Planner Single-Environment Requirement:**
- Current capacity: One episode at a time
- Limit: Motion planner cannot be vectorized because `mplib.Planner` instances are not thread-safe. Each episode must complete before the next begins.
- Scaling path: To parallelize motion planning, refactor to use separate planner instances per worker thread, or implement a motion planning service that can handle concurrent requests (e.g., using multiprocessing with process pools).

## Dependencies at Risk

**mplib 0.2.1 Pinned with numpy Constraint:**
- Risk: mplib 0.2.1 requires `numpy<2.0`. When ManiSkill upgrades to numpy 2.0+, this project will be stuck or forced to migrate.
- Impact: Cannot upgrade to newer numpy ecosystem tools that depend on numpy 2.0+ API. Security updates to numpy may be missed.
- Migration plan: Track mplib releases for numpy 2.0 support. If mplib 0.2.x doesn't upgrade, migrate to a different motion planner (e.g., PyBullet, OMPL via MoveIt).

**ManiSkill 3.0.0b22 Beta Status:**
- Risk: Project depends on ManiSkill 3.0.0b22 which is a beta release. No guarantee of API stability in future releases.
- Impact: Upgrading to ManiSkill 3.1 or 4.0 could introduce breaking changes to env creation, sim backends, or observation/reward modes.
- Migration plan: Pin ManiSkill version explicitly in pyproject.toml until a stable 3.0.x release is available. Test compatibility with new releases before upgrading.

**WandB Optional but No Fallback:**
- Risk: If `logging.use_wandb=true` is set but wandb is not installed or network is unavailable, `wandb.init()` will hang or raise an unhandled exception.
- Impact: Can block experiment runs if wandb is down.
- Migration plan: Wrap wandb initialization in try-except, log warnings instead of failing, and ensure CLI docs clarify that wandb is optional.

## Missing Critical Features

**No Experiment Resume:**
- Problem: If a long run is interrupted (e.g., after 500/1000 episodes), there is no way to resume from episode 501. The entire run must restart.
- Blocks: Long-running experiments on unreliable hardware.
- Solution: Add checkpoint saving at regular intervals (e.g., every 100 episodes) and implement a `--resume_from_checkpoint` flag in Hydra config.

**No Episode Filtering or Replay:**
- Problem: Episodes are logged and executed but cannot be filtered by outcome, replayed, or debugged.
- Blocks: Analysis of failure modes, debugging specific scenarios.
- Solution: Save episode trajectories (observations, actions, rewards) to disk and implement a replay tool.

**No Metrics Aggregation Across Runs:**
- Problem: Results are logged to WandB or stdout, but there is no built-in way to aggregate results across multiple seeds or hyperparameter sweeps.
- Blocks: Running Hyperopt or statistical significance testing.
- Solution: Save all episode metrics to a local results database (e.g., SQLite or JSON lines) and provide a post-processing script to aggregate and analyze.

## Test Coverage Gaps

**No Unit Tests:**
- What's not tested: No test coverage exists. The repo explicitly states "No tests exist in this repo" in CLAUDE.md.
- Files: All source files in `ps_bed/`
- Risk: Any refactoring or dependency upgrade risks introducing silent bugs. Motion planner logic (grasp search, trajectory execution) is especially fragile.
- Priority: **High** — Motion planning is safety-critical in robotics. Add unit tests for:
  - `_sapien_to_mplib_pose()` conversion with various tensor shapes
  - Grasp search logic with different approaching vectors
  - Trajectory following with control mode variations
  - Integration test: full solve() pipeline on a test environment

**No Integration Tests:**
- What's not tested: Full episode runs with different policies, environments, and configurations are not tested.
- Risk: Configuration changes could silently break one policy path while the other still works (e.g., motion planner only tested manually).
- Priority: **High** — Add pytest fixture for a minimal test environment and run both `run_random()` and `run_pick_place()` against it.

**No Regression Tests for Motion Planning Failures:**
- What's not tested: Failure modes in `_move_to_pose_with_screw()`, grasp search, and planner initialization are not tested.
- Risk: Silent failures in motion planning go unnoticed until production.
- Priority: **Medium** — Add tests that intentionally trigger planning failures (e.g., with tight workspaces, collision-heavy scenes) and verify that they raise exceptions rather than silently degrading.

**No Environment Compatibility Tests:**
- What's not tested: Different `env_id` values and custom environments (like `StackCubeDistractor-v1`) are not tested programmatically.
- Risk: Custom env features (like `force_close_distractor`) might not work as intended.
- Priority: **Medium** — Add parametrized tests that instantiate both `StackCube-v1` and `StackCubeDistractor-v1` with different configurations and verify expected attributes.

---

*Concerns audit: 2026-02-13*
