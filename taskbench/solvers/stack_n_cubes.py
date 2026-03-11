"""Unified cube-stacking solver using pick/place skill objects.

Loops over ``pick()`` / ``place()`` calls to stack N cubes into a tower.
The 2-cube case (``StackCube-v1``) is just ``n=2``.
"""

import logging

import numpy as np
import sapien

from taskbench.recorder import StateRecorder
from taskbench.skills.context import SkillContext
from taskbench.skills.motion import actuate_gripper
from taskbench.solver import BaseSolver, SolverResult, register_solver

logger = logging.getLogger("taskbench.solvers.stack_n_cubes")


@register_solver("stack_cubes")
class StackCubesSolver(BaseSolver):
    """Stack N cubes into a tower using sequential pick-place primitives."""

    def solve(self, env, seed=None) -> SolverResult:
        """Stack all cubes into a tower using N-1 pick-place operations."""
        # Set up recorder and skill context
        ctx = SkillContext(env)
        ctx.reset(seed=seed)

        assert env.unwrapped.control_mode in [
            "pd_joint_pos",
            "pd_joint_pos_vel",
        ], f"Unsupported control mode: {env.unwrapped.control_mode}"

        raw = env.unwrapped
        objects = ctx.objects
        names = list(objects.keys())
        rng = np.random.default_rng(seed)
        rng.shuffle(names)
        n = len(names)
        total_steps = n - 1

        # Set up state recorder and rebind skills with callback
        recorder = StateRecorder(
            env,
            objects=objects,
            robot_fields=["qpos", "tcp_pos", "tcp_quat", "gripper_qpos"],
        )
        ctx.step_callback = recorder.record
        ctx._build_skills()
        recorder.record()  # initial state

        logger.info(f"Starting sequential stacking: {n} cubes, {total_steps} pick-place steps (seed={seed})")

        for i in range(total_steps):
            pick_name = names[i + 1]
            target_name = names[i]
            pick_actor = objects[pick_name]
            target_actor = objects[target_name]

            # Dynamic lift height scales with stack progress
            cube_height = (raw.cube_half_size[2] * 2).item()
            lift_height = max(0.1, (i + 2) * cube_height + 0.05)

            logger.info(f"Step {i+1}/{total_steps}: picking {pick_name}...")
            recorder.set_skill(f"pick({pick_name})")
            pick_result = ctx.pick(pick_name, lift_height=lift_height)

            if not pick_result.success:
                logger.warning(
                    f"Step {i+1}/{total_steps} FAILED: {pick_result.failure_reason}"
                )
                self._save_recording(recorder, seed)
                return SolverResult(
                    success=False,
                    info={"cubes_stacked": i},
                    failure_reason=pick_result.failure_reason,
                )

            # Compute release pose: above target at lift height
            goal_pose = target_actor.pose * sapien.Pose([0, 0, cube_height])
            offset = (goal_pose.p - pick_actor.pose.p).cpu().numpy()[0]
            release_p = pick_result.lift_pose.p + offset
            release_q = pick_result.lift_pose.q

            logger.info(f"Step {i+1}/{total_steps}: placing {pick_name} on {target_name}...")
            recorder.set_skill(f"place({pick_name},{target_name})")
            place_result = ctx.place(
                (release_p, release_q),
                retract_height=pick_result.lift_pose.p[2],
            )

            if not place_result.success:
                logger.warning(
                    f"Step {i+1}/{total_steps} FAILED: {place_result.failure_reason}"
                )
                self._save_recording(recorder, seed)
                return SolverResult(
                    success=False,
                    info={"cubes_stacked": i},
                    failure_reason=place_result.failure_reason,
                )

            # Verify placement (task-specific: check cube Z-height)
            expected_z = (target_actor.pose.p[..., 2] + cube_height).cpu().numpy().item()
            actual_z = pick_actor.pose.p[..., 2].cpu().numpy().item()
            if abs(actual_z - expected_z) > 0.01:
                logger.warning(
                    f"Placement check failed: expected_z={expected_z:.4f}, "
                    f"actual_z={actual_z:.4f}, diff={abs(actual_z - expected_z):.4f}"
                )
                self._save_recording(recorder, seed)
                return SolverResult(
                    success=False,
                    info={"cubes_stacked": i},
                    failure_reason="placement_check_failed",
                )

            logger.info(f"Step {i+1}/{total_steps} complete")

        # Settle: step until success or timeout
        recorder.set_skill("settle")
        rc = ctx.robot_config
        max_settle = 100
        for step in range(max_settle):
            actuate_gripper(env, ctx.planner, rc.gripper_open, steps=1,
                            step_callback=recorder.record)
            info = raw.evaluate()
            if info["success"].item():
                logger.debug("Settled after %d steps", step)
                break

        # Save state recording
        self._save_recording(recorder, seed)

        info = raw.evaluate()
        success = bool(info["success"].item())
        elapsed = int(info["elapsed_steps"])

        if not success:
            logger.warning("Stacking complete but env reports failure")

        logger.info(f"Stacking complete: {total_steps}/{total_steps} cubes stacked")
        return SolverResult(
            success=success,
            elapsed_steps=elapsed,
            info={"cubes_stacked": total_steps},
        )

    def _save_recording(self, recorder, seed):
        """Save state recording to the data/ directory."""
        recorder.save(f"data/episode_seed{seed}.npz")
