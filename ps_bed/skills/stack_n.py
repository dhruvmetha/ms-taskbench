"""Sequential N-cube stacking skill using motion planning.

StackNSkill extends PickPlaceSkill to stack N cubes into a tower using
N-1 sequential pick-place operations with dynamic stack-top targeting,
grasp verification, placement verification, and settling steps.
"""

import logging

import numpy as np
import sapien
from transforms3d.euler import euler2quat

from mani_skill.examples.motionplanning.base_motionplanner.utils import (
    compute_grasp_info_by_obb,
    get_actor_obb,
)

from ps_bed.skills.pick_place import PickPlaceSkill, _sapien_to_mplib_pose

logger = logging.getLogger("ps_bed.skills.stack_n")


class StackNSkill(PickPlaceSkill):
    """Sequential N-cube stacking using motion-planned pick-place primitives.

    Inherits all motion planning primitives from PickPlaceSkill and adds
    a sequential stacking loop that:
    - Picks cubes[i+1] and places on cubes[i] for i=0..N-2
    - Verifies grasp success using is_grasping check
    - Uses dynamic lift heights that scale with stack progress
    - Verifies placement accuracy after physics settling
    - Aborts immediately on any failure with detailed info
    """

    def _pick_and_stack(
        self, env, planner, cube_to_pick, target_cube, step_index, total_steps
    ):
        """Execute one pick-and-place operation to stack cube_to_pick on target_cube.

        Args:
            env: The gym environment (num_envs=1, pd_joint_pos control)
            planner: mplib.Planner instance
            cube_to_pick: The cube actor to grasp and lift
            target_cube: The cube actor to place on (stack top)
            step_index: Current step number (0-indexed)
            total_steps: Total number of pick-place steps (N-1)

        Returns:
            (obs, reward, terminated, truncated, info) tuple on success
            None on failure (failure_reason stored in class for retrieval)
        """
        raw = env.unwrapped
        cube_index = step_index + 1  # cube_to_pick is cubes[step_index+1]

        logger.info(f"Picking cube_{cube_index}...")

        # Compute grasp pose from OBB
        obb = get_actor_obb(cube_to_pick)
        approaching = np.array([0, 0, -1])
        target_closing = (
            raw.agent.tcp.pose.to_transformation_matrix()[0, :3, 1].cpu().numpy()
        )
        grasp_info = compute_grasp_info_by_obb(
            obb,
            approaching=approaching,
            target_closing=target_closing,
            depth=self.FINGER_LENGTH,
        )
        closing, center = grasp_info["closing"], grasp_info["center"]
        grasp_pose = raw.agent.build_grasp_pose(approaching, closing, center)

        # Search for collision-free grasp orientation
        angles = np.arange(0, np.pi * 2 / 3, np.pi / 2)
        angles = np.repeat(angles, 2)
        angles[1::2] *= -1

        grasp_found = False
        for angle in angles:
            delta_pose = sapien.Pose(q=euler2quat(0, 0, angle))
            candidate = grasp_pose * delta_pose
            res = self._move_to_pose_with_screw(
                env, planner, candidate, self.GRIPPER_OPEN, dry_run=True
            )
            if res == -1:
                continue
            grasp_pose = candidate
            grasp_found = True
            break

        if not grasp_found:
            self._failure_reason = "grasp_plan_failed"
            logger.warning(
                f"Step {step_index+1}/{total_steps} FAILED: grasp_plan_failed for cube_{cube_index}"
            )
            return None

        # Reach phase: approach from 0.05m behind grasp pose
        reach_pose = grasp_pose * sapien.Pose([0, 0, -0.05])
        res = self._move_to_pose_with_screw(env, planner, reach_pose, self.GRIPPER_OPEN)
        if res == -1:
            self._failure_reason = "reach_plan_failed"
            logger.warning(
                f"Step {step_index+1}/{total_steps} FAILED: reach_plan_failed for cube_{cube_index}"
            )
            return None

        # Grasp phase: move to grasp pose, close gripper
        res = self._move_to_pose_with_screw(env, planner, grasp_pose, self.GRIPPER_OPEN)
        if res == -1:
            self._failure_reason = "grasp_move_failed"
            logger.warning(
                f"Step {step_index+1}/{total_steps} FAILED: grasp_move_failed for cube_{cube_index}"
            )
            return None

        obs, reward, terminated, truncated, info = self._actuate_gripper(
            env, planner, self.GRIPPER_CLOSED
        )

        # Verify grasp
        is_holding = raw.agent.is_grasping(cube_to_pick)
        # is_holding is batched tensor shape (1,) - extract scalar bool
        if not bool(is_holding.cpu().numpy().item()):
            self._failure_reason = "grasp_verification_failed"
            logger.warning(
                f"Step {step_index+1}/{total_steps} FAILED: grasp_verification_failed for cube_{cube_index}"
            )
            return None

        logger.info(f"Placing on cube_{step_index}...")

        # Lift phase: dynamic lift height scales with stack progress
        cube_height = (raw.cube_half_size[2] * 2).item()
        lift_z = max(0.1, (step_index + 2) * cube_height + 0.05)
        lift_pose = sapien.Pose([0, 0, lift_z]) * grasp_pose

        res = self._move_to_pose_with_screw(env, planner, lift_pose, self.GRIPPER_CLOSED)
        if res == -1:
            self._failure_reason = "lift_plan_failed"
            logger.warning(
                f"Step {step_index+1}/{total_steps} FAILED: lift_plan_failed for cube_{cube_index}"
            )
            return None

        # Place phase: dynamic target from target_cube's current physics pose
        goal_pose = target_cube.pose * sapien.Pose([0, 0, cube_height])
        offset = (goal_pose.p - cube_to_pick.pose.p).cpu().numpy()[0]
        align_pose = sapien.Pose(lift_pose.p + offset, lift_pose.q)

        res = self._move_to_pose_with_screw(env, planner, align_pose, self.GRIPPER_CLOSED)
        if res == -1:
            self._failure_reason = "place_plan_failed"
            logger.warning(
                f"Step {step_index+1}/{total_steps} FAILED: place_plan_failed for cube_{cube_index}"
            )
            return None

        # Release phase: open gripper
        obs, reward, terminated, truncated, info = self._actuate_gripper(
            env, planner, self.GRIPPER_OPEN
        )

        # Settling steps: let physics settle before next pick
        obs, reward, terminated, truncated, info = self._actuate_gripper(
            env, planner, self.GRIPPER_OPEN, steps=10
        )

        # Placement verification: check cube is at expected z-position
        expected_z = (target_cube.pose.p[..., 2] + cube_height).cpu().numpy().item()
        actual_z = cube_to_pick.pose.p[..., 2].cpu().numpy().item()
        z_threshold = 0.01  # half a cube height tolerance

        if abs(actual_z - expected_z) > z_threshold:
            self._failure_reason = "placement_check_failed"
            logger.warning(
                f"Step {step_index+1}/{total_steps} FAILED: placement_check_failed for cube_{cube_index} "
                f"(expected_z={expected_z:.4f}, actual_z={actual_z:.4f}, diff={abs(actual_z - expected_z):.4f})"
            )
            return None

        logger.info(f"Step {step_index+1}/{total_steps} complete")
        return obs, reward, terminated, truncated, info

    def solve(self, env, seed=None):
        """Stack N cubes into a tower using N-1 sequential pick-place operations.

        Args:
            env: The gym environment (num_envs=1, pd_joint_pos control)
            seed: Random seed for env reset

        Returns:
            (obs, reward, terminated, truncated, info) tuple where:
            - obs is always a valid observation (never None)
            - info dict includes:
                - cubes_stacked: int, number of cubes successfully stacked
                - failure_reason: str, present only on failure
                - success: bool, from env.evaluate()
        """
        env.reset(seed=seed)
        assert env.unwrapped.control_mode in [
            "pd_joint_pos",
            "pd_joint_pos_vel",
        ], f"Unsupported control mode: {env.unwrapped.control_mode}"

        planner = self._setup_planner(env)
        raw = env.unwrapped
        cubes = raw.cubes
        n = len(cubes)

        logger.info(f"Starting sequential stacking: {n} cubes, {n-1} pick-place steps")

        # Loop: pick cubes[i+1], place on cubes[i]
        for i in range(n - 1):
            self._failure_reason = None
            result = self._pick_and_stack(
                env, planner, cubes[i + 1], cubes[i], step_index=i, total_steps=n - 1
            )

            if result is None:
                # Failure occurred - get current observation
                robot = raw.agent.robot
                qpos = robot.get_qpos()[0, : len(planner.joint_vel_limits)].cpu().numpy()
                control_mode = raw.control_mode
                if control_mode == "pd_joint_pos_vel":
                    action = np.hstack([qpos, qpos * 0, self.GRIPPER_OPEN])
                else:
                    action = np.hstack([qpos, self.GRIPPER_OPEN])
                obs, _, _, _, base_info = env.step(action)

                # Build failure info
                info = raw.evaluate()
                info["cubes_stacked"] = i  # number successfully stacked so far
                info["failure_reason"] = self._failure_reason

                logger.warning(f"Stacking aborted: {i}/{n-1} cubes stacked")
                return obs, 0.0, False, False, info

        # Success: all N-1 operations completed
        obs, reward, terminated, truncated, info = result
        info["cubes_stacked"] = n - 1

        logger.info(f"Stacking complete: {n-1}/{n-1} cubes stacked")
        return obs, reward, terminated, truncated, info
