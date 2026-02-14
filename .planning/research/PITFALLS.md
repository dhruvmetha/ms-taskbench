# Pitfalls Research

**Domain:** Multi-object sequential stacking in ManiSkill3/SAPIEN with mplib 0.2.x motion planning
**Researched:** 2026-02-13
**Confidence:** MEDIUM-HIGH (grounded in codebase analysis, verified API docs, and known issues)

## Critical Pitfalls

### Pitfall 1: mplib Planner Has No Knowledge of Placed Cubes

**What goes wrong:**
The current `PickPlaceSkill` creates an `mplib.Planner` once per episode and never updates its world model. After stacking cube 1 onto the target, the planner does not know cube 1 is now sitting on the stack. When planning the trajectory for cube 2, the robot arm or gripper can collide with the already-placed cube 1 because mplib plans as if the table is empty.

**Why it happens:**
The existing code (lines 27-53 of `pick_place.py`) builds the planner from the robot URDF only. No environment obstacles are registered. For single pick-place, this works because the only obstacle is the target cube (which the robot is moving toward, not avoiding). With N cubes, previously placed cubes become obstacles that mplib must know about.

**How to avoid:**
After each successful place-and-release step, sample a point cloud from the placed cube's geometry and call `planner.update_point_cloud(points, name="placed_cubes")`. In mplib 0.2.x, `plan_screw` and `plan_pose` automatically use registered collision objects -- the old `use_point_cloud=True` parameter was removed in the 0.1-to-0.2 API migration. You simply need to call `update_point_cloud` and the planner will respect it.

Alternatively, for box-shaped cubes, you could use `planner.update_attached_box()` on a fixed link or add FCL collision objects directly. Point cloud is simpler and more general.

**Warning signs:**
- Robot arm sweeps through the stack on the way to grasp the next cube
- Placed cubes get knocked off during transit motions
- Success rate drops sharply between cube 2 and cube 3 (taller stack = more collision surface)

**Phase to address:**
Phase 1 (core multi-stack skill). This must be solved before any multi-cube stacking can work reliably.

---

### Pitfall 2: plan_screw Cannot Detour Around Obstacles

**What goes wrong:**
`plan_screw` computes a single screw-motion trajectory (straight-line in task space). If any point along that straight line collides with an obstacle (like a placed cube), the plan fails outright. It does not search for alternative paths. The current code retries once on failure (lines 91-100 of `pick_place.py`), but a second identical call will produce the same failure.

**Why it happens:**
Screw motion is a deterministic interpolation, not a sampling-based search. It is fast and produces smooth paths, but it has zero ability to navigate around obstacles. The existing code works for single pick-place because the path from above the table to the grasp pose is typically unobstructed.

**How to avoid:**
Implement a fallback planning strategy. When `plan_screw` fails, fall back to `plan_pose` which uses RRT-Connect (sampling-based planner) that can find collision-free paths around obstacles. The pattern should be:

```python
result = planner.plan_screw(goal, current_qpos, time_step=dt)
if result["status"] != "Success":
    result = planner.plan_pose(goal, current_qpos, time_step=dt)
    if result["status"] != "Success":
        return FAILURE  # abort this cube
```

This is especially critical for the "align over stack" motion where the gripper must move laterally above already-placed cubes.

**Warning signs:**
- `plan_screw` failures increase with stack height
- Failures concentrate on lateral alignment moves (not vertical lifts)
- Adding more cubes to the scene makes previously-working episodes fail

**Phase to address:**
Phase 1 (core multi-stack skill). The fallback planner is a prerequisite for reliable multi-cube stacking.

---

### Pitfall 3: Physics Instability Topples Tall Stacks

**What goes wrong:**
After stacking 3+ cubes, the tower becomes unstable. Cubes slide off or the entire stack topples. This happens even when the placement was geometrically correct, because PhysX's iterative constraint solver does not perfectly resolve resting contact in tall stacks.

**Why it happens:**
PhysX (SAPIEN's physics engine) uses an iterative solver. The default solver position iterations (15 in ManiSkill3) may be insufficient for maintaining stable contact across 4+ stacked objects. The constraint graph depth grows with stack height, and the solver's convergence degrades. The ManiSkill source code itself acknowledges this: "GPU sim can be fast but unstable. Angular velocity is rather high despite it not really rotating."

Additionally, the current code uses `cube_half_size` (0.02m) cubes. A 5-cube stack is only 0.2m tall with a 0.04m x 0.04m base -- an aspect ratio of 5:1, which is challenging for any physics engine.

**How to avoid:**
1. Increase solver iterations for the stacking environment: override `_default_sim_config` to set `solver_position_iterations >= 20` and `solver_velocity_iterations >= 4` (ManiSkill docs recommend >= 20 for stable grasps).
2. Add a settling period after each placement: after releasing the gripper, step the simulation 10-20 extra times before checking success or grasping the next cube.
3. For placement, approach from directly above and release at minimal height above the stack (reduce drop distance).
4. Consider slightly larger cubes (half_size=0.025) for stacks of 4+ to improve the base-to-height ratio.

**Warning signs:**
- Stacks wobble visibly in video recordings after cube 3
- Angular velocity of placed cubes is non-zero despite appearing stationary
- Success rate degrades non-linearly: 2-stack works great, 3-stack is marginal, 4-stack rarely succeeds
- Cubes that were stationary start moving 5-10 timesteps after release

**Phase to address:**
Phase 1 (environment and physics tuning). Physics parameters should be validated with a simple scripted drop test before integrating with the motion planner.

---

### Pitfall 4: Grasp Pose Computation Ignores Stack Context

**What goes wrong:**
The current grasp computation (lines 121-147 of `pick_place.py`) uses `get_actor_obb` and `compute_grasp_info_by_obb` with a fixed top-down approach vector `[0, 0, -1]`. This works when cubes are flat on the table. But when the next cube to pick is near the base of a tall stack, the top-down approach may collide with the stack. Worse: if a cube needs to be picked from a position adjacent to the stack, the gripper fingers may not have clearance.

**Why it happens:**
The approach vector is hardcoded. The grasp search loop (lines 137-148) only rotates around the Z axis, never changing the approach angle. For cubes on a clear table, top-down is always best. With obstacles nearby, a tilted or side approach may be the only feasible option.

**How to avoid:**
1. For N-cube stacking where all cubes start on the table, pick in order from farthest-from-stack to nearest. This maximizes clearance.
2. Before computing the grasp, check if the top-down approach is clear by testing a pre-grasp pose (the `reach_pose` at -0.05m offset). If `plan_screw` to the reach pose fails, try approach angles tilted 15-30 degrees from vertical.
3. Consider adding a pre-sort step that orders cubes by distance from the target stack position, picking the farthest first.

**Warning signs:**
- Grasp search loop exhausts all angles without finding a valid pose
- "Warning: failed to find a valid grasp pose" message appears more often with more cubes
- Success depends heavily on random initial cube placement

**Phase to address:**
Phase 2 (grasp strategy refinement). Basic multi-stacking should work first with favorable cube arrangements before tackling adversarial placements.

---

### Pitfall 5: No Abort-on-Failure Propagation in Sequential Steps

**What goes wrong:**
The current `solve()` method (lines 105-175) executes a fixed sequence: reach, grasp, lift, align, release. If any step fails (e.g., `_move_to_pose_with_screw` returns -1), the code prints a warning and continues to the next step. For multi-cube stacking, this means a failed grasp on cube 2 leads to the robot attempting to "lift" nothing, then "placing" nothing on the stack -- wasting time and potentially knocking over the existing stack with random motions.

**Why it happens:**
The single pick-place code was written as a proof-of-concept where failure just means a failed episode. With sequential stacking, a failure mid-sequence must halt the entire sequence or at minimum skip to the next cube.

**How to avoid:**
Implement structured abort semantics:

```python
class StackResult:
    success: bool
    cubes_placed: int
    failure_reason: Optional[str]
    failure_step: Optional[str]  # "grasp", "lift", "align", "place"
    failure_cube: Optional[int]
```

Each sub-step should return a status. On failure:
- If grasp fails: skip this cube, try the next one (or abort entirely)
- If lift fails: open gripper, retreat to home, skip this cube
- If align/place fails: retreat with cube still grasped, try a different placement approach
- Track partial success (e.g., "placed 3 of 5 cubes")

**Warning signs:**
- Robot makes motions that make no sense after a planning failure
- Stack gets knocked over by a failed placement attempt
- Episode takes much longer than expected (robot is executing garbage actions)

**Phase to address:**
Phase 1 (core multi-stack skill). Abort semantics are fundamental to sequential execution.

---

### Pitfall 6: Attached Object Collision Not Updated During Carry

**What goes wrong:**
When the gripper grasps a cube and carries it to the stack, the carried cube occupies space that mplib does not account for. The planner may generate a path where the carried cube collides with the stack or table, even though the gripper itself is collision-free.

**Why it happens:**
mplib only checks collisions for the robot's own links (defined in the URDF). A grasped cube is not part of the robot model. Without `update_attached_box`, the planner treats the gripper as if it were empty.

**How to avoid:**
After grasping, call `planner.update_attached_box(size=[0.04, 0.04, 0.04], pose=[0, 0, 0.02, 1, 0, 0, 0])` (cube dimensions + offset from TCP to cube center). After releasing, call `planner.detach_object()`. The pose is relative to the move group link (panda_hand_tcp), so the offset depends on how deep the grasp is.

In mplib 0.2.x, once `update_attached_box` is called, the planner automatically includes the attached geometry in collision checks for all subsequent planning calls.

**Warning signs:**
- Carried cube clips through the top of the stack during lateral alignment
- Successful planning but physics detects collision during execution
- Cube gets knocked out of gripper by collision with stack edge

**Phase to address:**
Phase 2 (robust carry and place). Basic stacking may work without this if approach angles are favorable, but robust multi-cube stacking requires it.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcoded approach vector `[0, 0, -1]` | Simple, works for table-top | Cannot grasp near obstacles or in cluttered scenes | Only for 2-3 cube stacks with favorable placement |
| Recreating planner every episode | Avoids stale state | ~200ms overhead per episode, prevents caching | Always acceptable for CPU single-env |
| No point cloud updates | Simpler code path | Arm collisions with placed objects | Never acceptable for 3+ cube stacking |
| Fixed gripper open/close steps (6) | Simple timing | May not fully close on smaller cubes or fully open to clear | Acceptable if cube size is fixed |
| Single `plan_screw` with one retry | Fast planning | Fails when any obstacle is in the straight-line path | Only for single pick-place with clear workspace |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| mplib 0.2.x point cloud | Passing point cloud in world frame without accounting for robot base pose | Transform points into the robot arm's root link frame before calling `update_point_cloud` |
| mplib 0.2.x attached box pose | Using world-frame pose for the attached box | Pose must be relative to the move group link (panda_hand_tcp), not world frame |
| SAPIEN pose tensors | Using `pose.p` directly (shape `(1, 3)`) | Must `.flatten()` or index `[0]` before passing to mplib or numpy operations |
| ManiSkill `_initialize_episode` | Setting object poses with unbatched tensors | All pose tensors must have batch dimension matching `len(env_idx)` |
| `RecordEpisode` with sequential skills | Calling `env.reset()` mid-sequence triggers video save | Use `save_on_reset=False` and call `flush_video()` only at sequence end |
| mplib quaternion convention | Assuming xyzw quaternion order | mplib uses wxyz (same as SAPIEN), but numpy operations may accidentally reorder |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Rebuilding planner per cube | 200ms+ per cube, 1s+ for 5-cube stack | Build planner once per episode, update point cloud between cubes | Noticeable at 4+ cubes per episode |
| Dense point cloud for obstacle cubes | `plan_pose` (RRT) takes 5+ seconds per plan | Use resolution=0.005 (5mm) for cube point clouds, not default 1mm. 200-500 points per cube is sufficient | With 5+ obstacle cubes in scene |
| Settling simulation after each place | 20 extra steps x 4 cubes = 80 wasted steps if settling is too generous | Measure actual settling time: check velocity < threshold, stop early | When episode step budget is tight (default 50 steps may be too low for 5-cube stacking) |
| Full `get_actor_obb` per cube | OBB computation involves mesh processing | Cache cube dimensions (they are all the same size), only query pose | Negligible for 5 cubes, matters at 20+ |

## "Looks Done But Isn't" Checklist

- [ ] **Multi-stack skill:** Robot places cube correctly in video BUT angular velocity of placed cube is > 0.5 rad/s (ManiSkill's static threshold) -- verify `evaluate()` actually passes the is_cubeA_static check
- [ ] **Point cloud collision:** Planner finds a path AND it visually avoids placed cubes BUT check `env.scene.get_contacts()` to verify no actual physics collisions occurred during execution (mplib plans in configuration space, execution is in physics simulation -- they can disagree)
- [ ] **Gripper clearance:** Gripper opens to release cube BUT cube sticks to gripper due to residual contact forces -- verify cube is actually released by checking cube position 5+ steps after gripper open
- [ ] **Stack height measurement:** Place pose is computed as `target_z + N * cube_height` BUT this assumes perfect placement of all previous cubes -- use actual measured pose of the top of the stack instead of theoretical height
- [ ] **Episode step budget:** 5-cube stacking completes all grasps BUT episode truncates before final placement because `max_episode_steps=50` is too low for sequential manipulation -- budget ~15-20 steps per pick-place cycle
- [ ] **Success metric:** Environment reports success=True BUT only checks top cube placement (inherited from 2-cube StackCube) -- verify custom `evaluate()` checks ALL N cubes are stacked

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Planner ignores placed cubes | LOW | Add `update_point_cloud` call after each place. No architectural change needed |
| `plan_screw` fails with obstacles | LOW | Add `plan_pose` fallback. Single function call change in `_move_to_pose_with_screw` |
| Physics instability | MEDIUM | Tune solver iterations, add settling period, possibly enlarge cubes. Requires testing |
| Grasp pose fails near stack | MEDIUM | Add approach angle search, cube ordering heuristic. Moderate code addition |
| No abort semantics | MEDIUM | Restructure `solve()` into per-cube loop with status returns. Moderate refactor |
| Attached box not tracked | LOW | Add `update_attached_box` / `detach_object` calls around grasp/release. Minimal code |
| Episode step budget exceeded | LOW | Increase `max_episode_steps` in env registration and config. Config change only |
| `evaluate()` only checks 2 cubes | MEDIUM | Write custom `evaluate()` for N-cube stacking env. Requires env subclass work |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Planner ignores placed cubes | Phase 1: Core multi-stack | Run 3-cube stack, visually confirm no arm-through-stack collisions |
| plan_screw cannot detour | Phase 1: Core multi-stack | Run with obstacle cube between pick and place zones, verify planner finds path |
| Physics instability | Phase 1: Environment setup | Script a 5-cube drop test (no robot) and measure settling time and drift |
| Grasp pose near stack | Phase 2: Robust grasping | Place a cube 4cm from a 3-high stack, verify successful grasp |
| No abort semantics | Phase 1: Core multi-stack | Intentionally fail a grasp (e.g., unreachable cube) and verify clean abort |
| Attached box not tracked | Phase 2: Robust carry | Carry cube past a 3-high stack, verify no clipping in video |
| Episode step budget | Phase 1: Environment setup | Profile steps per pick-place cycle, set max_episode_steps = N_cubes * steps_per_cycle * 1.5 |
| evaluate() for N cubes | Phase 1: Environment setup | Build custom env, verify success=True requires all N cubes stacked |
| Contact buffer overflow (GPU) | Phase 3: GPU scaling (if needed) | Increase `max_rigid_contact_count` and `max_rigid_patch_count` in `SimConfig` if switching to GPU sim |

## Sources

- [mplib 0.2.0a1 Planner API Reference](https://motion-planning-lib.readthedocs.io/v0.2.0a1/reference/Planner.html) -- Confirmed `plan_screw` signature lacks `use_point_cloud` in 0.2.x (removed, now automatic). HIGH confidence.
- [mplib Releases (v0.2.0 changelog)](https://github.com/haosulab/MPlib/releases) -- Confirmed `use_point_cloud`/`use_attach` args removed in 0.2.0; collision objects auto-used when registered. HIGH confidence.
- [SAPIEN Collision Avoidance Tutorial](https://sapien.ucsd.edu/docs/latest/tutorial/motion_planning/collision_avoidance.html) -- Demonstrates `update_point_cloud` and `update_attached_box` workflow for obstacle avoidance. MEDIUM confidence (SAPIEN 2.2 tutorial, may use mplib 0.1.x API).
- [ManiSkill Issue #957: Collision detection with mplib](https://github.com/haosulab/ManiSkill/issues/957) -- Documents known issue: mplib planner may accept trajectories that visually collide with obstacles. MEDIUM confidence.
- [MPlib Issue #108: Collision detection with obstacles](https://github.com/haosulab/MPlib/issues/108) -- Insufficient point cloud density causes missed collisions. Point cloud must be in robot root frame. MEDIUM confidence.
- [PhysX 5.4.1 Rigid Body Dynamics](https://nvidia-omniverse.github.io/PhysX/physx/5.4.1/docs/RigidBodyDynamics.html) -- TGS solver recommended for stacking. Default 4 position iterations insufficient for tall stacks. HIGH confidence.
- [ManiSkill GPU Simulation docs](https://maniskill.readthedocs.io/en/latest/user_guide/concepts/gpu_simulation.html) -- `solver_position_iterations >= 20` recommended for stable grasps. Buffer overflow parameters for many-object scenes. MEDIUM confidence.
- [ManiSkill StackCube source](https://github.com/haosulab/ManiSkill/blob/main/mani_skill/envs/tasks/tabletop/stack_cube.py) -- Developer comment: "GPU sim can be fast but unstable." Angular velocity threshold relaxed to 0.5 rad/s. HIGH confidence (verified in source).
- [ManiSkill Advanced Task Building](https://github.com/haosulab/ManiSkill/blob/main/docs/source/user_guide/tutorials/custom_tasks/advanced.md) -- Scene masks and `Actor.merge()` for heterogeneous object counts. Objects cannot be added/removed between episodes without reconfiguration. MEDIUM confidence.
- [PyBullet Forum: Stable box stacking](https://pybullet.org/Bullet/phpBB3/viewtopic.php?t=9712&start=15) -- Solver iteration count, friction basis consistency, and angular integration are key factors in stacking stability. LOW confidence (different engine, but physics principles transfer).

---
*Pitfalls research for: Multi-object sequential stacking in ManiSkill3/SAPIEN with mplib 0.2.x*
*Researched: 2026-02-13*
