# Phase 2: Sequential Stacking Skill - Context

**Gathered:** 2026-02-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Compose reusable grasp primitives into a sequential N-cube stacking skill that chains N-1 pick-place operations with clean failure handling. The skill targets StackNCube-v1 (Phase 1). The existing 2-cube PickPlaceSkill must remain backward-compatible with StackCube-v1.

</domain>

<decisions>
## Implementation Decisions

### Stacking strategy
- Sequential index order: cube_0 always stays on the table as base, stack cube_1 on cube_0, cube_2 on cube_1, etc.
- No adaptive/nearest-first ordering — index order matches evaluate() directly, no remapping needed
- Dynamic lift height: increase lift clearance proportional to stack height as the tower grows, to help avoid arm-stack collisions for N>3

### Retry & robustness
- Abort immediately if all grasp angles fail for a cube — no retry of the full grasp cycle
- Verify every grasp with `is_grasping()` after closing the gripper — abort if cube isn't actually held
- Verify each placement after releasing — check the placed cube's z-position is where expected before moving to next pick
- Add explicit settling steps (no-op actions) between releasing a cube and starting the next pick, beyond the existing 6 gripper steps

### Failure reporting
- Step-by-step prints during successful runs: "Picking cube_1...", "Placing on cube_0...", "Step 1/2 complete"
- On failure: print which step failed and why (e.g., "Step 2/4 FAILED: grasp verification failed for cube_3") — concise but actionable
- Use Python's `logging` module (not plain prints) with configurable levels

### Partial success & return values
- Report progress fraction on failure: include `cubes_stacked` count in info dict
- Always return a valid obs (real env observation), never None — consistent 5-tuple on both success and failure
- Include `failure_reason` string in info dict on failure (e.g., "grasp_verification_failed", "placement_check_failed", "plan_failed")
- Binary success still determined by evaluate() (all N cubes stacked), but partial progress is tracked

### Claude's Discretion
- Exact settling step count between placements
- Lift height formula (e.g., proportional to `i * cube_height + margin`)
- Placement verification threshold (how close z must be to expected)
- Logger name and format conventions

</decisions>

<specifics>
## Specific Ideas

- Dynamic lift height should scale with stack progress to help N=4-5 succeed even without collision-aware planning
- Failure reasons should be machine-readable strings (not free-form messages) so they can be aggregated programmatically

</specifics>

<deferred>
## Deferred Ideas

- Collision-aware planning (point cloud obstacles, plan_pose fallback) — v2 scope per prior decision
- Nearest-first adaptive stacking order — adds complexity for little gain with current evaluate() logic
- GSD agent model profile configuration — use `/gsd:set-profile` separately

</deferred>

---

*Phase: 02-sequential-stacking-skill*
*Context gathered: 2026-02-13*
