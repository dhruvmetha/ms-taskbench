"""Unified cube-stacking solver using pick/place primitives.

Replaces both the 2-cube and N-cube solvers with a single solver that
loops over ``pick()`` / ``place()`` calls.
The 2-cube case (``StackCube-v1``) is just ``n=2``.
"""

import logging

import numpy as np
import sapien

from ps_bed.recorder import StateRecorder
from ps_bed.skills.motion import (
    GRIPPER_OPEN,
    actuate_gripper,
    attach_object,
    detach_object,
    setup_planner,
)
from ps_bed.skills.primitives import pick, place
from ps_bed.solvers.base import BaseSolver

logger = logging.getLogger("ps_bed.solvers.stack_cubes")


class StackCubesSolver(BaseSolver):
    """Stack N cubes into a tower using sequential pick-place primitives."""

    def _get_cube_list(self, env):
        """Return ordered cube list [base, ..., top] for any supported env.

        Handles:
        - StackNCube-v1: ``raw.cubes`` list (cube_0 is base)
        - StackCube-v1 / StackCubeDistractor-v1: ``[cubeB, cubeA]``
          (cubeB is the green base, cubeA is the red cube to stack)
        """
        raw = env.unwrapped
        if hasattr(raw, "cubes"):
            return raw.cubes
        # StackCube-v1 convention: cubeA goes on top of cubeB
        return [raw.cubeB, raw.cubeA]

    def solve(self, env, seed=None):
        """Stack all cubes into a tower using N-1 pick-place operations."""
        env.reset(seed=seed)
        assert env.unwrapped.control_mode in [
            "pd_joint_pos",
            "pd_joint_pos_vel",
        ], f"Unsupported control mode: {env.unwrapped.control_mode}"

        planner = setup_planner(env)
        raw = env.unwrapped
        cubes = list(self._get_cube_list(env))
        rng = np.random.default_rng(seed)
        rng.shuffle(cubes)
        n = len(cubes)
        total_steps = n - 1

        # Set up state recorder
        objects = {f"cube_{i}": cube for i, cube in enumerate(cubes)}
        recorder = StateRecorder(
            env,
            objects=objects,
            robot_fields=["qpos", "tcp_pos", "tcp_quat", "gripper_qpos"],
        )
        recorder.record()  # initial state

        logger.info(f"Starting sequential stacking: {n} cubes, {total_steps} pick-place steps (seed={seed})")

        for i in range(total_steps):
            cube_to_pick = cubes[i + 1]
            target_cube = cubes[i]

            # Dynamic lift height scales with stack progress
            cube_height = (raw.cube_half_size[2] * 2).item()
            lift_height = max(0.1, (i + 2) * cube_height + 0.05)

            logger.info(f"Step {i+1}/{total_steps}: picking cube_{i+1}...")
            recorder.set_skill(f"pick(cube_{i+1})")
            pick_result = pick(env, planner, cube_to_pick, lift_height=lift_height,
                               step_callback=recorder.record)

            if not pick_result.success:
                logger.warning(
                    f"Step {i+1}/{total_steps} FAILED: {pick_result.failure_reason}"
                )
                return self._finish(env, planner, recorder, seed,
                                    cubes_stacked=i, reason=pick_result.failure_reason)

            # Tell planner about the held object for collision-aware planning
            attach_object(planner, pick_result.obj_size)

            # Compute release pose: above target_cube at lift height
            goal_pose = target_cube.pose * sapien.Pose([0, 0, cube_height])
            offset = (goal_pose.p - cube_to_pick.pose.p).cpu().numpy()[0]
            release_pose = sapien.Pose(
                pick_result.lift_pose.p + offset, pick_result.lift_pose.q
            )

            logger.info(f"Step {i+1}/{total_steps}: placing on cube_{i}...")
            recorder.set_skill(f"place(cube_{i+1},cube_{i})")
            place_result = place(
                env, planner, release_pose,
                retract_height=pick_result.lift_pose.p[2],
                step_callback=recorder.record,
            )

            # Object released — remove from planner
            detach_object(planner)

            if not place_result.success:
                logger.warning(
                    f"Step {i+1}/{total_steps} FAILED: {place_result.failure_reason}"
                )
                return self._finish(env, planner, recorder, seed,
                                    cubes_stacked=i, reason=place_result.failure_reason)

            # Verify placement (task-specific: check cube Z-height)
            expected_z = (target_cube.pose.p[..., 2] + cube_height).cpu().numpy().item()
            actual_z = cube_to_pick.pose.p[..., 2].cpu().numpy().item()
            if abs(actual_z - expected_z) > 0.01:
                logger.warning(
                    f"Placement check failed: expected_z={expected_z:.4f}, "
                    f"actual_z={actual_z:.4f}, diff={abs(actual_z - expected_z):.4f}"
                )
                return self._finish(env, planner, recorder, seed,
                                    cubes_stacked=i, reason="placement_check_failed")

            logger.info(f"Step {i+1}/{total_steps} complete")

        # Settle: step until success or timeout
        recorder.set_skill("settle")
        max_settle = 100
        for step in range(max_settle):
            actuate_gripper(env, planner, GRIPPER_OPEN, steps=1,
                            step_callback=recorder.record)
            info = raw.evaluate()
            if info["success"].item():
                logger.debug("Settled after %d steps", step)
                break

        # Save state recording
        self._save_recording(recorder, seed)

        obs, reward, terminated, truncated, _ = place_result.step_result
        info = raw.evaluate()
        info["cubes_stacked"] = total_steps

        if not info["success"].item():
            logger.warning("Stacking complete but env reports failure")

        logger.info(f"Stacking complete: {total_steps}/{total_steps} cubes stacked")
        return obs, reward, terminated, truncated, info

    def _save_recording(self, recorder, seed):
        """Save state recording to the data/ directory."""
        recorder.save(f"data/episode_seed{seed}.npz")

    def _finish(self, env, planner, recorder, seed, cubes_stacked, reason):
        """Save recording and build failure result."""
        self._save_recording(recorder, seed)
        return self._make_failure_result(env, planner, cubes_stacked, reason)

    def _make_failure_result(self, env, planner, cubes_stacked, reason):
        """Build a valid (obs, reward, terminated, truncated, info) on failure."""
        raw = env.unwrapped
        robot = raw.agent.robot
        qpos = robot.get_qpos()[0, : len(planner.joint_vel_limits)].cpu().numpy()
        control_mode = raw.control_mode
        if control_mode == "pd_joint_pos_vel":
            action = np.hstack([qpos, qpos * 0, GRIPPER_OPEN])
        else:
            action = np.hstack([qpos, GRIPPER_OPEN])
        obs, _, _, _, _ = env.step(action)

        info = raw.evaluate()
        info["cubes_stacked"] = cubes_stacked
        info["failure_reason"] = reason

        logger.warning(f"Stacking aborted: {cubes_stacked} cubes stacked")
        return obs, 0.0, False, False, info
