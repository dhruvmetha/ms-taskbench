# Milestones

## v1.0 N-Cube Stacking MVP (Shipped: 2026-02-14)

**Phases completed:** 3 phases, 3 plans, 6 tasks
**Lines of code:** 1,533 Python
**Timeline:** ~3 hours (2026-02-13 20:42 → 23:32)
**Git range:** 6de1a8a → 6ee7f7b (19 commits)

**Delivered:** Configurable N-cube stacking testbed with motion-planned sequential stacking skill and CLI-driven video recording.

**Key accomplishments:**
- StackNCube-v1 environment with parameterized N cubes (2-6), collision-free random placement, and N-pair stacking evaluation
- StackNSkill with sequential N-1 pick-place loop, dynamic stack-top targeting, grasp/placement verification, and clean abort semantics
- Hydra CLI integration: `python -m ps_bed.run run.policy=stack_n env.num_cubes=5 env.record_video=true`
- Auto env_id switching and conditional parameter forwarding for seamless UX
- Full backward compatibility with existing random and pick_place policies

---

