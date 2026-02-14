# Program Synthesis Bed

## What This Is

A robotics research testbed for evaluating and stress-testing manipulation skills on ManiSkill3 cube-stacking tasks. It provides configurable environments with N cubes, a motion-planned pick-place skill, and video recording for generating demos. The primary user is a robotics researcher exploring multi-step manipulation and program synthesis.

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

### Active

- [ ] Configurable N-cube environment (parameterize cube count)
- [ ] Sequential skill chaining — loop pick-place N-1 times per episode
- [ ] Dynamic cube discovery — query all cubes in scene, pick first as base
- [ ] Dynamic placement targeting — compute stack-top position each cycle
- [ ] Abort-on-failure semantics — episode ends if any grasp/place step fails
- [ ] Video demos of multi-cube stacking sequences

### Out of Scope

- Learned/RL policies for stacking — this is about motion-planned skill execution
- Specific stacking order or color-based sequencing — any order is fine
- Success metrics dashboard or automated benchmarking — video output is sufficient for now
- Force/compliance control — relying on position-based motion planning

## Context

- Built on ManiSkill3 (3.0.0b22) with SAPIEN physics
- mplib 0.2.1 for motion planning (0.1.1 segfaults on this system)
- SAPIEN poses are batched even with num_envs=1 — must flatten before mplib
- numpy pinned to <2.0 for mplib compatibility
- Motion planner requires: num_envs=1, sim_backend="cpu", pd_joint_pos control
- Existing PickPlaceSkill handles single grasp-lift-stack cycle
- Existing StackCubeDistractor adds a blue distractor to StackCubeEnv (3 cubes total)

## Constraints

- **mplib API**: Must use mplib 0.2.x Pose objects, not numpy arrays
- **Single env**: Motion planner only works with num_envs=1, cpu backend
- **numpy**: Must stay on numpy <2.0 (mplib 0.2.1 requirement)
- **Physics stability**: Tall stacks (5+) may become unstable — placement precision matters
- **Video recording**: Must use save_on_reset=False with manual flush_video() for planner-based control

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Configurable N (not fixed count) | Enables experimentation with difficulty scaling | — Pending |
| New env vs extend distractor: Claude decides | Implementation detail — pick cleaner approach | — Pending |
| Any stacking order | Simplifies skill logic, order isn't the research question | — Pending |
| Abort on failure | Clean failure semantics, avoid partial/corrupt stacks | — Pending |
| First cube found as base | No need for designated base — arbitrary is fine | — Pending |

---
*Last updated: 2026-02-13 after initialization*
