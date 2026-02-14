# Technology Stack

**Project:** Program Synthesis Bed -- N-Cube Sequential Stacking
**Researched:** 2026-02-13

## Existing Stack (No Changes Required)

These are already in `pyproject.toml` and working. Not re-researched per milestone context.

| Technology | Version | Purpose |
|------------|---------|---------|
| ManiSkill3 | 3.0.0b22 | Simulation framework, GPU-parallel envs |
| mplib | 0.2.1 | Motion planning (Planner, PlanningWorld) |
| SAPIEN | (bundled) | Physics engine, pose types |
| Hydra | >=1.3 | Config management |
| gymnasium | (bundled) | Env interface |
| torch | (bundled) | Tensor ops for batched env state |
| numpy | 1.26.4 | Pinned <2.0 for mplib compatibility |

## New/Extended Stack for N-Cube Stacking

### No New Dependencies Required

The existing stack covers everything needed. N-cube stacking is an architecture and environment design problem, not a dependency problem. **Confidence: HIGH** -- verified against ManiSkill3 docs and existing StackPyramid reference implementation.

### ManiSkill3 APIs to Use

| API | Module | Purpose | Confidence |
|-----|--------|---------|------------|
| `actors.build_cube()` | `mani_skill.utils.building.actors` | Spawn N cubes in `_load_scene` | HIGH -- already used in project |
| `Actor.merge()` | `mani_skill.utils.structs.Actor` | Merge N cube actors into single batched actor for vectorized ops | HIGH -- used by PickSingleYCB, StackPyramid |
| `UniformPlacementSampler` | `mani_skill.envs.utils.randomization` | Collision-aware N-cube placement | HIGH -- already used in project |
| `register_env()` | `mani_skill.utils.registration` | Register `StackNCube-v1` with `num_cubes` kwarg | HIGH -- verified in registration.py source |
| `Pose.create_from_pq()` | `mani_skill.utils.structs.pose` | Batched pose creation | HIGH -- already used |
| `compute_grasp_info_by_obb` | `mani_skill.examples.motionplanning.base_motionplanner.utils` | OBB-based grasp computation per cube | HIGH -- already used in project |

### mplib 0.2.x APIs for Sequential Planning

| API | Class | Purpose | Confidence |
|-----|-------|---------|------------|
| `plan_screw(goal, current_qpos, time_step)` | `mplib.Planner` | Primary motion primitive | HIGH -- already used |
| `update_attached_box(size, pose, link_id=-1)` | `mplib.Planner` | Attach grasped cube to gripper for collision-aware planning of subsequent moves | MEDIUM -- verified in mplib 0.2 docs, not yet tested in project |
| `update_point_cloud(points, resolution, name)` | `mplib.Planner` | Add placed cubes as obstacles so planner avoids knocking the stack | MEDIUM -- verified in mplib 0.2 docs, not yet tested |
| `PlanningWorld.attach_box()` | `mplib.PlanningWorld` | Lower-level attached body management | MEDIUM -- verified in API docs |
| `PlanningWorld.detach_object()` | `mplib.PlanningWorld` | Remove attached body after release | MEDIUM -- verified in API docs |
| `PlanningWorld.add_object()` | `mplib.PlanningWorld` | Add placed cubes as static obstacles | MEDIUM -- verified in API docs |

### Hydra Config Extensions

| Component | Pattern | Purpose |
|-----------|---------|---------|
| `EnvConfig.num_cubes` | New field, `int = 3` | Parameterize cube count |
| `EnvConfig.env_id` | Default `StackNCube-v1` | New env registration |
| `RunConfig.policy` | Add `"stack_n"` option | New skill dispatch |

No new libraries needed. Config changes are additive.

## Key Technical Decisions

### Decision 1: Store cubes in a list, merge into one Actor for batched ops

**Use:** `self.cubes = [actors.build_cube(...) for i in range(num_cubes)]` in `_load_scene`, then `self.merged_cubes = Actor.merge(self.cubes)` for vectorized pose access.

**Why:** ManiSkill3's `Actor.merge()` gives you `self.merged_cubes.pose.p` as a `(num_envs, num_cubes, 3)` tensor -- no loops needed for evaluation. The PickSingleYCB env and StackPyramid env both use this pattern. Keep individual cube references too (e.g., `self.cubes[i]`) for skill code that operates on specific cubes.

**Confidence:** HIGH -- verified in ManiSkill3 PickSingleYCB source and StackPyramid source.

### Decision 2: Pass `num_cubes` as constructor kwarg via `register_env`

**Use:** `@register_env("StackNCube-v1", max_episode_steps=250)` with `__init__(self, *args, num_cubes=3, **kwargs)`.

**Why:** `register_env` forwards JSON-serializable kwargs to `__init__`. Gymnasium's `gym.make("StackNCube-v1", num_cubes=5)` works natively. This is the standard ManiSkill3 pattern (see PickSingleYCB's `reconfiguration_freq` kwarg).

**Confidence:** HIGH -- verified in `mani_skill/utils/registration.py` source.

### Decision 3: Use `update_attached_box` + `update_point_cloud` for sequential planning awareness

**Use:** After grasping cube i, call `planner.update_attached_box(size=[0.04]*3, pose=grasp_relative_pose)`. After placing cube i, add it as a point cloud obstacle via `planner.update_point_cloud()` or add as box obstacle via `PlanningWorld.add_object()`.

**Why:** Without this, the planner does not know about already-placed cubes and will plan paths that collide with the growing stack. The existing `PickPlaceSkill` works for 2 cubes only because there is only one pick-place operation. For N cubes, each subsequent pick-place must be aware of the already-stacked cubes.

**Confidence:** MEDIUM -- APIs verified in mplib 0.2 docs. The existing StackPyramid motion planning solution in ManiSkill3 does NOT use these APIs (it is a simpler 3-cube case that often avoids collision by luck/geometry). For N>3, collision awareness becomes necessary.

### Decision 4: Sequential skill loop, NOT monolithic solve

**Use:** A `StackNSkill.solve()` method that loops `for i in range(num_cubes - 1)` calling a parameterized single pick-place skill for each cube.

**Why:** The existing `PickPlaceSkill.solve()` hardcodes cubeA/cubeB references. Refactor to accept `(source_cube, target_pose)` parameters, then compose N-1 pick-place calls. This is the pattern used by the official StackPyramid solution (sequential phases, not parallel).

**Confidence:** HIGH -- verified against ManiSkill3 StackPyramid solution source.

### Decision 5: Scale `max_episode_steps` with N

**Use:** `max_episode_steps = 50 * num_cubes` (or similar linear scaling).

**Why:** StackCube (N=2) uses 50 steps. StackPyramid (N=3) uses 250 steps. Each pick-place cycle takes ~40-50 steps with the motion planner. Scaling linearly ensures the episode does not truncate before the skill sequence completes.

**Confidence:** HIGH -- derived from existing ManiSkill3 env configs.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Object storage | List + `Actor.merge()` | Dict of named actors | Merge gives vectorized tensor ops; dict requires manual iteration |
| Parameterization | Constructor kwarg `num_cubes` | Separate env class per N | Does not scale; ManiSkill3 pattern is kwargs |
| Collision awareness | `update_attached_box` + point cloud | No collision tracking | Works for N=2-3 but fails at N>3 when stack is tall enough to obstruct approach |
| Planning approach | Reuse mplib Planner per episode | Create new Planner per pick-place | Planner creation is expensive (URDF parsing); reuse and update state instead |
| Skill composition | Parameterized single-step skill in loop | Monolithic N-step method | Loop is testable, debuggable, and reusable for different stacking orders |

## Installation

No new packages. Existing setup works:

```bash
conda activate /common/users/dm1487/envs/maniskill
pip install -e .
```

## Sources

- [ManiSkill3 Custom Task Tutorial](https://maniskill.readthedocs.io/en/latest/user_guide/tutorials/custom_tasks/intro.html) -- HIGH confidence, official docs
- [ManiSkill3 Loading Actors](https://maniskill.readthedocs.io/en/latest/user_guide/tutorials/custom_tasks/loading_objects.html) -- HIGH confidence, official docs
- [ManiSkill3 Advanced Features](https://github.com/haosulab/ManiSkill/blob/main/docs/source/user_guide/tutorials/custom_tasks/advanced.md) -- HIGH confidence, official source
- [ManiSkill3 GPU Simulation Concepts](https://maniskill.readthedocs.io/en/latest/user_guide/concepts/gpu_simulation.html) -- HIGH confidence, official docs
- [ManiSkill3 StackPyramid Source](https://github.com/haosulab/ManiSkill/blob/main/mani_skill/envs/tasks/tabletop/stack_pyramid.py) -- HIGH confidence, official reference implementation
- [ManiSkill3 PickSingleYCB Source](https://github.com/haosulab/ManiSkill/blob/main/mani_skill/envs/tasks/tabletop/pick_single_ycb.py) -- HIGH confidence, official reference for Actor.merge pattern
- [ManiSkill3 StackPyramid Motion Planning Solution](https://github.com/haosulab/ManiSkill/blob/main/mani_skill/examples/motionplanning/panda/solutions/stack_pyramid.py) -- HIGH confidence, official reference
- [ManiSkill3 registration.py](https://github.com/haosulab/ManiSkill/blob/main/mani_skill/utils/registration.py) -- HIGH confidence, verified kwargs forwarding
- [mplib 0.2 Planner API](https://motion-planning-lib.readthedocs.io/v0.2.0a1/reference/Planner.html) -- MEDIUM confidence, docs match 0.2.x but project uses 0.2.1
- [mplib 0.2 PlanningWorld API](https://motion-planning-lib.readthedocs.io/stable/reference/PlanningWorld.html) -- MEDIUM confidence, same caveat
- [mplib Collision Avoidance Tutorial](https://motion-planning-lib.readthedocs.io/latest/tutorials/collision_avoidance.html) -- MEDIUM confidence, tutorial verified
