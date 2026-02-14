# Roadmap: Program Synthesis Bed

## Overview

This roadmap delivers configurable N-cube sequential stacking on ManiSkill3. Phase 1 builds the parameterized StackNCube-v1 environment with collision-free spawning and N-cube success evaluation. Phase 2 composes reusable grasp primitives into a sequential stacking skill that chains N-1 pick-place operations. Phase 3 wires everything into the existing Hydra config and run.py dispatch with video recording. Collision-aware planning (point cloud obstacles, plan_pose fallback) is explicitly v2 scope.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: N-Cube Environment** - Parameterized StackNCube-v1 env with N cubes, collision-free spawn, success evaluation, and scaled step budget
- [ ] **Phase 2: Sequential Stacking Skill** - Extract grasp primitives and compose N-1 pick-place loop with dynamic targeting and abort semantics
- [ ] **Phase 3: Config and Recording Integration** - Hydra wiring, run.py dispatch, and video capture of full stacking sequences

## Phase Details

### Phase 1: N-Cube Environment
**Goal**: User can instantiate a ManiSkill3 environment with any number of cubes that spawn safely, evaluate stacking success correctly, and allow enough steps
**Depends on**: Nothing (first phase)
**Requirements**: ENV-01, ENV-02, ENV-03, ENV-04
**Success Criteria** (what must be TRUE):
  1. `gym.make("StackNCube-v1", num_cubes=N)` creates an environment with exactly N cubes visible on the table for any N in [2, 6]
  2. Cubes spawn at random positions each reset without overlapping each other or falling off the table
  3. `env.evaluate()` returns success=True only when all N cubes form a single stack (all N-1 adjacent pairs stacked, static, and released)
  4. Episodes allow enough steps for a planner to complete N-1 pick-place operations without premature truncation
**Plans:** 1 plan

Plans:
- [ ] 01-01-PLAN.md -- Implement StackNCubeEnv (BaseEnv), register as StackNCube-v1, verify all ENV requirements

### Phase 2: Sequential Stacking Skill
**Goal**: A skill can pick up cubes one by one and stack all N cubes into a tower, aborting cleanly if any step fails
**Depends on**: Phase 1
**Requirements**: SKIL-01, SKIL-02, SKIL-03
**Success Criteria** (what must be TRUE):
  1. Running the stacking skill on StackNCube-v1 with N=3 produces a 3-cube tower in a single episode
  2. Each successive cube is placed on top of the current stack (not at a fixed height), correctly computing the dynamic stack-top position
  3. If a grasp fails or a place fails, the episode terminates immediately with a clear failure indication rather than continuing with a corrupt state
  4. The existing 2-cube PickPlaceSkill still works on StackCube-v1 after primitives are refactored (backward compatibility)
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: Config and Recording Integration
**Goal**: User can run N-cube stacking from the command line with a single Hydra command and get a video of the result
**Depends on**: Phase 1, Phase 2
**Requirements**: INTG-01, INTG-02, INTG-03
**Success Criteria** (what must be TRUE):
  1. `python -m ps_bed.run env.num_cubes=5 run.policy=stack_n` runs a 5-cube stacking episode end to end without manual setup
  2. `env.record_video=true` produces a video file showing the complete multi-cube stacking sequence from start to finish
  3. Default config values work sensibly (e.g., num_cubes defaults to 3 or similar, policy dispatches correctly)
**Plans**: TBD

Plans:
- [ ] 03-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. N-Cube Environment | 0/1 | Planned | - |
| 2. Sequential Stacking Skill | 0/TBD | Not started | - |
| 3. Config and Recording Integration | 0/TBD | Not started | - |
