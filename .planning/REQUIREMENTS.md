# Requirements: Program Synthesis Bed

**Defined:** 2026-02-13
**Core Value:** Reliably execute multi-step pick-place sequences on configurable N-cube environments and produce video demos

## v1 Requirements

Requirements for N-cube stacking milestone. Each maps to roadmap phases.

### Environment

- [ ] **ENV-01**: User can specify number of cubes N via `gym.make("StackNCube-v1", num_cubes=N)`
- [ ] **ENV-02**: N cubes spawn on table with collision-free random placement each episode
- [ ] **ENV-03**: Success evaluation checks all N-1 adjacent pairs are stacked, static, and released
- [ ] **ENV-04**: Episode step budget scales with N to prevent premature truncation

### Skill

- [ ] **SKIL-01**: Skill chains N-1 pick-place operations sequentially in a single episode
- [ ] **SKIL-02**: Each pick-place targets the current stack-top position (dynamic height computation)
- [ ] **SKIL-03**: Episode aborts immediately if any grasp or place step fails

### Integration

- [ ] **INTG-01**: `num_cubes` configurable via Hydra (`env.num_cubes=5`)
- [ ] **INTG-02**: `run.py` dispatches to new stacking skill via `run.policy=stack_n`
- [ ] **INTG-03**: Video recording captures full multi-cube stacking sequence

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Robustness

- **ROB-01**: plan_pose (RRT) fallback when plan_screw fails near obstacles
- **ROB-02**: Planner scene awareness via update_point_cloud for placed cubes
- **ROB-03**: Partial success metrics (cubes_stacked count in evaluate())
- **ROB-04**: Failure recovery/retry per cube before aborting
- **ROB-05**: Stacking order specification (user-defined sequence)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| RL policy for N-cube stacking | Research problem, not demo generation scope |
| GPU-parallel motion planning | mplib requires num_envs=1, CPU single-env |
| Dynamic N mid-episode | ManiSkill3 actors loaded once at construction via _load_scene |
| Heterogeneous object shapes | Scope creep — cubes only for this milestone |
| Configurable cube sizes | Separate concern, defer to later milestone |
| Dense reward shaping for N cubes | Only needed for RL, not motion-planned demos |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENV-01 | Phase 1: N-Cube Environment | Pending |
| ENV-02 | Phase 1: N-Cube Environment | Pending |
| ENV-03 | Phase 1: N-Cube Environment | Pending |
| ENV-04 | Phase 1: N-Cube Environment | Pending |
| SKIL-01 | Phase 2: Sequential Stacking Skill | Pending |
| SKIL-02 | Phase 2: Sequential Stacking Skill | Pending |
| SKIL-03 | Phase 2: Sequential Stacking Skill | Pending |
| INTG-01 | Phase 3: Config and Recording Integration | Pending |
| INTG-02 | Phase 3: Config and Recording Integration | Pending |
| INTG-03 | Phase 3: Config and Recording Integration | Pending |

**Coverage:**
- v1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0

---
*Requirements defined: 2026-02-13*
*Last updated: 2026-02-13 after roadmap creation*
