# Feature Landscape

**Domain:** Multi-object sequential robotic stacking (simulation testbed)
**Researched:** 2026-02-13

## Table Stakes

Features required for the N-cube stacking milestone to be useful.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Configurable N (cube count) | Core requirement -- testbed must handle variable object counts | Med | Constructor kwarg `num_cubes`, forwarded through `gym.make` |
| Sequential pick-place skill | Must stack N cubes in order | Med | Loop over parameterized single pick-place, not monolithic |
| Collision-aware placement sampling | N cubes on table must not overlap at spawn | Low | `UniformPlacementSampler` already handles this -- just loop N times |
| Success evaluation for N-high stack | Must verify full tower is correctly stacked and stable | Med | Check each adjacent pair (i, i+1) for alignment + static + released |
| Video recording of full sequence | Demo generation is the project's purpose | Low | Already works -- just ensure `max_episode_steps` scales with N |
| Hydra config for num_cubes | Testbed is config-driven | Low | Add field to `EnvConfig` dataclass |

## Differentiators

Features not strictly required but high-value for the research testbed.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Stacking order specification | Control which cube goes where (bottom-up color order, random, etc.) | Low | Skill takes ordered list of cube indices |
| Per-step collision awareness in planner | Planner knows about already-stacked cubes, avoids knocking them | Med | `update_point_cloud` or `update_attached_box` in mplib -- see STACK.md |
| Partial success metrics | Track how many cubes were successfully stacked before failure | Low | `evaluate()` returns `{"cubes_stacked": k, "success": k == N}` |
| Distractor objects (non-target cubes on table) | Test robustness to irrelevant objects | Low | Already have `StackCubeDistractor-v1` pattern to extend |
| Configurable cube sizes | Test grasp generalization across sizes | Med | Parameterize `half_size`, adjust grasp depth and placement offsets |
| Failure recovery / retry per cube | If one pick-place fails, retry before giving up | Low | Wrap single pick-place in try/retry loop in skill |

## Anti-Features

Features to explicitly NOT build for this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| GPU-parallel N-cube stacking with planner | mplib requires `num_envs=1` + CPU sim -- cannot parallelize motion planning | Keep planner in single-env mode; use GPU parallelism only for RL policy evaluation later |
| RL policy for N-cube stacking | Out of scope for demo generation milestone; reward shaping for N cubes is a research problem | Focus on motion-planned demos first; RL is a future milestone |
| Dynamic N (changing cube count mid-episode) | ManiSkill3 actors are loaded in `_load_scene` which runs once at construction; changing N requires `reconfigure=True` reset | Fix N per environment instance; create new env for different N |
| Heterogeneous object shapes (not cubes) | Scope creep; grasp computation assumes box OBB | Stick to cubes; shape variation is a separate milestone |
| Multi-arm manipulation | Single Panda arm is the project scope | Single arm sequential manipulation |
| Dense reward shaping for N-cube | Complex to design correctly, only needed for RL | Use sparse reward (success/fail) for demo generation |

## Feature Dependencies

```
Configurable N (env) --> Collision-aware placement (N cubes on table)
Configurable N (env) --> Success evaluation (check N-1 stacking pairs)
Configurable N (env) --> Sequential pick-place skill (N-1 iterations)
Sequential pick-place skill --> Stacking order specification
Sequential pick-place skill --> Per-step collision awareness
Sequential pick-place skill --> Failure recovery / retry
Per-step collision awareness --> Partial success metrics (know what's stacked)
Hydra config --> Configurable N (env)
```

## MVP Recommendation

**Prioritize (Phase 1 -- must have):**
1. Configurable N environment (`StackNCube-v1`) with collision-aware spawn
2. Success evaluation for N-high stack
3. Sequential pick-place skill (loop of parameterized single pick-place)
4. Hydra config integration
5. Video recording of full sequence

**Phase 2 (high value, low cost):**
1. Partial success metrics (cubes_stacked count)
2. Stacking order specification
3. Failure recovery / retry per cube

**Defer:**
- Per-step collision awareness in planner: MEDIUM complexity, test without it first. For N=3-5, the geometry often works without explicit obstacle tracking. Add only if success rate drops.
- Configurable cube sizes: separate concern, defer to later milestone.
- Distractor objects: already proven pattern, add after core N-stacking works.

## Sources

- [ManiSkill3 StackPyramid env](https://github.com/haosulab/ManiSkill/blob/main/mani_skill/envs/tasks/tabletop/stack_pyramid.py) -- reference for 3-cube evaluation logic
- [ManiSkill3 StackPyramid solution](https://github.com/haosulab/ManiSkill/blob/main/mani_skill/examples/motionplanning/panda/solutions/stack_pyramid.py) -- reference for sequential manipulation
- Existing project code: `ps_bed/envs/stack_cube_distractor.py`, `ps_bed/skills/pick_place.py`
