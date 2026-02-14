# Architecture Patterns

**Domain:** Multi-object sequential manipulation (N-cube stacking) in ManiSkill3
**Researched:** 2026-02-13

## Current Architecture (Baseline)

The existing system has five clear layers with hardcoded two-cube assumptions throughout:

```
[Hydra Config] --> [Env Factory] --> [Policy Runner] --> [Skill Layer] --> [ManiSkill3 Env]
  config.py          env.py           run.py           pick_place.py    stack_cube_distractor.py
```

**Current two-cube assumptions baked into the code:**
- `StackCubeEnv` hardcodes `self.cubeA` and `self.cubeB` as named attributes
- `PickPlaceSkill.solve()` directly references `raw.cubeA` and `raw.cubeB`
- `evaluate()` checks a single "is_cubeA_on_cubeB" condition
- Dense reward has a single reach-grasp-place-release progression
- `_get_obs_extra()` returns fixed `cubeA_pose`, `cubeB_pose`, pairwise distances

## Recommended Architecture for N-Cube Stacking

### Design Principle: Loop Over Primitives, Not a Task Graph

After analyzing ManiSkill3's own `StackPyramid` solution and the existing `PickPlaceSkill`, the evidence strongly favors a **sequential loop** pattern over a state machine or task graph for this domain. Here is why:

1. **The task is inherently sequential.** You stack cube 1 on the base, then cube 2 on cube 1, etc. There is no parallelism, no branching, no conditional paths.
2. **ManiSkill3's own StackPyramid solution** uses a flat sequential script, not a state machine. It calls `move_to_pose_with_screw()` in a linear sequence (verified: `/mani_skill/examples/motionplanning/panda/solutions/stack_pyramid.py`).
3. **State machines add complexity without benefit** when the transitions are purely linear. A state machine is warranted when you have error recovery branches, concurrent skills, or non-deterministic transitions. N-cube vertical stacking has none of these.

**Recommendation: Decompose `PickPlaceSkill.solve()` into reusable primitives, then loop over (cube, target) pairs in a `StackNSkill.solve()` method.**

### Component Boundaries

| Component | Responsibility | Communicates With | Changes from Baseline |
|-----------|---------------|-------------------|-----------------------|
| **`Config` (Hydra)** | Declare `num_cubes`, env params | Env Factory, Policy Runner | Add `num_cubes: int` to `EnvConfig` |
| **`Env Factory`** (`env.py`) | Create gym env with correct `env_id` and pass `num_cubes` | ManiSkill3 gym registry | Pass `num_cubes` kwarg to `gym.make()` |
| **`StackNCubeEnv`** | Spawn N cubes, evaluate N-1 stacking conditions, compute reward | ManiSkill3 BaseEnv | New env class, replaces hardcoded cube attrs with `self.cubes: list[Actor]` |
| **`StackNSkill`** | Orchestrate N-1 pick-place iterations | Grasp primitives, Env | New skill class that loops pick-place primitives |
| **`GraspPrimitives`** (module) | Low-level: compute_grasp, reach, grasp, lift, place, release | mplib Planner, Env | Extract from `PickPlaceSkill` into standalone functions |
| **`Policy Runner`** (`run.py`) | Episode loop, logging | Skill, Env Factory, Logger | Minimal changes -- just dispatch to `StackNSkill` |
| **`Logger`** | WandB metrics | Policy Runner | Add per-step success metrics (cubes_stacked count) |

### Data Flow

```
User invokes:
  python -m ps_bed.run env.env_id=StackNCube-v1 env.num_cubes=4 run.policy=stack_n

1. Hydra loads Config with num_cubes=4
2. run.py dispatches to run_stack_n()
3. run_stack_n() calls make_single_env(cfg) which does:
     gym.make("StackNCube-v1", num_cubes=4, ...)
4. StackNCubeEnv.__init__ stores num_cubes, _load_scene creates 4 cubes
5. StackNSkill.solve(env, seed) executes:
     env.reset(seed)
     planner = setup_planner(env)
     cubes = env.unwrapped.cubes          # list of 4 Actor objects
     base_cube = cubes[0]                 # bottom of stack (stays on table)
     for i in range(1, len(cubes)):
         pick_cube = cubes[i]
         stack_target = cubes[i-1]        # top of current stack
         stack_height = i * cube_size     # cumulative height
         grasp_primitives.pick_and_stack(env, planner, pick_cube, stack_target, stack_height)
     return final (obs, reward, terminated, truncated, info)
```

## Patterns to Follow

### Pattern 1: Parameterized Environment via Constructor Kwargs

**What:** Pass `num_cubes` as a constructor parameter to the environment, stored as instance attribute, used in `_load_scene` to build a variable number of actors.

**Why this pattern:** ManiSkill3's `register_env` decorator passes `**kwargs` through to `gym.register`, which forwards them to the environment constructor. This is the canonical ManiSkill3 pattern (verified in `registration.py` source, line 238: `default_kwargs=deepcopy(kwargs)`). The `PickClutterYCB` environment demonstrates a similar pattern with `episode_json` and `reconfiguration_freq`.

**Confidence:** HIGH (verified against ManiSkill3 source code)

**Example:**
```python
@register_env("StackNCube-v1", max_episode_steps=100)
class StackNCubeEnv(BaseEnv):
    SUPPORTED_ROBOTS = ["panda_wristcam", "panda", "fetch"]

    def __init__(
        self,
        *args,
        robot_uids="panda_wristcam",
        robot_init_qpos_noise=0.02,
        num_cubes: int = 3,
        **kwargs,
    ):
        self.num_cubes = num_cubes
        self.robot_init_qpos_noise = robot_init_qpos_noise
        super().__init__(*args, robot_uids=robot_uids, **kwargs)

    def _load_scene(self, options: dict):
        self.cube_half_size = common.to_tensor([0.02] * 3, device=self.device)
        self.table_scene = TableSceneBuilder(
            env=self, robot_init_qpos_noise=self.robot_init_qpos_noise
        )
        self.table_scene.build()

        # Build N cubes with distinct colors
        colors = [
            [1, 0, 0, 1],    # red
            [0, 1, 0, 1],    # green
            [0, 0, 1, 1],    # blue
            [1, 1, 0, 1],    # yellow
            [1, 0, 1, 1],    # magenta
            [0, 1, 1, 1],    # cyan
        ]
        self.cubes = []
        for i in range(self.num_cubes):
            cube = actors.build_cube(
                self.scene,
                half_size=0.02,
                color=colors[i % len(colors)],
                name=f"cube_{i}",
                initial_pose=sapien.Pose(p=[i * 0.5, 0, 0.1]),
            )
            self.cubes.append(cube)

        # Backward compat aliases for 2-cube case
        if self.num_cubes >= 2:
            self.cubeA = self.cubes[0]
            self.cubeB = self.cubes[1]
```

### Pattern 2: Extracted Grasp Primitives as Stateless Functions

**What:** Factor the low-level motion planning steps out of `PickPlaceSkill.solve()` into a `grasp_primitives` module containing pure functions that take `(env, planner, ...)` as arguments.

**Why this pattern:** The current `PickPlaceSkill` mixes two concerns: (1) orchestrating a grasp-lift-stack sequence and (2) computing grasp poses, planning motions, and executing trajectories. For N-cube stacking, the orchestration must change (loop N-1 times) but the primitives stay identical. Extracting primitives enables reuse without inheritance hierarchies.

**Confidence:** HIGH (based on direct code analysis of both the existing skill and ManiSkill3's reference solutions)

**Example:**
```python
# ps_bed/skills/grasp_primitives.py

def compute_grasp_pose(env, cube, finger_length=0.025):
    """Compute a collision-free grasp pose for a cube."""
    obb = get_actor_obb(cube)
    approaching = np.array([0, 0, -1])
    target_closing = (
        env.unwrapped.agent.tcp.pose.to_transformation_matrix()[0, :3, 1].cpu().numpy()
    )
    grasp_info = compute_grasp_info_by_obb(
        obb, approaching=approaching,
        target_closing=target_closing, depth=finger_length,
    )
    return env.unwrapped.agent.build_grasp_pose(
        approaching, grasp_info["closing"], grasp_info["center"]
    )

def find_valid_grasp(env, planner, grasp_pose, move_fn):
    """Search grasp orientations for a collision-free plan."""
    angles = np.arange(0, np.pi * 2 / 3, np.pi / 2)
    angles = np.repeat(angles, 2)
    angles[1::2] *= -1
    for angle in angles:
        delta = sapien.Pose(q=euler2quat(0, 0, angle))
        candidate = grasp_pose * delta
        res = move_fn(candidate, dry_run=True)
        if res != -1:
            return candidate
    return None  # all orientations failed

def pick_and_stack(env, planner, pick_cube, target_cube, stack_height,
                   move_fn, gripper_fn, finger_length=0.025):
    """Full pick-lift-stack-release sequence for one cube."""
    grasp_pose = compute_grasp_pose(env, pick_cube, finger_length)
    grasp_pose = find_valid_grasp(env, planner, grasp_pose, move_fn) or grasp_pose

    # Reach (approach from above)
    reach_pose = grasp_pose * sapien.Pose([0, 0, -0.05])
    move_fn(reach_pose)

    # Grasp
    move_fn(grasp_pose)
    gripper_fn(close=True)

    # Lift
    lift_pose = sapien.Pose([0, 0, 0.1]) * grasp_pose
    move_fn(lift_pose)

    # Align over target
    goal_pos = target_cube.pose.p.cpu().numpy()[0].copy()
    goal_pos[2] += stack_height + 0.02  # clearance
    offset = goal_pos - pick_cube.pose.p.cpu().numpy()[0]
    align_pose = sapien.Pose(np.asarray(lift_pose.p) + offset, lift_pose.q)
    move_fn(align_pose)

    # Release
    return gripper_fn(close=False)
```

### Pattern 3: List-Based Cube Storage with Collision-Free Placement

**What:** Store cubes in a `self.cubes: list[Actor]` and use `UniformPlacementSampler` in a loop to place all N cubes with collision avoidance.

**Why this pattern:** ManiSkill3's `UniformPlacementSampler.sample()` is designed for exactly this -- each call returns a position that avoids all previously sampled positions (it maintains internal state of fixture positions). Both `StackCubeEnv` and `StackPyramidEnv` use this pattern already. The sampler is batched, so it works with GPU-parallelized envs.

**Confidence:** HIGH (verified against ManiSkill3 `randomization/samplers.py` source)

**Example:**
```python
def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
    with torch.device(self.device):
        b = len(env_idx)
        self.table_scene.initialize(env_idx)

        xyz = torch.zeros((b, 3))
        xyz[:, 2] = 0.02
        xy = torch.rand((b, 2)) * 0.2 - 0.1

        # Bounds may need to grow with num_cubes to avoid sampling failures
        region = [[-0.15, -0.25], [0.15, 0.25]]
        sampler = randomization.UniformPlacementSampler(
            bounds=region, batch_size=b, device=self.device
        )
        radius = torch.linalg.norm(torch.tensor([0.02, 0.02])) + 0.001

        for i, cube in enumerate(self.cubes):
            cube_xy = xy + sampler.sample(radius, 100, verbose=(i == 0))
            xyz[:, :2] = cube_xy
            qs = randomization.random_quaternions(
                b, lock_x=True, lock_y=True, lock_z=False
            )
            self.cubes[i].set_pose(Pose.create_from_pq(p=xyz.clone(), q=qs))
```

### Pattern 4: Progressive Evaluation for Partial Credit

**What:** The `evaluate()` method counts how many cubes are correctly stacked (not just binary success), enabling richer reward signals and metrics.

**Why this pattern:** With 5+ cubes, binary success becomes extremely sparse. ManiSkill3's `StackPyramidEnv.evaluate()` checks multiple conditions (A next to B, C on top of both). For a vertical N-stack, the natural analog is counting consecutive correctly-stacked cubes from the bottom up. This also gives the policy runner meaningful intermediate metrics.

**Confidence:** MEDIUM (pattern extrapolated from StackPyramid; the specific progressive counting is our design choice)

**Example:**
```python
def evaluate(self):
    cubes_stacked = torch.zeros(self.num_envs, device=self.device, dtype=torch.int32)
    all_static = torch.ones(self.num_envs, device=self.device, dtype=torch.bool)
    any_grasped = torch.zeros(self.num_envs, device=self.device, dtype=torch.bool)

    for i in range(1, self.num_cubes):
        pos_top = self.cubes[i].pose.p
        pos_bot = self.cubes[i - 1].pose.p
        offset = pos_top - pos_bot

        xy_ok = torch.linalg.norm(offset[..., :2], axis=1) <= (
            torch.linalg.norm(self.cube_half_size[:2]) + 0.005
        )
        z_ok = torch.abs(
            offset[..., 2] - self.cube_half_size[2] * 2
        ) <= 0.005
        pair_stacked = xy_ok & z_ok

        # Only count if all below are stacked (consecutive from bottom)
        if i == 1:
            cubes_stacked += pair_stacked.int()
        else:
            cubes_stacked += (pair_stacked & (cubes_stacked >= i - 1)).int()

        all_static &= self.cubes[i].is_static(lin_thresh=1e-2, ang_thresh=0.5)
        any_grasped |= self.agent.is_grasping(self.cubes[i])

    success = (cubes_stacked == self.num_cubes - 1) & all_static & (~any_grasped)
    return {
        "cubes_stacked": cubes_stacked,
        "all_static": all_static,
        "any_grasped": any_grasped,
        "success": success.bool(),
    }
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Inheriting from StackCubeEnv for N-Cube

**What:** Making `StackNCubeEnv` extend `StackCubeEnv` (the way `StackCubeDistractorEnv` extends it).

**Why bad:** `StackCubeEnv` hardcodes `self.cubeA` and `self.cubeB` throughout `_load_scene`, `_initialize_episode`, `evaluate`, `_get_obs_extra`, and `compute_dense_reward`. Every one of these methods would need to be completely overridden, defeating the purpose of inheritance. The `StackCubeDistractor` extension works because it only *adds* a cube; an N-cube env *replaces* the entire scene logic.

**Instead:** Extend `BaseEnv` directly, copying the `TableSceneBuilder` pattern from `StackCubeEnv` but using a list of cubes. Keep the `StackCubeDistractorEnv` as-is -- it serves a different purpose.

### Anti-Pattern 2: State Machine with Named States for Linear Sequences

**What:** Building an explicit `SkillState` enum (REACH, GRASP, LIFT, ALIGN, RELEASE, NEXT_CUBE) with transition logic.

**Why bad:** For a strictly linear sequence with no branching or error recovery, a state machine adds boilerplate (state enum, transition table, state tracking) without providing any benefit. The ManiSkill3 reference solutions (both `stack_cube.py` and `stack_pyramid.py`) use flat sequential code. A state machine is warranted only when you need: conditional branching (if grasp fails, try re-approach), concurrent skills, or reentrant execution. None of these apply to motion-planned N-stacking.

**Instead:** Use a simple `for` loop over `(pick_cube, target_cube)` pairs, calling sequential primitive functions.

### Anti-Pattern 3: Monolithic solve() That Handles All N

**What:** Writing a single `solve()` method with N-specific branches or deeply nested logic.

**Why bad:** The current `PickPlaceSkill.solve()` is already 70 lines for 2 cubes. Scaling to N cubes inline would create an unreadable method. ManiSkill3's `stack_pyramid.py` already shows strain at 3 cubes -- the code has repeated blocks and a conditional `need_move_a_b` flag that would not scale.

**Instead:** Extract `pick_and_stack()` as a primitive, then the orchestrating `solve()` is a clean 15-line loop.

### Anti-Pattern 4: Variable `max_episode_steps` at Runtime

**What:** Trying to dynamically adjust `max_episode_steps` based on `num_cubes` after environment creation.

**Why bad:** ManiSkill3's `TimeLimitWrapper` reads `max_episode_steps` from the gym `EnvSpec` at creation time (verified in `registration.py`). It cannot be changed after `gym.make()`. The `register_env` decorator bakes it in.

**Instead:** Set a generous default (e.g., `max_episode_steps=250` for up to 6 cubes) and override via `gym.make("StackNCube-v1", max_episode_steps=N*50)` at creation time, which ManiSkill3's `TimeLimitWrapper` does support.

## Recommended File Structure After Changes

```
ps_bed/
    config.py               # Add num_cubes to EnvConfig
    env.py                  # Pass num_cubes to gym.make
    run.py                  # Add run_stack_n() dispatcher
    logger.py               # (minimal changes)
    envs/
        __init__.py          # Register StackNCube-v1
        stack_cube_distractor.py  # UNCHANGED
        stack_n_cube.py      # NEW: parameterized N-cube env
    skills/
        __init__.py
        pick_place.py        # UNCHANGED (kept for backward compat)
        grasp_primitives.py  # NEW: extracted low-level functions
        stack_n.py           # NEW: StackNSkill with solve() loop
```

## Build Order (Dependencies Between Components)

The components have clear dependency ordering:

```
Phase 1: grasp_primitives.py
    Depends on: nothing new (uses existing mplib, sapien, ManiSkill utils)
    Unlocks: StackNSkill, and can be tested against existing StackCube-v1

Phase 2: stack_n_cube.py (environment)
    Depends on: nothing new (extends BaseEnv, uses actors.build_cube, UniformPlacementSampler)
    Unlocks: all testing with random policy immediately

Phase 3: stack_n.py (skill)
    Depends on: grasp_primitives.py (Phase 1) + stack_n_cube.py (Phase 2)
    This is the integration point

Phase 4: config.py + env.py + run.py (wiring)
    Depends on: Phase 2 + Phase 3
    Can be done incrementally alongside Phase 3
```

**Critical path:** Phase 1 and Phase 2 are independent and can be built in parallel. Phase 3 requires both. Phase 4 is light wiring that can happen alongside Phase 3.

**Recommendation:** Build Phase 1 first because it can be validated against the existing `StackCube-v1` environment -- extract primitives from `PickPlaceSkill.solve()`, then verify the existing pick-place still works. This de-risks the refactor before adding new env complexity.

## Scalability Considerations

| Concern | N=2 (current) | N=3-4 | N=5-6 | N>6 |
|---------|---------------|-------|-------|-----|
| **Episode length** | 50 steps | 100-150 steps | 200-300 steps | Linear growth, need proportional `max_episode_steps` |
| **Placement region** | 0.2x0.4 table region | Adequate | May hit sampling failures | Widen `region` bounds or reduce cube count |
| **Motion planning time** | ~0.5s per plan | Same per plan, 3-4x total | 5-6x total | Linear growth, acceptable for research |
| **Stack stability** | Trivial | Still stable | Physics instability possible | May need damping or wider cubes |
| **Observation space** | 2 cube poses + pairwise | 3-4 poses + O(N^2) pairs | Variable-size obs complicates RL | Use padded fixed-size obs or just pairwise-to-stack-top |
| **Reward shaping** | Single reach-grasp-place | Per-step rewards for each stack level | Reward complexity grows linearly | Hierarchical reward: per-cube-stacked bonus |

**Key scaling decision:** For observations, use a fixed-size representation padded to `max_cubes` (e.g., 6) rather than variable-length. This avoids RL framework compatibility issues. Cubes beyond `num_cubes` get zero-padded poses and are masked out. This is the pattern used by ManiSkill3's `PickClutterYCB` for variable object counts.

## Sources

- ManiSkill3 `StackCubeEnv` source: `/mani_skill/envs/tasks/tabletop/stack_cube.py` (HIGH confidence, direct source)
- ManiSkill3 `StackPyramidEnv` source: `/mani_skill/envs/tasks/tabletop/stack_pyramid.py` (HIGH confidence, direct source)
- ManiSkill3 stack_cube motion planning solution: `/mani_skill/examples/motionplanning/panda/solutions/stack_cube.py` (HIGH confidence)
- ManiSkill3 stack_pyramid motion planning solution: `/mani_skill/examples/motionplanning/panda/solutions/stack_pyramid.py` (HIGH confidence)
- ManiSkill3 `PickClutterYCB` for variable object patterns: `/mani_skill/envs/tasks/tabletop/pick_clutter_ycb.py` (HIGH confidence)
- ManiSkill3 `register_env` and gym registration: `/mani_skill/utils/registration.py` (HIGH confidence)
- ManiSkill3 `UniformPlacementSampler`: `/mani_skill/envs/utils/randomization/samplers.py` (HIGH confidence)
- ManiSkill3 BaseEnv constructor and `reconfiguration_freq`: `/mani_skill/envs/sapien_env.py` (HIGH confidence)
- ManiSkill3 custom task tutorial: [Introduction to Task Building](https://maniskill.readthedocs.io/en/latest/user_guide/tutorials/custom_tasks/intro.html) (MEDIUM confidence, web fetch)
- ManiSkill3 env template: [GitHub template.py](https://github.com/haosulab/ManiSkill/blob/main/mani_skill/envs/template.py) (MEDIUM confidence, web fetch)
- Existing ps_bed codebase: all files in `/ps_bed/` (HIGH confidence, direct source)
