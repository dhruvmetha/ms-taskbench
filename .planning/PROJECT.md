# Program Synthesis Bed

## What This Is

A robotics research testbed for evaluating and stress-testing manipulation skills on ManiSkill3 cube-stacking tasks. It provides configurable N-cube environments (2-6 cubes), a motion-planned sequential stacking skill, and Hydra-driven CLI with video recording for generating demos.

## Core Value

Reliably execute multi-step pick-place sequences on configurable N-cube environments and produce video demos of the results.

## Requirements

### Validated

- ✓ Single pick-place skill via mplib 0.2.x motion planning — existing
- ✓ Hydra-based configuration with CLI overrides — existing
- ✓ Random policy runner with vectorized environments — existing
- ✓ Pick-place policy runner with single-env setup — existing
- ✓ Video recording of episodes via RecordEpisode — existing
- ✓ Custom StackCubeDistractor-v1 environment with 3 cubes — existing
- ✓ Optional WandB experiment logging — existing
- ✓ Deterministic seeding across numpy/torch/python — existing
- ✓ Configurable N-cube environment (parameterize cube count) — v1.0
- ✓ Sequential skill chaining — loop pick-place N-1 times per episode — v1.0
- ✓ Dynamic cube discovery — query all cubes in scene, pick first as base — v1.0
- ✓ Dynamic placement targeting — compute stack-top position each cycle — v1.0
- ✓ Abort-on-failure semantics — episode ends if any grasp/place step fails — v1.0
- ✓ Video demos of multi-cube stacking sequences — v1.0

### Active

(None yet — define in next milestone)

### Out of Scope

- Learned/RL policies for stacking — this is about motion-planned skill execution
- Specific stacking order or color-based sequencing — any order is fine
- Success metrics dashboard or automated benchmarking — video output is sufficient for now
- Force/compliance control — relying on position-based motion planning
- GPU-parallel motion planning — mplib requires num_envs=1, CPU single-env
- Dynamic N mid-episode — ManiSkill3 actors loaded once at construction
- Heterogeneous object shapes — cubes only for now
- Dense reward shaping for N cubes — only needed for RL

## Context

Shipped v1.0 with 1,533 LOC Python across 3 phases in ~3 hours.
Tech stack: ManiSkill3 (3.0.0b22), SAPIEN, mplib 0.2.1, Hydra, numpy <2.0.

Key modules:
- `ps_bed/envs/stack_n_cube.py` — StackNCubeEnv (N=2-6, BaseEnv extension)
- `ps_bed/skills/stack_n.py` — StackNSkill (sequential N-1 pick-place loop)
- `ps_bed/skills/pick_place.py` — PickPlaceSkill (single-cycle, backward compatible)
- `ps_bed/run.py` — Hydra entry point with random/pick_place/stack_n dispatch

Known limitations:
- mplib plan_screw cannot route around obstacles — N>3 success rate drops
- Physics stability for tall stacks (5+) needs empirical tuning
- No retry logic — skill aborts on first failure

## Constraints

- **mplib API**: Must use mplib 0.2.x Pose objects, not numpy arrays
- **Single env**: Motion planner only works with num_envs=1, cpu backend
- **numpy**: Must stay on numpy <2.0 (mplib 0.2.1 requirement)
- **Physics stability**: Tall stacks (5+) may become unstable — placement precision matters
- **Video recording**: Must use save_on_reset=False with manual flush_video() for planner-based control

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Configurable N (not fixed count) | Enables experimentation with difficulty scaling | ✓ Good — works for N=2-6 |
| Extend BaseEnv directly (not StackCubeEnv) | StackCubeEnv hardcodes 2-cube assumptions in every method | ✓ Good — clean parameterized design |
| Any stacking order | Simplifies skill logic, order isn't the research question | ✓ Good — sequential bottom-up works |
| Abort on failure | Clean failure semantics, avoid partial/corrupt stacks | ✓ Good — clear cubes_stacked count and failure_reason |
| First cube as base | No need for designated base — arbitrary is fine | ✓ Good — cubes[0] as base, stack upward |
| StackNSkill inherits PickPlaceSkill | Reuse all motion planning primitives without modification | ✓ Good — zero changes to pick_place.py |
| Dynamic lift height formula | max(0.1, (step_index+2)*cube_height+0.05) scales with stack | ✓ Good — clears growing tower |
| Conditional num_cubes forwarding | Prevent unexpected kwargs to StackCube-v1 | ✓ Good — backward compatible |
| Auto env_id switching | UX improvement — no need to specify env_id with stack_n | ✓ Good — respects explicit overrides |
| Collision-aware planning deferred to v2 | plan_screw limitation acknowledged, not blocking v1 demos | — Pending |

---
*Last updated: 2026-02-14 after v1.0 milestone*
