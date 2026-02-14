import mplib
import numpy as np
import sapien
from transforms3d.euler import euler2quat

from mani_skill.examples.motionplanning.base_motionplanner.utils import (
    compute_grasp_info_by_obb,
    get_actor_obb,
)


def _sapien_to_mplib_pose(pose: sapien.Pose) -> mplib.pymp.Pose:
    """Convert a SAPIEN Pose to an mplib Pose (handles batched tensors)."""
    p = np.asarray(pose.p, dtype=np.float64).flatten()[:3]
    q = np.asarray(pose.q, dtype=np.float64).flatten()[:4]
    return mplib.pymp.Pose(p=p, q=q)


class PickPlaceSkill:
    """Motion-planned pick-and-place for StackCube-v1 using mplib 0.2.x."""

    FINGER_LENGTH = 0.025
    GRIPPER_OPEN = 1.0
    GRIPPER_CLOSED = -1.0
    MOVE_GROUP = "panda_hand_tcp"

    def _setup_planner(self, env):
        """Create an mplib Planner from the env's robot."""
        raw = env.unwrapped
        agent = raw.agent
        robot = agent.robot

        link_names = [link.get_name() for link in robot.get_links()]
        joint_names = [joint.get_name() for joint in robot.get_active_joints()]

        planner = mplib.Planner(
            urdf=agent.urdf_path,
            srdf=agent.urdf_path.replace(".urdf", ".srdf"),
            user_link_names=link_names,
            user_joint_names=joint_names,
            move_group=self.MOVE_GROUP,
        )

        base_pose = _sapien_to_mplib_pose(agent.robot.pose)
        planner.set_base_pose(base_pose)

        planner.joint_vel_limits = (
            np.asarray(planner.joint_vel_limits) * 0.9
        )
        planner.joint_acc_limits = (
            np.asarray(planner.joint_acc_limits) * 0.9
        )
        return planner

    def _follow_path(self, env, result, gripper_state, refine_steps=0):
        """Execute a planned path, returning the last step result."""
        n_step = result["position"].shape[0]
        control_mode = env.unwrapped.control_mode
        for i in range(n_step + refine_steps):
            qpos = result["position"][min(i, n_step - 1)]
            if control_mode == "pd_joint_pos_vel":
                qvel = result["velocity"][min(i, n_step - 1)]
                action = np.hstack([qpos, qvel, gripper_state])
            else:
                action = np.hstack([qpos, gripper_state])
            obs, reward, terminated, truncated, info = env.step(action)
        return obs, reward, terminated, truncated, info

    def _actuate_gripper(self, env, planner, gripper_state, steps=6):
        """Open or close the gripper for a number of steps."""
        robot = env.unwrapped.agent.robot
        qpos = robot.get_qpos()[0, : len(planner.joint_vel_limits)].cpu().numpy()
        control_mode = env.unwrapped.control_mode
        for _ in range(steps):
            if control_mode == "pd_joint_pos_vel":
                action = np.hstack([qpos, qpos * 0, gripper_state])
            else:
                action = np.hstack([qpos, gripper_state])
            obs, reward, terminated, truncated, info = env.step(action)
        return obs, reward, terminated, truncated, info

    def _move_to_pose_with_screw(self, env, planner, pose, gripper_state, dry_run=False):
        """Plan and execute a screw motion to target pose."""
        goal = _sapien_to_mplib_pose(pose)
        current_qpos = env.unwrapped.agent.robot.get_qpos().cpu().numpy()[0]
        result = planner.plan_screw(
            goal,
            current_qpos,
            time_step=env.unwrapped.control_timestep,
        )
        if result["status"] != "Success":
            # Retry once
            result = planner.plan_screw(
                goal,
                current_qpos,
                time_step=env.unwrapped.control_timestep,
            )
            if result["status"] != "Success":
                print(f"Screw plan failed: {result['status']}")
                return -1
        if dry_run:
            return result
        return self._follow_path(env, result, gripper_state)

    def solve(self, env, seed=None):
        """Run a full grasp-lift-stack sequence on a *single* raw gym env.

        The env must use ``pd_joint_pos`` control mode and ``num_envs=1``.
        Returns the last ``(obs, reward, terminated, truncated, info)`` tuple.
        """
        env.reset(seed=seed)
        assert env.unwrapped.control_mode in [
            "pd_joint_pos",
            "pd_joint_pos_vel",
        ], f"Unsupported control mode: {env.unwrapped.control_mode}"

        planner = self._setup_planner(env)
        gripper_state = self.GRIPPER_OPEN

        raw = env.unwrapped
        obb = get_actor_obb(raw.cubeA)

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

        # Search for a collision-free grasp orientation
        angles = np.arange(0, np.pi * 2 / 3, np.pi / 2)
        angles = np.repeat(angles, 2)
        angles[1::2] *= -1
        for angle in angles:
            delta_pose = sapien.Pose(q=euler2quat(0, 0, angle))
            candidate = grasp_pose * delta_pose
            res = self._move_to_pose_with_screw(env, planner, candidate, gripper_state, dry_run=True)
            if res == -1:
                continue
            grasp_pose = candidate
            break
        else:
            print("Warning: failed to find a valid grasp pose")

        # Reach
        reach_pose = grasp_pose * sapien.Pose([0, 0, -0.05])
        self._move_to_pose_with_screw(env, planner, reach_pose, gripper_state)

        # Grasp
        self._move_to_pose_with_screw(env, planner, grasp_pose, gripper_state)
        gripper_state = self.GRIPPER_CLOSED
        self._actuate_gripper(env, planner, gripper_state)

        # Lift
        lift_pose = sapien.Pose([0, 0, 0.1]) * grasp_pose
        self._move_to_pose_with_screw(env, planner, lift_pose, gripper_state)

        # Stack on cubeB
        goal_pose = raw.cubeB.pose * sapien.Pose(
            [0, 0, (raw.cube_half_size[2] * 2).item()]
        )
        offset = (goal_pose.p - raw.cubeA.pose.p).cpu().numpy()[0]
        align_pose = sapien.Pose(lift_pose.p + offset, lift_pose.q)
        self._move_to_pose_with_screw(env, planner, align_pose, gripper_state)

        # Release
        gripper_state = self.GRIPPER_OPEN
        res = self._actuate_gripper(env, planner, gripper_state)
        return res
