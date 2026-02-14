# Research Summary: N-Cube Sequential Stacking

**Domain:** Multi-object sequential robotic manipulation (simulation testbed)
**Researched:** 2026-02-13
**Overall confidence:** HIGH

## Executive Summary

Adding configurable N-cube stacking to the existing ps_bed testbed requires no new dependencies. The existing ManiSkill3 (3.0.0b22) + mplib (0.2.1) stack provides all necessary APIs. ManiSkill3 has two official reference implementations -- StackCube (2 cubes) and StackPyramid (3 cubes) -- that establish the patterns for multi-object manipulation. The key insight from analyzing these references is that ManiSkill3 environments handle variable object counts through constructor kwargs (forwarded via `register_env`), individual Actor references stored in lists, and `UniformPlacementSampler` for collision-free placement.

The primary architectural decision is to decompose the existing monolithic `PickPlaceSkill.solve()` into reusable grasp primitives, then compose N-1 sequential pick-place operations in a new `StackNSkill`. ManiSkill3's official StackPyramid solution validates this sequential-loop pattern -- it uses flat sequential code, not a state machine or task graph. The environment side requires a new `StackNCubeEnv` extending `BaseEnv` directly (not `StackCubeEnv`, which hardcodes 2-cube assumptions throughout).

The most consequential technical risk is physics instability in tall stacks. PhysX's iterative solver struggles with 4+ stacked cubes at the default solver iteration count, and mplib's `plan_screw` cannot route around obstacles. Both issues have known mitigations: increase solver iterations to 20+, and implement `plan_pose` (RRT-based) as a fallback when `plan_screw` fails. These mitigations should be built into Phase 1 rather than deferred.

A secondary risk is that the motion planner has no scene awareness -- after placing cube 1, the planner does not know it exists and may plan trajectories that collide with it. For N=3, this often works by geometric luck. For N>3, mplib's `update_point_cloud` API must be used to register placed cubes as obstacles. This API is documented and verified in mplib 0.2.x but has not been tested in this project, so it carries MEDIUM confidence.

## Key Findings

**Stack:** No new dependencies. Use existing ManiSkill3 APIs (`actors.build_cube`, `Actor.merge`, `register_env` with kwargs, `UniformPlacementSampler`) plus mplib 0.2.x APIs (`update_point_cloud`, `update_attached_box`, `plan_pose` fallback).

**Architecture:** Extend `BaseEnv` (not `StackCubeEnv`). Store cubes in `self.cubes` list. Extract grasp primitives from existing `PickPlaceSkill`. Compose N-1 pick-place calls in a loop. Build order: primitives and env in parallel, then skill integration, then config wiring.

**Critical pitfall:** mplib's `plan_screw` cannot navigate around obstacles. For stacks of 3+ cubes, the straight-line trajectory will collide with already-placed cubes. Must implement `plan_pose` (RRT) as fallback from day one.

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Environment + Physics Foundation** - Build `StackNCubeEnv`, tune physics parameters
   - Addresses: Configurable N, collision-free spawn, N-cube success evaluation, step budget scaling
   - Avoids: Physics instability pitfall (tune solver iterations early)
   - Validation: Drop-test N cubes scripted (no robot) to verify stable resting contact

2. **Grasp Primitives Extraction** - Refactor `PickPlaceSkill` into reusable functions
   - Addresses: Parameterized single pick-place (source cube + target pose)
   - Avoids: Monolithic solve() anti-pattern
   - Validation: Extracted primitives pass existing StackCube-v1 tests (backward compat)

3. **Sequential Stacking Skill** - Compose primitives into N-1 pick-place loop
   - Addresses: Sequential skill, abort semantics, partial success tracking
   - Avoids: No-abort-on-failure pitfall
   - Depends on: Phase 1 (env) + Phase 2 (primitives)

4. **Collision-Aware Planning** - Add planner scene awareness for robustness
   - Addresses: Point cloud obstacles, attached body tracking, plan_pose fallback
   - Avoids: Planner-ignores-placed-cubes pitfall
   - Note: May be partially integrated into Phase 3 if N=3 success rate is too low

5. **Config Integration + Polish** - Hydra wiring, run.py dispatch, logging
   - Addresses: Hydra config, video recording, WandB metrics
   - Light wiring phase, can overlap with Phase 3-4

**Phase ordering rationale:**
- Phase 1 before all others because the environment is the foundation. Physics tuning must happen early -- discovering instability after building the skill wastes effort.
- Phase 2 can be done in parallel with Phase 1 since it only touches existing code (refactoring `PickPlaceSkill`).
- Phase 3 depends on both Phase 1 and Phase 2 -- it is the integration point.
- Phase 4 can be deferred or interleaved. Start with N=3 (no collision awareness needed), then add it if N=4-5 success rate drops.
- Phase 5 is pure wiring with no research risk.

**Research flags for phases:**
- Phase 1: Needs empirical testing of solver iterations for N=5 stability. Recommend a scripted drop test early.
- Phase 3: Standard pattern (loop of primitives). Unlikely to need additional research.
- Phase 4: `update_point_cloud` and `update_attached_box` APIs are MEDIUM confidence -- need hands-on validation. May discover coordinate frame issues (point cloud must be in robot root frame, not world frame).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new deps. All APIs verified against official docs and source code. |
| Features | HIGH | Feature landscape derived from existing ManiSkill3 reference implementations (StackCube, StackPyramid). |
| Architecture | HIGH | Build patterns verified against PickSingleYCB (Actor.merge, kwargs), StackPyramid (sequential skill), and BaseEnv source (lifecycle hooks). |
| Pitfalls | MEDIUM-HIGH | Critical pitfalls (planner collision, physics stability, plan_screw limitations) verified in docs. Severity estimates are based on engineering judgment, not empirical data from this project. |

## Gaps to Address

- **mplib `update_point_cloud` coordinate frame:** Documentation says "world frame" but one GitHub issue suggests robot root frame. Needs empirical verification with a simple test case. Flag for Phase 4.
- **mplib `update_attached_box` with mplib 0.2.1 specifically:** API verified in 0.2.0a1 docs, but the project uses 0.2.1. Minor version differences may exist. Test early.
- **PhysX solver iterations for N>5:** No empirical data. The recommendation to use 20+ iterations is from ManiSkill docs for "stable grasps," but stacking may need even more. Empirical tuning needed.
- **`max_episode_steps` dynamic override:** Verified that `gym.make` accepts `max_episode_steps` kwarg and it overrides the `register_env` default. But unclear if this works for all gymnasium wrappers. Needs validation.
- **Observation space for RL readiness:** For N cubes, observation includes O(N) poses and O(N^2) pairwise distances. Fixed-size padded observations (pad to max_cubes=6) are recommended but not validated against downstream RL frameworks.
