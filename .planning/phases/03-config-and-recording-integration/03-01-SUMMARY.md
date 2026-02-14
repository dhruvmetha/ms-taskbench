---
phase: 03-config-and-recording-integration
plan: 01
subsystem: config
tags: [hydra, config, cli, integration, video-recording]

# Dependency graph
requires:
  - phase: 01-n-cube-environment
    provides: StackNCubeEnv with configurable N-cube environments
  - phase: 02-sequential-stacking-skill
    provides: StackNSkill for sequential multi-cube stacking
provides:
  - Hydra config integration with num_cubes parameter
  - run_stack_n() policy dispatcher with auto env_id switching
  - Conditional num_cubes forwarding to env factories
  - CLI interface for N-cube stacking with video recording
affects: [usage, deployment, testing]

# Tech tracking
tech-stack:
  added: []
  patterns: [conditional-kwargs-forwarding, auto-env-switching, policy-dispatch-pattern]

key-files:
  created: []
  modified: [ps_bed/config.py, configs/default.yaml, ps_bed/env.py, ps_bed/run.py]

key-decisions:
  - "Conditional num_cubes forwarding prevents passing unexpected kwargs to StackCube-v1"
  - "Auto env_id switching from StackCube-v1 to StackNCube-v1 when policy=stack_n"
  - "max_episode_steps=250 default for stack_n policy to accommodate N-cube sequences"

patterns-established:
  - "_extra_env_kwargs() pattern for env-specific parameter forwarding"
  - "Auto env_id switching pattern for policy-specific environment requirements"
  - "Policy dispatch with specialized parameter overrides per policy type"

# Metrics
duration: 2min
completed: 2026-02-14
---

# Phase 03 Plan 01: Config and Recording Integration Summary

**Hydra CLI integration enabling `python -m ps_bed.run run.policy=stack_n env.num_cubes=5 env.record_video=true` with auto env_id switching and conditional parameter forwarding**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-14T04:15:04Z
- **Completed:** 2026-02-14T04:17:18Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- num_cubes config parameter added to Hydra config (default: 3) with conditional forwarding to gym.make()
- run_stack_n() policy dispatcher with automatic StackCube-v1 → StackNCube-v1 switching
- Full CLI integration: `python -m ps_bed.run run.policy=stack_n env.num_cubes=N env.record_video=true`
- Backward compatibility maintained: random and pick_place policies unaffected

## Task Commits

Each task was committed atomically:

1. **Task 1: Add num_cubes to Hydra config and conditionally forward through env factories** - `c62a06d` (feat)
   - Added num_cubes field to EnvConfig dataclass (default: 3)
   - Added num_cubes to configs/default.yaml
   - Created _extra_env_kwargs() helper for conditional parameter forwarding
   - Updated make_env() and make_single_env() to use extra kwargs
   - Ensures backward compatibility: num_cubes only passed to StackNCube-v1

2. **Task 2: Add run_stack_n() with auto env_id switching and policy dispatch** - `1fb3498` (feat)
   - Implemented run_stack_n() function with StackNSkill integration
   - Auto-switches env_id from StackCube-v1 to StackNCube-v1 when policy=stack_n
   - Overrides control_mode, reward_mode, max_episode_steps for planner requirements
   - Added camera configurations to StackNCubeEnv for video recording
   - Updated policy dispatch in main() to include stack_n branch
   - Updated ValueError message to list all three policies

## Files Created/Modified
- `ps_bed/config.py` - Added num_cubes: int = 3 field to EnvConfig
- `configs/default.yaml` - Added num_cubes: 3 under env section
- `ps_bed/env.py` - Added _extra_env_kwargs() helper for conditional parameter forwarding
- `ps_bed/run.py` - Added run_stack_n() function with auto env_id switching and policy dispatch
- `ps_bed/envs/stack_n_cube.py` - Added camera configurations for video recording support

## Decisions Made

**Conditional parameter forwarding via _extra_env_kwargs():**
- Prevents passing unexpected num_cubes kwarg to StackCube-v1 and StackCubeDistractor-v1
- Uses simple string check: if "StackNCube" in env_id, include num_cubes in kwargs dict
- Maintains backward compatibility with existing environments

**Auto env_id switching pattern:**
- When run.policy=stack_n and env.env_id is still default "StackCube-v1", auto-switch to "StackNCube-v1"
- Prints notification: "Note: auto-switching env_id to StackNCube-v1 for stack_n policy"
- Improves UX: users can run `python -m ps_bed.run run.policy=stack_n` without explicit env_id override
- Respects explicit user overrides if env_id is set to something other than default

**Policy-specific parameter overrides:**
- run_stack_n() overrides control_mode, reward_mode, max_episode_steps to meet planner requirements
- max_episode_steps=250 (up from default 100) to accommodate multi-cube stacking sequences
- Follows pattern established by run_pick_place()

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. All verification tests passed:
- EnvConfig.num_cubes defaults to 3
- configs/default.yaml parses with num_cubes: 3
- Backward compatibility verified: StackCube-v1 works without receiving num_cubes kwarg
- stack_n policy completes episodes successfully with auto env_id switching
- Video recording produces .mp4 files in videos/ directory
- random and pick_place policies continue to work unchanged

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**All requirements met:**
- INTG-01 (num_cubes via Hydra): `python -m ps_bed.run env.num_cubes=5 run.policy=stack_n` works
- INTG-02 (policy dispatch): run.policy=stack_n dispatches correctly
- INTG-03 (video recording): env.record_video=true produces .mp4 files
- Backward compatibility: existing policies unaffected

**Integration complete.** The ps_bed testbed now provides a unified CLI interface for:
- Random policies on vectorized environments
- Single-cube motion planning (pick_place)
- N-cube sequential stacking (stack_n) with configurable cube count

**Project milestone achieved:** All three phases complete. Users can now:
```bash
# Stack N cubes with video recording
python -m ps_bed.run run.policy=stack_n env.num_cubes=5 env.record_video=true

# Change seed and episode count
python -m ps_bed.run run.policy=stack_n env.num_cubes=4 seed=123 run.num_episodes=10

# Works with defaults (3 cubes, auto env_id switching)
python -m ps_bed.run run.policy=stack_n
```

---
*Phase: 03-config-and-recording-integration*
*Completed: 2026-02-14*

## Self-Check: PASSED

All files exist:
- FOUND: ps_bed/config.py
- FOUND: configs/default.yaml
- FOUND: ps_bed/env.py
- FOUND: ps_bed/run.py
- FOUND: ps_bed/envs/stack_n_cube.py

All commits exist:
- FOUND: c62a06d (Task 1: Add num_cubes to Hydra config and conditional env forwarding)
- FOUND: 1fb3498 (Task 2: Add run_stack_n() with auto env_id switching and policy dispatch)
