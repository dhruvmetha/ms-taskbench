# Phase 1: N-Cube Environment - Research

**Researched:** 2026-02-13
**Domain:** ManiSkill3 custom environment with parameterized N-cube spawning, collision-free placement, and N-stack success evaluation
**Confidence:** HIGH

## Summary

Phase 1 builds a new `StackNCubeEnv` extending `BaseEnv` directly (not `StackCubeEnv`) that spawns N cubes (2-6) on the table with collision-free random placement, evaluates stacking success across all N-1 adjacent pairs, and provides a step budget scaled to N. No new dependencies are needed -- the existing ManiSkill3 3.0.0b22 stack provides every API required: `actors.build_cube()` for spawning, `UniformPlacementSampler` for collision-free placement, `register_env()` for gym registration with custom kwargs, and `Actor.is_static()` / `agent.is_grasping()` for evaluation.

The environment extends `BaseEnv` directly because `StackCubeEnv` hardcodes two-cube assumptions in every overridable method (`_load_scene`, `_initialize_episode`, `evaluate`, `_get_obs_extra`, `compute_dense_reward`). Extending it would require overriding every method, negating the benefit of inheritance. The prior research document explicitly recommends this approach.

The primary technical risk in this phase is physics instability for tall stacks (N=5-6). The default PhysX solver uses 15 position iterations, which ManiSkill's own source code notes may be insufficient ("solver iterations 15 is recommended to balance speed and accuracy. If stable grasps are necessary >= 20 is preferred"). The environment should override `_default_sim_config` to use 20+ solver position iterations.

**Primary recommendation:** Build `ps_bed/envs/stack_n_cube.py` extending `BaseEnv` with `num_cubes` constructor kwarg, `self.cubes` list, looped `UniformPlacementSampler`, and N-pair `evaluate()`. Set `max_episode_steps=250` as a generous default for up to 6 cubes, overridable at `gym.make()` time.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ManiSkill3 | 3.0.0b22 | BaseEnv, Actor, register_env, UniformPlacementSampler | Already installed; provides all env APIs |
| SAPIEN | (bundled with ManiSkill3) | Physics engine, Pose types, scene management | Bundled; underlies all ManiSkill3 environments |
| torch | (bundled) | Batched tensor ops for poses, evaluation | Required by ManiSkill3's batched env interface |
| gymnasium | (bundled) | Env registration, gym.make interface | Standard RL env interface |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 1.26.4 | Array operations for non-batched code | Already pinned <2.0 for mplib compat |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| BaseEnv (direct) | StackCubeEnv (inherit) | StackCubeEnv hardcodes 2-cube assumptions in every method; would need to override everything anyway |
| `self.cubes` list | Dict of named actors | List enables loop-based spawn/eval; dict adds key management overhead with no benefit |

**Installation:**
```bash
# No new packages needed
pip install -e .
```

## Architecture Patterns

### Recommended Project Structure
```
ps_bed/
    envs/
        __init__.py              # Add import for stack_n_cube registration
        stack_cube_distractor.py # UNCHANGED
        stack_n_cube.py          # NEW: parameterized N-cube environment
```

### Pattern 1: Parameterized Environment via Constructor Kwargs

**What:** Accept `num_cubes` as an `__init__` kwarg, store it before calling `super().__init__()`, use it in `_load_scene` to build N cubes dynamically.

**When to use:** Always -- this is how ManiSkill3 environments accept custom parameters. Verified that `register_env()` forwards JSON-serializable kwargs through `gym.register()` to the env constructor (source: `mani_skill/utils/registration.py` lines 233-256).

**Example:**
```python
# Source: verified against mani_skill/utils/registration.py and
# mani_skill/envs/tasks/tabletop/stack_cube.py

@register_env("StackNCube-v1", max_episode_steps=250)
class StackNCubeEnv(BaseEnv):
    SUPPORTED_ROBOTS = ["panda_wristcam", "panda", "fetch"]
    agent: Union[Panda, Fetch]

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
```

**Confidence:** HIGH -- verified in ManiSkill3 source (`registration.py`) and matches existing patterns (`PickClutterYCB` with `episode_json` kwarg).

### Pattern 2: Loop-Based Cube Spawning in _load_scene

**What:** Build N cubes in a loop using `actors.build_cube()`, store references in `self.cubes` list. Assign distinct colors for visual differentiation.

**When to use:** Always for variable-count object environments.

**Example:**
```python
# Source: verified against mani_skill/utils/building/actors/common.py
# and mani_skill/envs/tasks/tabletop/stack_pyramid.py

CUBE_COLORS = [
    [1, 0, 0, 1],    # red
    [0, 1, 0, 1],    # green
    [0, 0, 1, 1],    # blue
    [1, 1, 0, 1],    # yellow
    [1, 0, 1, 1],    # magenta
    [0, 1, 1, 1],    # cyan
]

def _load_scene(self, options: dict):
    self.cube_half_size = common.to_tensor([0.02] * 3, device=self.device)
    self.table_scene = TableSceneBuilder(
        env=self, robot_init_qpos_noise=self.robot_init_qpos_noise
    )
    self.table_scene.build()

    self.cubes = []
    for i in range(self.num_cubes):
        cube = actors.build_cube(
            self.scene,
            half_size=0.02,
            color=CUBE_COLORS[i % len(CUBE_COLORS)],
            name=f"cube_{i}",
            initial_pose=sapien.Pose(p=[i * 0.1, 0, 0.1]),
        )
        self.cubes.append(cube)
```

**Confidence:** HIGH -- `actors.build_cube()` is used identically in `StackCubeEnv` and `StackPyramidEnv`.

### Pattern 3: Sequential UniformPlacementSampler for N Cubes

**What:** Use `UniformPlacementSampler` with one `sample()` call per cube. The sampler maintains internal state (`fixture_positions`, `fixtures_radii`) and automatically avoids previously sampled positions.

**When to use:** For collision-free random placement of multiple objects.

**Example:**
```python
# Source: verified against mani_skill/envs/utils/randomization/samplers.py

def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
    with torch.device(self.device):
        b = len(env_idx)
        self.table_scene.initialize(env_idx)

        xyz = torch.zeros((b, 3))
        xyz[:, 2] = 0.02  # half cube height above table

        region = [[-0.1, -0.2], [0.1, 0.2]]
        sampler = randomization.UniformPlacementSampler(
            bounds=region, batch_size=b, device=self.device
        )
        radius = torch.linalg.norm(
            torch.tensor([0.02, 0.02])
        ) + 0.001

        for i, cube in enumerate(self.cubes):
            cube_xy = sampler.sample(radius, 100, verbose=False)
            xyz[:, :2] = cube_xy
            qs = randomization.random_quaternions(
                b, lock_x=True, lock_y=True, lock_z=False
            )
            cube.set_pose(Pose.create_from_pq(
                p=xyz.clone(), q=qs
            ))
```

**Confidence:** HIGH -- empirically verified that the sampler successfully places 6 cubes in the standard region `[-0.1,0.1]x[-0.2,0.2]` in 100/100 trials.

**Important note on StackCubeEnv's xy offset pattern:** The existing `StackCubeEnv._initialize_episode` creates a random `xy` offset: `xy = torch.rand((b, 2)) * 0.2 - 0.1` and adds it to each sampled position (`cubeA_xy = xy + sampler.sample(...)`). This shifts all cubes as a group, centering them around a random point. The new env should replicate this pattern for consistency. However, this offset is added BEFORE the sampler's collision-aware sampling, so the sampled positions are relative to the sampler's bounds, not the offset origin. The result is that cubes end up within `region + xy_offset`, which could extend slightly outside the original region. For N=6, dropping the offset (or using a smaller one) avoids cubes spawning too close to table edges.

### Pattern 4: N-Pair Stacking Evaluation

**What:** Check all N-1 adjacent pairs (cube[i] on cube[i-1]) for XY alignment, Z height, static velocity, and release. All pairs must pass for success.

**When to use:** For any N-cube vertical stacking evaluation.

**Example:**
```python
# Source: derived from mani_skill/envs/tasks/tabletop/stack_cube.py evaluate()
# and mani_skill/envs/tasks/tabletop/stack_pyramid.py evaluate()

def evaluate(self):
    pos = [cube.pose.p for cube in self.cubes]  # list of (B, 3) tensors

    all_pairs_stacked = torch.ones(
        self.num_envs, device=self.device, dtype=torch.bool
    )
    all_static = torch.ones(
        self.num_envs, device=self.device, dtype=torch.bool
    )
    any_grasped = torch.zeros(
        self.num_envs, device=self.device, dtype=torch.bool
    )

    half_size = self.cube_half_size
    xy_thresh = torch.linalg.norm(half_size[:2]) + 0.005
    z_target = half_size[2] * 2  # full cube height

    for i in range(1, self.num_cubes):
        offset = pos[i] - pos[i - 1]

        xy_ok = torch.linalg.norm(
            offset[..., :2], axis=1
        ) <= xy_thresh
        z_ok = torch.abs(offset[..., 2] - z_target) <= 0.005
        pair_stacked = xy_ok & z_ok

        all_pairs_stacked &= pair_stacked
        all_static &= self.cubes[i].is_static(
            lin_thresh=1e-2, ang_thresh=0.5
        )
        any_grasped |= self.agent.is_grasping(self.cubes[i])

    # Also check bottom cube is static and not grasped
    all_static &= self.cubes[0].is_static(
        lin_thresh=1e-2, ang_thresh=0.5
    )
    any_grasped |= self.agent.is_grasping(self.cubes[0])

    success = all_pairs_stacked & all_static & (~any_grasped)
    return {
        "all_pairs_stacked": all_pairs_stacked,
        "all_static": all_static,
        "any_grasped": any_grasped,
        "success": success.bool(),
    }
```

**Confidence:** HIGH -- logic directly extends `StackCubeEnv.evaluate()` pattern. The `is_static` thresholds (`lin_thresh=1e-2, ang_thresh=0.5`) match the upstream values. The angular velocity threshold of 0.5 is deliberately relaxed from the default 0.1 because ManiSkill's own comment says "GPU sim can be fast but unstable. Angular velocity is rather high despite it not really rotating."

### Pattern 5: Physics Config Override for Stable Stacking

**What:** Override `_default_sim_config` property to increase solver iterations for physics stability with tall stacks.

**When to use:** For any environment with 3+ stacked objects.

**Example:**
```python
# Source: verified against mani_skill/utils/structs/types.py (SceneConfig defaults)
# and mani_skill/envs/sapien_env.py (_default_sim_config usage)

@property
def _default_sim_config(self):
    return SimConfig(
        scene_config=SceneConfig(
            solver_position_iterations=20,
            solver_velocity_iterations=4,
        )
    )
```

**Confidence:** HIGH -- The `_default_sim_config` property pattern is used by `TwoRobotStackCube` in the ManiSkill3 codebase. The ManiSkill source code comment in `types.py` says: "solver iterations 15 is recommended to balance speed and accuracy. If stable grasps are necessary >= 20 is preferred." Defaults are `solver_position_iterations=15, solver_velocity_iterations=1`.

### Anti-Patterns to Avoid

- **Inheriting from StackCubeEnv:** StackCubeEnv hardcodes `self.cubeA`/`self.cubeB` in `_load_scene`, `_initialize_episode`, `evaluate`, `_get_obs_extra`, and `compute_dense_reward`. Every method must be overridden, making inheritance pointless and confusing. Extend `BaseEnv` directly.

- **Variable max_episode_steps at runtime:** ManiSkill3's `TimeLimitWrapper` reads `max_episode_steps` at creation time. It cannot be changed after `gym.make()`. Set a generous default in `register_env()` (250 steps handles up to N=6). Override per-instantiation via `gym.make("StackNCube-v1", max_episode_steps=N*50)`.

- **Dynamic actor count between episodes:** ManiSkill3 loads actors once in `_load_scene()` during reconfiguration. Actors cannot be added or removed between resets. The cube count must be fixed at construction time (via `num_cubes` kwarg).

- **Forgetting `.clone()` on pose tensors:** When reusing the `xyz` tensor in a loop, the last cube's pose would share memory with all previous cubes. Always use `xyz.clone()` before passing to `set_pose()`. The existing `StackCubeEnv` uses `.clone()` for the first cube and passes without clone for the last one -- follow the same pattern (clone for all but the last).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Collision-free placement | Custom rejection sampling loop | `UniformPlacementSampler.sample()` | Sampler is batched, GPU-compatible, maintains fixture state automatically |
| Cube spawning | Manual SAPIEN actor builder setup | `actors.build_cube()` | Handles collision + visual geometry setup in one call |
| Gym registration | Manual `gym.register()` call | `@register_env()` decorator | Handles both ManiSkill and gym registries, adds TimeLimitWrapper |
| Static check | Manual velocity threshold comparison | `Actor.is_static(lin_thresh, ang_thresh)` | Returns batched bool tensor, handles both GPU and CPU sim |
| Grasp check | Manual contact force analysis | `agent.is_grasping(actor)` | Panda-specific implementation handles finger contact detection |
| Random rotations | Manual quaternion generation | `randomization.random_quaternions()` | Batched, supports axis locking |
| Batched poses | Manual tensor manipulation | `Pose.create_from_pq(p=..., q=...)` | ManiSkill3's pose type with correct batching semantics |

**Key insight:** ManiSkill3 provides all the building blocks. The N-cube environment is a composition problem, not a building-from-scratch problem.

## Common Pitfalls

### Pitfall 1: Physics Instability in Tall Stacks (N >= 4)

**What goes wrong:** After stacking 4+ cubes, the tower wobbles or topples despite geometrically correct placement. Angular velocity exceeds the `is_static` threshold even though the cubes appear stationary.

**Why it happens:** PhysX's iterative constraint solver (default 15 position iterations, 1 velocity iteration) does not fully converge for deep constraint chains. A 5-cube stack has 4 resting contact pairs, each requiring the solver to propagate forces through the chain. The ManiSkill source acknowledges this: "GPU sim can be fast but unstable."

**How to avoid:** Override `_default_sim_config` with `solver_position_iterations=20` and `solver_velocity_iterations=4`. These values are within the range recommended by ManiSkill documentation. If stability is still an issue for N=6, increase to 25/5.

**Warning signs:** `evaluate()` returns `all_static=False` even though cubes look stationary in video. Success rate drops non-linearly between N=3 and N=4.

### Pitfall 2: Placement Region Too Small for N=6

**What goes wrong:** The `UniformPlacementSampler` exhausts max_trials without finding collision-free positions for all cubes, resulting in overlapping cube positions.

**Why it happens:** The sampler does NOT raise an error when it fails -- it silently returns the last sampled position, which may overlap with existing fixtures. With 6 cubes and the original `[-0.1, -0.2]` to `[0.1, 0.2]` region, sampling failures are rare but not impossible, especially when combined with the `xy` group offset.

**How to avoid:** Keep the standard region but drop or reduce the `xy` group offset. Empirical testing showed 100/100 success rate with 6 cubes in the standard region. Monitor `verbose=True` on the first sample to detect sampling pressure.

**Warning signs:** Cubes overlapping at episode start. Cubes flying apart at episode start (physics resolving penetration).

### Pitfall 3: Forgetting to Import the Module for Registration

**What goes wrong:** `gym.make("StackNCube-v1")` raises `KeyError: 'Env StackNCube-v1 not found in registry'`.

**Why it happens:** ManiSkill3's `@register_env` decorator runs at import time. If `ps_bed/envs/stack_n_cube.py` is never imported, the environment is never registered. The existing project handles this via `ps_bed/envs/__init__.py` which imports `stack_cube_distractor`.

**How to avoid:** Add `import ps_bed.envs.stack_n_cube  # noqa: F401` to `ps_bed/envs/__init__.py`.

**Warning signs:** Environment works when running the file directly but fails when invoked through `gym.make()`.

### Pitfall 4: max_episode_steps Mismatch

**What goes wrong:** The planner successfully stacks N-1 cubes but the episode truncates before completion because the step budget is too small.

**Why it happens:** `register_env` bakes in `max_episode_steps`. If set too low (e.g., 50 from StackCube), N=5 stacking needs ~200 steps. The `TimeLimitWrapper` truncates the episode before the skill finishes.

**How to avoid:** Set `max_episode_steps=250` in the `@register_env` decorator. This accommodates up to N=6 (each pick-place cycle takes ~40-50 steps, so 5 cycles * 50 steps = 250). For specific N values, override at `gym.make()` time: `gym.make("StackNCube-v1", max_episode_steps=num_cubes * 50)`.

**Warning signs:** Skill reports success=False but video shows cubes being actively stacked when episode ends. `truncated=True` in step output.

### Pitfall 5: Unbatched Tensors in _initialize_episode

**What goes wrong:** `set_pose` crashes or places cubes at wrong positions when `env_idx` has unexpected batch size.

**Why it happens:** ManiSkill3 calls `_initialize_episode(env_idx, options)` where `env_idx` can be a subset of environment indices (for partial resets in GPU sim). All pose tensors must have batch dimension `len(env_idx)`, not hardcoded to 1.

**How to avoid:** Always use `b = len(env_idx)` as the batch size and construct tensors with shape `(b, ...)`. The loop-based spawning pattern naturally handles this since `sampler.sample()` returns `(b, 2)` tensors.

**Warning signs:** Works with `num_envs=1` but crashes with `num_envs>1`. Works on first reset but crashes on partial resets in GPU sim.

### Pitfall 6: Evaluation Ordering Assumption

**What goes wrong:** `evaluate()` returns `success=True` when cubes are stacked in the wrong order (e.g., cube[2] on cube[0], skipping cube[1]).

**Why it happens:** If the evaluation only checks pairwise stacking without ordering, any arrangement where cubes happen to be vertically aligned could pass.

**How to avoid:** The evaluation must check CONSECUTIVE pairs: cube[1] on cube[0], cube[2] on cube[1], ..., cube[N-1] on cube[N-2]. The expected z-offset between each pair is exactly `cube_half_size[2] * 2` (one full cube height). This means cube[0] is on the table, cube[1] is one cube height above, etc. The ordering is implicit in the z-height check combined with the sequential pairing.

**Warning signs:** Success rate is suspiciously high for random policies on N=3+.

## Code Examples

### Complete _load_scene with Backward-Compatible Aliases

```python
# Source: pattern from mani_skill/envs/tasks/tabletop/stack_cube.py
# Extended for N cubes

CUBE_COLORS = [
    [1, 0, 0, 1],    # red
    [0, 1, 0, 1],    # green
    [0, 0, 1, 1],    # blue
    [1, 1, 0, 1],    # yellow
    [1, 0, 1, 1],    # magenta
    [0, 1, 1, 1],    # cyan
]

def _load_scene(self, options: dict):
    self.cube_half_size = common.to_tensor([0.02] * 3, device=self.device)
    self.table_scene = TableSceneBuilder(
        env=self, robot_init_qpos_noise=self.robot_init_qpos_noise
    )
    self.table_scene.build()

    self.cubes = []
    for i in range(self.num_cubes):
        cube = actors.build_cube(
            self.scene,
            half_size=0.02,
            color=CUBE_COLORS[i % len(CUBE_COLORS)],
            name=f"cube_{i}",
            initial_pose=sapien.Pose(p=[i * 0.1, 0, 0.1]),
        )
        self.cubes.append(cube)
```

### Complete _get_obs_extra for N Cubes

```python
# Source: pattern from mani_skill/envs/tasks/tabletop/stack_cube.py
# and mani_skill/envs/tasks/tabletop/stack_pyramid.py

def _get_obs_extra(self, info: dict):
    obs = dict(tcp_pose=self.agent.tcp.pose.raw_pose)
    if "state" in self.obs_mode:
        for i, cube in enumerate(self.cubes):
            obs[f"cube_{i}_pose"] = cube.pose.raw_pose
            obs[f"tcp_to_cube_{i}_pos"] = (
                cube.pose.p - self.agent.tcp.pose.p
            )
        # Pairwise distances between adjacent cubes
        for i in range(1, self.num_cubes):
            obs[f"cube_{i-1}_to_cube_{i}_pos"] = (
                self.cubes[i].pose.p - self.cubes[i-1].pose.p
            )
    return obs
```

### Sparse Reward for N-Cube Stacking

```python
# Source: pattern from mani_skill/envs/tasks/tabletop/stack_pyramid.py
# (which only supports sparse reward)

SUPPORTED_REWARD_MODES = ["sparse", "none"]

def compute_sparse_reward(self, obs, action, info):
    return info["success"].float()
```

**Note:** Dense reward for N-cube stacking is complex (reward shaping for sequential multi-step tasks). The upstream `StackPyramidEnv` only supports sparse reward. For Phase 1, supporting only sparse reward is sufficient since the motion planner does not use reward signals. Dense reward can be added in a future phase if needed for RL training.

### Environment Registration and Import

```python
# In ps_bed/envs/stack_n_cube.py:
from mani_skill.utils.registration import register_env

@register_env("StackNCube-v1", max_episode_steps=250)
class StackNCubeEnv(BaseEnv):
    ...

# In ps_bed/envs/__init__.py:
import ps_bed.envs.stack_cube_distractor  # noqa: F401
import ps_bed.envs.stack_n_cube  # noqa: F401
```

### Instantiation (How Users Create the Environment)

```python
import gymnasium as gym
import ps_bed.envs  # triggers registration

# Default: 3 cubes, 250 max steps
env = gym.make("StackNCube-v1")

# Custom: 5 cubes
env = gym.make("StackNCube-v1", num_cubes=5)

# Custom: 5 cubes with scaled step budget
env = gym.make("StackNCube-v1", num_cubes=5, max_episode_steps=250)

# With rendering for motion planner
env = gym.make(
    "StackNCube-v1",
    num_cubes=4,
    obs_mode="state",
    control_mode="pd_joint_pos",
    num_envs=1,
    sim_backend="cpu",
    render_mode="rgb_array",
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inherit StackCubeEnv | Extend BaseEnv directly | Prior research decision | Must copy table/camera/agent setup from StackCubeEnv |
| Hardcoded cubeA/cubeB | `self.cubes` list | This phase | Enables variable N |
| `max_episode_steps=50` | `max_episode_steps=250` default | This phase | Prevents truncation for N=6 |
| solver_position_iterations=15 | 20+ for stacking | This phase | Physics stability for tall stacks |

**Deprecated/outdated:**
- The `StackCubeDistractorEnv` (inheriting StackCubeEnv) is kept for backward compatibility but is NOT the pattern to follow for N-cube work.

## Open Questions

1. **Exact solver iterations needed for N=6 stability**
   - What we know: Default is 15. ManiSkill recommends >= 20 for stable grasps. StackPyramid (3 cubes) uses the default 15.
   - What's unclear: Whether 20 is sufficient for 6-cube stacks or if 25+ is needed.
   - Recommendation: Start with 20. Add a simple scripted verification (stack 6 cubes programmatically without the robot and check stability) during implementation. Adjust if needed.

2. **Whether to keep the xy group offset in placement**
   - What we know: StackCubeEnv applies `xy = torch.rand((b, 2)) * 0.2 - 0.1` as an offset to all cubes. This shifts the group randomly, adding variety.
   - What's unclear: With 6 cubes, this offset could push cubes near table edges.
   - Recommendation: Keep a reduced offset (e.g., `0.1 - 0.05` instead of `0.2 - 0.1`) or remove it entirely for N >= 5. The sampler provides sufficient randomness on its own.

3. **Whether dense reward is needed for Phase 1**
   - What we know: StackPyramidEnv only supports sparse reward. The motion planner does not use reward signals.
   - What's unclear: Whether downstream RL experiments will need dense reward.
   - Recommendation: Support only sparse reward in Phase 1 (`SUPPORTED_REWARD_MODES = ["sparse", "none"]`). Dense reward for N-cube stacking is a significant design effort (progressive reaching + grasping + stacking reward for each cube) and is not needed for motion-planned demos.

4. **Observation space structure for variable N**
   - What we know: The observation dict will have variable keys depending on N (`cube_0_pose` through `cube_{N-1}_pose`).
   - What's unclear: Whether downstream RL code needs a fixed-size observation space.
   - Recommendation: Use per-cube named keys in the observation dict (e.g., `cube_0_pose`, `cube_1_pose`). This is the simplest approach and matches the dict-based `obs_mode="state_dict"` pattern. If fixed-size observations are later needed for RL, pad to `max_cubes=6` with zeros.

## Sources

### Primary (HIGH confidence)
- ManiSkill3 `StackCubeEnv` source: `/common/users/dm1487/envs/maniskill/lib/python3.11/site-packages/mani_skill/envs/tasks/tabletop/stack_cube.py` - _load_scene, _initialize_episode, evaluate patterns
- ManiSkill3 `StackPyramidEnv` source: same path `stack_pyramid.py` - 3-cube environment with sparse-only reward, sequential evaluation
- ManiSkill3 `BaseEnv` source: `sapien_env.py` - __init__ signature, _default_sim_config property
- ManiSkill3 `register_env` source: `registration.py` - kwargs forwarding, TimeLimitWrapper behavior
- ManiSkill3 `UniformPlacementSampler` source: `randomization/samplers.py` - collision-aware sequential sampling
- ManiSkill3 `actors.build_cube` source: `building/actors/common.py` - cube construction API
- ManiSkill3 `SceneConfig` source: `structs/types.py` - solver_position_iterations default (15) and recommendation (>= 20)
- ManiSkill3 `Actor.is_static` source: `structs/actor.py` - velocity threshold interface
- Existing ps_bed codebase: all files in `ps_bed/` - current patterns and conventions
- Empirical test: UniformPlacementSampler with N=6 in standard region - 100/100 success

### Secondary (MEDIUM confidence)
- Prior project research: `.planning/research/ARCHITECTURE.md` - validated architecture patterns
- Prior project research: `.planning/research/STACK.md` - validated stack decisions
- Prior project research: `.planning/research/PITFALLS.md` - validated pitfall catalog
- Prior project research: `.planning/research/SUMMARY.md` - validated summary and gaps

### Tertiary (LOW confidence)
- PhysX solver iteration tuning for N=6 stacks: no empirical data specific to this cube size and stack height. Recommendation based on ManiSkill docs and general PhysX guidance.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all APIs verified against installed source
- Architecture: HIGH - patterns verified against multiple ManiSkill3 reference environments
- Pitfalls: HIGH - grounded in source code analysis with specific line references
- Evaluation logic: HIGH - directly extends the verified StackCubeEnv.evaluate() pattern
- Physics tuning: MEDIUM - specific solver iteration values need empirical validation

**Research date:** 2026-02-13
**Valid until:** Stable -- ManiSkill3 3.0.0b22 is pinned. Valid until ManiSkill3 version changes.
