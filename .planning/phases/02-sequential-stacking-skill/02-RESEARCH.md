# Phase 2: Sequential Stacking Skill - Research

**Researched:** 2026-02-13
**Domain:** Motion planning skill composition, mplib 0.2.x grasp primitives, dynamic target computation, error propagation
**Confidence:** HIGH

## Summary

Phase 2 transforms the monolithic `PickPlaceSkill.solve()` into a sequential N-cube stacking skill by extracting reusable grasp primitives and composing them in an N-1 pick-place loop. The core technical challenge is computing the dynamic stack-top position after each placement (the target for cube `i` is the actual pose of cube `i-1` plus one cube height, read from the physics engine at runtime) and implementing clean abort semantics when any motion plan or grasp fails.

The existing `PickPlaceSkill` in `ps_bed/skills/pick_place.py` already contains all the low-level motion planning primitives needed: `_setup_planner()`, `_move_to_pose_with_screw()`, `_actuate_gripper()`, `_follow_path()`. These methods work correctly with mplib 0.2.x and handle the SAPIEN batched tensor conventions. The refactoring task is to extract the grasp-lift-place sequence into a reusable method that operates on any cube actor and any target position, then call it in a loop.

A key design decision is whether to create a new `SequentialStackSkill` class or extend `PickPlaceSkill`. The recommendation is to create a new class that reuses the same low-level primitives (either by inheritance or composition). The existing `PickPlaceSkill` must remain backward-compatible with `StackCube-v1` (which uses `cubeA`/`cubeB` attributes, not `cubes` list). The new skill targets `StackNCube-v1` (which uses `self.cubes` list with `cube_0` through `cube_{N-1}`).

**Primary recommendation:** Create `ps_bed/skills/stack_n.py` with a `StackNSkill` class that inherits from `PickPlaceSkill` (reusing `_setup_planner`, `_move_to_pose_with_screw`, `_actuate_gripper`, `_follow_path`) and adds a `solve()` method that loops N-1 times, each iteration grasping `cubes[i+1]` and placing it on the current stack top read from `cubes[i].pose.p`. Abort immediately on any plan failure or grasp verification failure.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mplib | 0.2.1 | Motion planning (plan_screw, plan_pose) | Already installed and working; all primitives tested |
| ManiSkill3 | 3.0.0b22 | Environment, Actor, agent APIs (is_grasping, tcp, build_grasp_pose) | Phase 1 environment; provides all env-side APIs |
| SAPIEN | (bundled) | Pose arithmetic, physics state access | Bundled with ManiSkill3; Pose multiplication for target computation |
| numpy | 1.26.4 | Array ops for mplib interface | Pinned <2.0 for mplib compatibility |
| transforms3d | (installed) | euler2quat for grasp rotation search | Already used in existing PickPlaceSkill |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| trimesh | (bundled) | OBB computation via get_actor_obb | Used to compute grasp geometry from cube mesh |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Inherit PickPlaceSkill | Standalone class with duplicated methods | Inheritance reuses tested primitives; standalone risks drift |
| plan_screw only | plan_screw + plan_pose fallback | plan_pose handles obstacles better but is deferred to v2 per prior decision |
| OBB-based grasp | Hardcoded cube center + approaching | OBB is more robust to pose uncertainty; already implemented |

**Installation:**
```bash
# No new packages needed
pip install -e .
```

## Architecture Patterns

### Recommended Project Structure
```
ps_bed/
    skills/
        __init__.py          # UNCHANGED
        pick_place.py        # PRESERVED (backward compat with StackCube-v1)
        stack_n.py           # NEW: N-cube sequential stacking skill
```

### Pattern 1: Inheritance for Primitive Reuse

**What:** `StackNSkill` inherits from `PickPlaceSkill` to reuse `_setup_planner()`, `_move_to_pose_with_screw()`, `_actuate_gripper()`, `_follow_path()`, and the `_sapien_to_mplib_pose()` module-level helper.

**When to use:** When the new skill uses identical low-level motion planning primitives but different high-level orchestration.

**Why this works:** All four private methods in `PickPlaceSkill` are stateless (they take `env`, `planner`, and pose arguments). They don't depend on any `StackCube-v1`-specific attributes. The only `StackCube-v1`-specific code is in `solve()`, which references `raw.cubeA`, `raw.cubeB`. The new `solve()` replaces this with a loop over `raw.cubes`.

**Example:**
```python
# Source: existing ps_bed/skills/pick_place.py analysis
from ps_bed.skills.pick_place import PickPlaceSkill

class StackNSkill(PickPlaceSkill):
    """Sequential N-cube stacking skill for StackNCube-v1."""

    def solve(self, env, seed=None):
        """Stack all N cubes into a tower. Returns (obs, rew, term, trunc, info)."""
        # Uses inherited: _setup_planner, _move_to_pose_with_screw,
        #                 _actuate_gripper, _follow_path
        ...
```

**Confidence:** HIGH -- verified that all four inherited methods are stateless and environment-agnostic.

### Pattern 2: Single Pick-Place-on-Stack Operation

**What:** Extract the grasp-lift-place sequence into a method `_pick_and_stack(env, planner, cube_to_pick, target_cube)` that:
1. Computes grasp pose from the cube's OBB
2. Searches for collision-free grasp orientation
3. Reaches, grasps, lifts the cube
4. Computes place target from `target_cube.pose.p + [0, 0, cube_height]`
5. Moves to align position above target, then releases

**When to use:** Each iteration of the N-1 stacking loop.

**Key detail -- dynamic stack-top computation:** The place target is NOT computed from cube indices or fixed heights. It is computed from the ACTUAL physics-engine pose of the top cube in the current stack at the moment of placement:

```python
# target_cube is cubes[i] -- the current top of the stack
# cube_height = cube_half_size[2] * 2 = 0.04 (for 0.02 half-size cubes)
goal_pose = target_cube.pose * sapien.Pose([0, 0, cube_height])
```

This handles any settling, drift, or imprecision from previous placements.

**Example:**
```python
def _pick_and_stack(self, env, planner, cube_to_pick, target_cube):
    """Pick cube_to_pick and place it on top of target_cube.

    Returns (obs, rew, term, trunc, info) on success, or None on failure.
    """
    raw = env.unwrapped
    cube_height = (raw.cube_half_size[2] * 2).item()

    # 1. Compute grasp from OBB
    obb = get_actor_obb(cube_to_pick)
    approaching = np.array([0, 0, -1])
    target_closing = (
        raw.agent.tcp.pose.to_transformation_matrix()[0, :3, 1].cpu().numpy()
    )
    grasp_info = compute_grasp_info_by_obb(
        obb, approaching=approaching,
        target_closing=target_closing,
        depth=self.FINGER_LENGTH,
    )
    closing, center = grasp_info["closing"], grasp_info["center"]
    grasp_pose = raw.agent.build_grasp_pose(approaching, closing, center)

    # 2. Search valid orientation
    angles = np.arange(0, np.pi * 2 / 3, np.pi / 2)
    angles = np.repeat(angles, 2)
    angles[1::2] *= -1
    for angle in angles:
        delta_pose = sapien.Pose(q=euler2quat(0, 0, angle))
        candidate = grasp_pose * delta_pose
        res = self._move_to_pose_with_screw(
            env, planner, candidate, self.GRIPPER_OPEN, dry_run=True
        )
        if res != -1:
            grasp_pose = candidate
            break
    else:
        return None  # ABORT: no valid grasp orientation

    # 3. Reach
    reach_pose = grasp_pose * sapien.Pose([0, 0, -0.05])
    res = self._move_to_pose_with_screw(
        env, planner, reach_pose, self.GRIPPER_OPEN
    )
    if res == -1:
        return None  # ABORT: reach plan failed

    # 4. Grasp
    res = self._move_to_pose_with_screw(
        env, planner, grasp_pose, self.GRIPPER_OPEN
    )
    if res == -1:
        return None  # ABORT: grasp approach failed
    self._actuate_gripper(env, planner, self.GRIPPER_CLOSED)

    # 5. Lift
    lift_pose = sapien.Pose([0, 0, 0.1]) * grasp_pose
    res = self._move_to_pose_with_screw(
        env, planner, lift_pose, self.GRIPPER_CLOSED
    )
    if res == -1:
        return None  # ABORT: lift plan failed

    # 6. Place on stack (DYNAMIC target)
    goal_pose = target_cube.pose * sapien.Pose([0, 0, cube_height])
    offset = (goal_pose.p - cube_to_pick.pose.p).cpu().numpy()[0]
    align_pose = sapien.Pose(lift_pose.p + offset, lift_pose.q)
    res = self._move_to_pose_with_screw(
        env, planner, align_pose, self.GRIPPER_CLOSED
    )
    if res == -1:
        return None  # ABORT: align plan failed

    # 7. Release
    return self._actuate_gripper(env, planner, self.GRIPPER_OPEN)
```

**Confidence:** HIGH -- pattern directly extends the working `PickPlaceSkill.solve()` with the same SAPIEN pose arithmetic verified in Phase 1.

### Pattern 3: N-1 Loop with Abort Semantics

**What:** The top-level `solve()` method loops N-1 times. In each iteration, it picks `cubes[i+1]` and places it on `cubes[i]` (the current stack top). If any step returns `None` (failure), the method returns immediately with a failure indication.

**When to use:** Always for the N-cube stacking skill.

**Stacking order:** The StackNCube-v1 evaluate() checks that cube[i] is directly on cube[i-1] for all i in [1, N-1]. So cube_0 stays on the table, cube_1 goes on cube_0, cube_2 goes on cube_1, etc. The loop iterates i from 0 to N-2, picking cubes[i+1] and placing on cubes[i].

**Example:**
```python
def solve(self, env, seed=None):
    env.reset(seed=seed)
    assert env.unwrapped.control_mode in ["pd_joint_pos", "pd_joint_pos_vel"]

    planner = self._setup_planner(env)
    raw = env.unwrapped
    cubes = raw.cubes
    n = len(cubes)

    last_result = None
    for i in range(n - 1):
        cube_to_pick = cubes[i + 1]
        target_cube = cubes[i]
        result = self._pick_and_stack(env, planner, cube_to_pick, target_cube)
        if result is None:
            print(f"Stacking failed at step {i+1}/{n-1}: "
                  f"picking cube_{i+1} onto cube_{i}")
            # Return last valid env state with success=False
            obs = env.unwrapped._get_obs(env.unwrapped.evaluate())
            info = env.unwrapped.evaluate()
            return obs, 0.0, False, False, info
        last_result = result

    return last_result
```

**Confidence:** HIGH -- stacking order verified against StackNCubeEnv.evaluate() which checks `pos[i] - pos[i-1]` for all i.

### Pattern 4: Grasp Verification via is_grasping

**What:** After closing the gripper, verify the cube is actually grasped by calling `agent.is_grasping(cube)`. If the grasp failed (cube slipped, was not reached), abort immediately.

**When to use:** After every gripper close operation, before attempting to lift.

**Example:**
```python
# After closing gripper
self._actuate_gripper(env, planner, self.GRIPPER_CLOSED)

# Verify grasp
is_holding = raw.agent.is_grasping(cube_to_pick)
if isinstance(is_holding, torch.Tensor):
    is_holding = bool(is_holding.item())
if not is_holding:
    print(f"Grasp verification failed for cube_{i+1}")
    return None  # ABORT
```

**Confidence:** HIGH -- `agent.is_grasping(actor)` verified in Panda class (uses pairwise contact forces between finger links and the actor, returns batched bool tensor).

### Anti-Patterns to Avoid

- **Fixed-height placement targets:** Do NOT compute placement height as `i * cube_height` from the table. Instead, read the actual pose of the current stack top from the physics engine. This handles cumulative settling and imprecise placements.

- **Modifying PickPlaceSkill.solve() in place:** The existing `solve()` method must remain backward-compatible with `StackCube-v1`. Create a NEW class with a NEW `solve()` method.

- **Skipping the OBB recomputation per cube:** Each cube's OBB must be computed fresh at grasp time because the cube may have been bumped or shifted by previous operations. Do NOT cache OBBs from episode start.

- **Continuing after plan_screw failure:** The current `_move_to_pose_with_screw` returns -1 on failure but the caller in `PickPlaceSkill.solve()` ignores this and continues. The new skill MUST check every return value and abort on failure.

- **Ignoring the gripper state between operations:** After placing cube i, the gripper must be fully open before computing the grasp for cube i+1. The `_actuate_gripper` call at the end of each pick-place handles this, but the next iteration must start with `GRIPPER_OPEN` state.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Grasp pose computation | Manual geometric approach/closing calculation | `get_actor_obb()` + `compute_grasp_info_by_obb()` + `build_grasp_pose()` | Handles arbitrary cube orientations, OBB-based closing direction |
| Motion planning | Custom IK solver or waypoint interpolation | `mplib.Planner.plan_screw()` | Handles joint limits, velocity limits, collision with self |
| Grasp verification | Manual finger distance check | `agent.is_grasping(actor)` | Uses contact forces + angle, handles both CPU and GPU sim |
| Pose arithmetic | Manual translation/rotation math | `sapien.Pose` multiplication | Correct SE(3) composition, handles quaternions properly |
| Batched tensor to scalar | Manual indexing | `.cpu().numpy()[0]` or `.item()` | Handles both GPU and CPU backends, SAPIEN batching conventions |

**Key insight:** The low-level motion planning primitives in the existing `PickPlaceSkill` are already battle-tested with mplib 0.2.x. The Phase 2 work is pure composition -- looping and error handling around proven building blocks.

## Common Pitfalls

### Pitfall 1: plan_screw Failure with Existing Stack as Obstacle

**What goes wrong:** `plan_screw()` fails to find a path when the gripper needs to reach a cube near an already-built stack, because the stack is a collision obstacle for the robot arm (even though mplib does not model the cubes as environment obstacles).

**Why it happens:** mplib's `plan_screw()` uses screw motion (straight-line in task space), which works for unobstructed paths but cannot route around obstacles. As the stack grows taller (N >= 3), the gripper approach path may pass through the stack volume. Note: mplib's self-collision checking only considers robot links, NOT environment objects.

**How to avoid:** For Phase 2, this is an acknowledged limitation (collision-aware planning deferred to v2 per prior decision). The 0.05m reach-back offset in the approach phase helps avoid some collisions. For N=3, empirical success rate should be acceptable. For N > 3, success rate will degrade.

**Warning signs:** `plan_screw` returns "FAILURE" status on cubes close to the stack. Success rate drops sharply at N=4+.

### Pitfall 2: Stack Toppling During Subsequent Grasps

**What goes wrong:** While grasping cube i+2, the robot arm or gripper bumps the existing stack (cubes 0 through i+1), causing it to topple.

**Why it happens:** mplib does not know about the cubes as obstacles, so planned paths may sweep through the stack volume. Even without direct collision, vibrations from nearby motion can destabilize a tall stack.

**How to avoid:** The lifted height (0.1m above grasp pose) provides clearance above a 3-cube stack (3 * 0.04 = 0.12m total height, plus 0.02m table offset = 0.14m). For tall stacks, may need to increase lift height. The 20-iteration physics solver from Phase 1 helps with settling stability.

**Warning signs:** Video shows cubes wobbling or falling during robot motion near the stack.

### Pitfall 3: _move_to_pose_with_screw Return Value Confusion

**What goes wrong:** The current `_move_to_pose_with_screw` returns EITHER `-1` (failure) OR `(obs, reward, terminated, truncated, info)` tuple (success) OR a result dict (dry_run). The caller must handle all three cases.

**Why it happens:** The method was designed for single-shot use, not for composition in a loop with error checking.

**How to avoid:** Always check `if res == -1` for failure. When `dry_run=True`, the return is a result dict (for orientation search). When `dry_run=False`, the return is the env step tuple. Document the three return types clearly. Consider adding a wrapper that raises an exception on failure for cleaner control flow.

**Warning signs:** `TypeError: cannot unpack non-sequence int` when trying to unpack -1 as a tuple.

### Pitfall 4: Stale OBB After Cube Movement

**What goes wrong:** If `get_actor_obb()` is called before the physics engine has settled, the OBB reflects the cube's old position, leading to a grasp at the wrong location.

**Why it happens:** `get_actor_obb()` reads the actor's current mesh transform from the physics engine. If called immediately after another cube was placed (while physics is still settling), the target cube's OBB might be stale or the cube might still be in motion.

**How to avoid:** The `_actuate_gripper()` call at the end of each placement runs 6 simulation steps, which provides some settling time. If stacking of 4+ cubes shows grasp misalignment, add explicit settling steps (a few no-op actions) between placement and the next grasp.

**Warning signs:** Grasp misses the cube. Cube position in OBB does not match visual position.

### Pitfall 5: Backward Compatibility with PickPlaceSkill

**What goes wrong:** Refactoring primitives in `PickPlaceSkill` to support the new skill inadvertently breaks the existing 2-cube `solve()` for `StackCube-v1`.

**Why it happens:** `PickPlaceSkill.solve()` references `raw.cubeA` and `raw.cubeB`, which exist on `StackCubeEnv` but NOT on `StackNCubeEnv`. Any change to `solve()` must preserve these references.

**How to avoid:** Do NOT modify `PickPlaceSkill.solve()` at all. The new `StackNSkill` inherits the primitives but overrides `solve()`. The original `PickPlaceSkill` remains completely unchanged.

**Warning signs:** `AttributeError: 'StackNCubeEnv' has no attribute 'cubeA'` or vice versa.

### Pitfall 6: Incorrect Cube Indexing for Stacking Order

**What goes wrong:** The skill picks cubes in the wrong order, resulting in the stack not matching the evaluate() expectation (cube_0 on bottom, cube_1 on cube_0, etc.).

**Why it happens:** Confusion between "which cube to pick" and "which cube is the target." The loop must pick `cubes[i+1]` and place it ON `cubes[i]`.

**How to avoid:** The stacking order is: cube_0 stays on the table (never picked). For i in range(N-1): pick cubes[i+1], place on cubes[i]. After the first iteration, cubes[i] is the top of the existing stack.

**Warning signs:** `evaluate()` returns `all_pairs_stacked=False` even though visual inspection shows cubes are stacked.

## Code Examples

### Complete StackNSkill.solve() Method

```python
# Source: composition of existing PickPlaceSkill patterns
# with StackNCubeEnv.cubes list

def solve(self, env, seed=None):
    """Run sequential N-cube stacking on StackNCube-v1.

    The env must use pd_joint_pos control mode and num_envs=1.
    Returns (obs, reward, terminated, truncated, info).
    """
    env.reset(seed=seed)
    assert env.unwrapped.control_mode in [
        "pd_joint_pos", "pd_joint_pos_vel",
    ], f"Unsupported control mode: {env.unwrapped.control_mode}"

    planner = self._setup_planner(env)
    raw = env.unwrapped
    cubes = raw.cubes
    n = len(cubes)

    for i in range(n - 1):
        result = self._pick_and_stack(
            env, planner,
            cube_to_pick=cubes[i + 1],
            target_cube=cubes[i],
        )
        if result is None:
            print(f"ABORT: stacking failed at step {i+1}/{n-1}")
            # Get current env state for return
            info = raw.evaluate()
            return None, 0.0, False, False, info
        last_obs, last_rew, last_term, last_trunc, last_info = result

    return last_obs, last_rew, last_term, last_trunc, last_info
```

### Dynamic Stack-Top Position Computation

```python
# Source: derived from PickPlaceSkill.solve() stack computation
# and StackNCubeEnv.evaluate() z_target logic

# After placing cube_i on the stack, the target for cube_{i+1} is:
target_cube = cubes[i]   # current stack top
cube_height = (raw.cube_half_size[2] * 2).item()  # 0.04 for 0.02 half-size

# Read ACTUAL pose from physics engine (not computed from index)
goal_pose = target_cube.pose * sapien.Pose([0, 0, cube_height])

# Compute offset from cube's current position to goal
offset = (goal_pose.p - cube_to_pick.pose.p).cpu().numpy()[0]

# Apply offset to lifted position (preserves gripper orientation)
align_pose = sapien.Pose(lift_pose.p + offset, lift_pose.q)
```

### Failure Return Convention

```python
# The solve() method returns a 5-tuple on both success and failure.
# Success: standard env step tuple (obs, reward, terminated, truncated, info)
# Failure: (None, 0.0, False, False, info) where info contains evaluate() results
#
# The caller (run.py) checks success via info["success"]:
res = skill.solve(env, seed=seed)
obs, reward, terminated, truncated, info = res
success = bool(info["success"].item()) if isinstance(info["success"], torch.Tensor) else bool(info["success"])
```

### Registering the New Skill in run.py (Phase 3 preview)

```python
# This is Phase 3 scope, but for context on how the skill will be used:
# In run.py, a new policy dispatch:
elif policy == "stack_n":
    from ps_bed.skills.stack_n import StackNSkill
    skill = StackNSkill()
    # ... same episode loop as run_pick_place
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Monolithic solve() for 2 cubes | Composable _pick_and_stack() primitive | This phase | Enables N-cube stacking via loop |
| Hardcoded cubeA/cubeB references | Generic cube actor parameter | This phase | Works with any cube from cubes[] list |
| Ignore plan_screw failures | Abort on any failure | This phase | Clean failure semantics vs corrupt state |
| Fixed goal: cubeB.pose + height | Dynamic: current_top.pose + height | This phase | Handles settling and imprecision |

**Deferred to v2 (per prior decision):**
- Collision-aware planning (update_point_cloud, plan_pose fallback)
- Obstacle avoidance around existing stack

## Open Questions

1. **Lift height sufficiency for tall stacks**
   - What we know: Current lift offset is 0.1m above grasp pose. A 3-cube stack is ~0.12m tall (3 * 0.04). Table surface is at z=0.
   - What's unclear: Whether 0.1m lift provides enough clearance to avoid bumping a 4+ cube stack during horizontal movement to align position.
   - Recommendation: Start with 0.1m. If N >= 4 shows arm-stack collisions, increase to 0.15m or make lift proportional to stack height: `lift_z = max(0.1, (i + 1) * cube_height + 0.05)`.

2. **Settling time between placements**
   - What we know: `_actuate_gripper` runs 6 steps after release. Physics solver uses 20 position iterations.
   - What's unclear: Whether 6 steps is enough settling time for a 4+ cube stack before the next OBB computation.
   - Recommendation: Start with 6 steps. Add settling verification if needed (check `cubes[i].is_static()` before proceeding to next grasp).

3. **Return value convention for failed episodes**
   - What we know: `run_pick_place()` unpacks the solve() return as `(obs, reward, terminated, truncated, info)`. On failure, we need a 5-tuple.
   - What's unclear: Whether returning `None` as obs will break downstream logging.
   - Recommendation: Always return a valid 5-tuple. On failure, call `env.unwrapped.evaluate()` to get info dict and return `(None, 0.0, False, False, info)`. The run loop only checks `info["success"]`, so `None` obs is safe. Phase 3 integration may refine this.

## Sources

### Primary (HIGH confidence)
- `ps_bed/skills/pick_place.py` -- Complete existing skill implementation: `_setup_planner()`, `_move_to_pose_with_screw()`, `_actuate_gripper()`, `_follow_path()`, `solve()`
- `ps_bed/envs/stack_n_cube.py` -- Phase 1 environment: `self.cubes` list, `evaluate()` with N-pair stacking check, `cube_half_size` attribute
- `mani_skill/envs/tasks/tabletop/stack_cube.py` -- Upstream StackCubeEnv: `cubeA`/`cubeB` naming, evaluate() pattern, cube_half_size usage
- `mani_skill/examples/motionplanning/panda/solutions/stack_pyramid.py` -- ManiSkill's own 3-cube stacking solution: same OBB + grasp + screw pattern
- `mani_skill/examples/motionplanning/panda/solutions/stack_cube.py` -- ManiSkill's 2-cube stacking solution: offset computation pattern
- `mani_skill/examples/motionplanning/base_motionplanner/utils.py` -- `get_actor_obb()` and `compute_grasp_info_by_obb()` implementations
- `mani_skill/agents/robots/panda/panda.py` -- `build_grasp_pose()` (static method) and `is_grasping()` (contact force verification)
- Phase 1 research: `.planning/phases/01-n-cube-environment/01-RESEARCH.md` -- solver iterations, placement patterns, evaluation logic

### Secondary (MEDIUM confidence)
- Project ROADMAP: `.planning/ROADMAP.md` -- Phase dependencies, success criteria, requirement definitions
- Project CLAUDE.md -- mplib 0.2.x API notes, SAPIEN batching conventions, critical constraints

### Tertiary (LOW confidence)
- Empirical success rate for plan_screw at N > 3: no data yet. Expectation of degradation is based on plan_screw's straight-line task-space property and lack of environment obstacle awareness.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all APIs verified against installed source code
- Architecture (inheritance pattern): HIGH -- verified all four PickPlaceSkill methods are stateless and environment-agnostic
- Architecture (stacking loop): HIGH -- stacking order verified against StackNCubeEnv.evaluate()
- Dynamic target computation: HIGH -- same SAPIEN Pose arithmetic as working PickPlaceSkill
- Abort semantics: HIGH -- is_grasping verified in Panda class source, plan_screw failure detection verified
- Pitfalls (obstacle avoidance): MEDIUM -- based on mplib plan_screw behavior analysis, no empirical testing at N > 3

**Research date:** 2026-02-13
**Valid until:** Stable -- mplib 0.2.1 and ManiSkill3 3.0.0b22 are pinned. Valid until either version changes.
