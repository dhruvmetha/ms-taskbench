"""Reusable manipulation skills.

Three task-agnostic skills built on the low-level helpers in ``motion.py``:

- ``move(target_pose)`` — move the arm to a pose (base primitive).
- ``pick(obj)`` — grasp an object and lift it (uses ``move`` internally).
- ``place(target_pose)`` — release the held object and retract (uses ``move`` internally).
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sapien
from transforms3d.euler import euler2quat

from mani_skill.examples.motionplanning.base_motionplanner.utils import (
    compute_grasp_info_by_obb,
    get_actor_obb,
)

from ps_bed.skills.motion import (
    FINGER_LENGTH,
    GRIPPER_CLOSED,
    GRIPPER_OPEN,
    actuate_gripper,
    move_to_pose,
)

logger = logging.getLogger("ps_bed.skills.primitives")


@dataclass
class MoveResult:
    success: bool
    failure_reason: Optional[str] = None
    step_result: Optional[tuple] = None


def move(env, planner, target_pose, *, gripper_open=True,
         monitor_contacts=True, step_callback=None) -> MoveResult:
    """Move the arm to target_pose.

    Args:
        env: Raw gym env (num_envs=1, cpu backend).
        planner: mplib.Planner instance.
        target_pose: sapien.Pose to move the end effector to.
        gripper_open: Gripper state during motion (default open).
        monitor_contacts: Abort on collision during execution (default True).
        step_callback: Optional callable invoked after each env.step().

    Returns:
        MoveResult with success status.
    """
    gripper_state = GRIPPER_OPEN if gripper_open else GRIPPER_CLOSED
    res = move_to_pose(env, planner, target_pose, gripper_state,
                       monitor_contacts=monitor_contacts,
                       step_callback=step_callback)
    if res == -1:
        return MoveResult(success=False, failure_reason="move_plan_failed")
    return MoveResult(success=True, step_result=res)


@dataclass
class PickResult:
    success: bool
    failure_reason: Optional[str] = None
    grasp_pose: Optional[sapien.Pose] = None
    lift_pose: Optional[sapien.Pose] = None
    obj_size: Optional[np.ndarray] = None
    step_result: Optional[tuple] = None


@dataclass
class PlaceResult:
    success: bool
    failure_reason: Optional[str] = None
    step_result: Optional[tuple] = None


def pick(env, planner, obj, *, lift_height=0.1, verify_grasp=True,
         step_callback=None) -> PickResult:
    """Pick up an object: compute grasp, reach, grasp, verify, lift.

    Args:
        env: Raw gym env (num_envs=1, cpu backend).
        planner: mplib.Planner instance.
        obj: SAPIEN actor to grasp.
        lift_height: Height above grasp pose to lift to.
        verify_grasp: If True, check ``agent.is_grasping()`` after closing.
        step_callback: Optional callable invoked after each env.step().

    Returns:
        PickResult with ``lift_pose`` (useful for computing release poses).
    """
    raw = env.unwrapped

    # Compute grasp pose from OBB
    obb = get_actor_obb(obj)
    obj_size = np.asarray(obb.extents, dtype=np.float64)
    approaching = np.array([0, 0, -1])
    target_closing = (
        raw.agent.tcp.pose.to_transformation_matrix()[0, :3, 1].cpu().numpy()
    )
    grasp_info = compute_grasp_info_by_obb(
        obb,
        approaching=approaching,
        target_closing=target_closing,
        depth=FINGER_LENGTH,
    )
    closing, center = grasp_info["closing"], grasp_info["center"]
    grasp_pose = raw.agent.build_grasp_pose(approaching, closing, center)

    # Search 6 rotation candidates for collision-free orientation
    angles = np.arange(0, np.pi * 2 / 3, np.pi / 2)
    angles = np.repeat(angles, 2)
    angles[1::2] *= -1

    grasp_found = False
    for angle in angles:
        delta_pose = sapien.Pose(q=euler2quat(0, 0, angle))
        candidate = grasp_pose * delta_pose
        res = move_to_pose(env, planner, candidate, GRIPPER_OPEN, dry_run=True)
        if res == -1:
            continue
        grasp_pose = candidate
        grasp_found = True
        break

    if not grasp_found:
        logger.warning("Failed to find a valid grasp pose")
        return PickResult(success=False, failure_reason="grasp_plan_failed")

    # Reach: approach from 0.05m behind grasp pose
    reach_pose = grasp_pose * sapien.Pose([0, 0, -0.05])
    result = move(env, planner, reach_pose, step_callback=step_callback)
    if not result.success:
        return PickResult(success=False, failure_reason="reach_failed")

    # Grasp: move to grasp pose
    result = move(env, planner, grasp_pose, step_callback=step_callback)
    if not result.success:
        return PickResult(success=False, failure_reason="grasp_approach_failed")

    # Close gripper
    actuate_gripper(env, planner, GRIPPER_CLOSED, step_callback=step_callback)

    # Verify grasp
    if verify_grasp:
        is_holding = raw.agent.is_grasping(obj)
        if not bool(is_holding.cpu().numpy().item()):
            logger.warning("Grasp verification failed")
            return PickResult(success=False, failure_reason="grasp_verification_failed")

    # Lift (contacts off — gripper is holding the object)
    lift_pose = sapien.Pose([0, 0, lift_height]) * grasp_pose
    result = move(env, planner, lift_pose, gripper_open=False,
                  monitor_contacts=False, step_callback=step_callback)
    if not result.success:
        return PickResult(
            success=False,
            failure_reason="lift_failed",
            grasp_pose=grasp_pose,
        )

    return PickResult(
        success=True,
        grasp_pose=grasp_pose,
        lift_pose=lift_pose,
        obj_size=obj_size,
        step_result=result.step_result,
    )


def place(
    env,
    planner,
    target_pose,
    *,
    settling_steps=10,
    retract_height=None,
    step_callback=None,
) -> PlaceResult:
    """Move to target_pose, release the held object, and retract upward.

    Args:
        env: Raw gym env (num_envs=1, cpu backend).
        planner: mplib.Planner instance.
        target_pose: sapien.Pose where the gripper moves to before releasing.
        settling_steps: Steps to let physics settle after release.
        retract_height: Absolute Z height to retract to after release.
            If None, retracts 0.1m above the release pose.
        step_callback: Optional callable invoked after each env.step().

    Returns:
        PlaceResult with success status.
    """
    # Move to target pose (contacts off — gripper is holding an object)
    result = move(env, planner, target_pose, gripper_open=False,
                  monitor_contacts=False, step_callback=step_callback)
    if not result.success:
        return PlaceResult(success=False, failure_reason="place_move_failed")

    # Release gripper
    actuate_gripper(env, planner, GRIPPER_OPEN, step_callback=step_callback)

    # Settle
    actuate_gripper(env, planner, GRIPPER_OPEN, steps=settling_steps,
                    step_callback=step_callback)

    # Retract: move straight up to clear before next action
    if retract_height is None:
        retract_height = target_pose.p[2] + 0.1
    retract_pose = sapien.Pose(
        [target_pose.p[0], target_pose.p[1], retract_height],
        target_pose.q,
    )
    result = move(env, planner, retract_pose, step_callback=step_callback)
    if not result.success:
        logger.warning("Retract failed, continuing anyway")

    return PlaceResult(success=True, step_result=result.step_result)


@dataclass
class PushResult:
    success: bool
    failure_reason: Optional[str] = None
    step_result: Optional[tuple] = None


def push(env, planner, approach_pose, push_pose, *,
         clearance_height=0.1, lift_height=0.1,
         step_callback=None) -> PushResult:
    """Lift for clearance, close gripper, approach, sweep, lift, open.

    Args:
        env: Raw gym env (num_envs=1, cpu backend).
        planner: mplib.Planner instance.
        approach_pose: sapien.Pose to move to before pushing (no contact).
        push_pose: sapien.Pose to sweep toward (contact expected).
        clearance_height: Height to lift above current position before approaching.
        lift_height: Height to lift above push_pose after pushing.
        step_callback: Optional callable invoked after each env.step().

    Returns:
        PushResult with success status.
    """
    raw = env.unwrapped

    # Lift from current position for clearance
    tcp_pose = raw.agent.tcp.pose
    tcp_p = np.asarray(tcp_pose.p, dtype=np.float64).flatten()[:3]
    tcp_q = np.asarray(tcp_pose.q, dtype=np.float32).flatten()[:4]
    clearance_pose = sapien.Pose(
        np.array([tcp_p[0], tcp_p[1], tcp_p[2] + clearance_height], dtype=np.float32),
        tcp_q,
    )
    result = move(env, planner, clearance_pose, step_callback=step_callback)
    if not result.success:
        return PushResult(success=False, failure_reason="clearance_lift_failed")

    # Close gripper for flat push surface
    actuate_gripper(env, planner, GRIPPER_CLOSED, step_callback=step_callback)

    # Approach — closed gripper, contact monitoring on
    result = move(env, planner, approach_pose, gripper_open=False,
                  step_callback=step_callback)
    if not result.success:
        return PushResult(success=False, failure_reason="approach_failed")

    # Sweep — closed gripper, contact monitoring off (contact is intentional)
    result = move(env, planner, push_pose, gripper_open=False,
                  monitor_contacts=False, step_callback=step_callback)
    if not result.success:
        return PushResult(success=False, failure_reason="push_failed")

    # Lift to disengage — gripper stays closed to avoid snagging
    lift_pose = sapien.Pose(
        [push_pose.p[0], push_pose.p[1], push_pose.p[2] + lift_height],
        push_pose.q,
    )
    result = move(env, planner, lift_pose, gripper_open=False,
                  step_callback=step_callback)
    if not result.success:
        logger.warning("Push lift failed, continuing anyway")

    # Open gripper once clear
    actuate_gripper(env, planner, GRIPPER_OPEN, step_callback=step_callback)

    return PushResult(success=True, step_result=result.step_result)
