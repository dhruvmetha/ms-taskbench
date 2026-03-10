"""Low-level motion planning helpers using mplib 0.2.x.

All functions are module-level (no class state) and operate on a raw
gym env with ``num_envs=1`` and ``sim_backend="cpu"``.
"""

from __future__ import annotations

import logging

import mplib
import numpy as np
import sapien

logger = logging.getLogger("ps_bed.skills.motion")

FINGER_LENGTH = 0.025
GRIPPER_OPEN = 1.0
GRIPPER_CLOSED = -1.0
MOVE_GROUP = "panda_hand_tcp"


def sapien_to_mplib_pose(pose: sapien.Pose) -> mplib.pymp.Pose:
    """Convert a SAPIEN Pose to an mplib Pose (handles batched tensors)."""
    p = np.asarray(pose.p, dtype=np.float64).flatten()[:3]
    q = np.asarray(pose.q, dtype=np.float64).flatten()[:4]
    return mplib.pymp.Pose(p=p, q=q)


def _add_table_collision(env, planner):
    """Add the table surface as a point cloud collision object."""
    import sapien.physx as physx

    raw = env.unwrapped
    for actor in raw.scene.get_all_actors():
        if "table" not in actor.name:
            continue
        comp = actor.find_component_by_type(physx.PhysxRigidDynamicComponent)
        if comp is None:
            comp = actor.find_component_by_type(physx.PhysxRigidStaticComponent)
        if comp is None:
            continue
        shape = comp.get_collision_shapes()[0]
        half = np.asarray(shape.half_size, dtype=np.float64)
        # Table top in world frame
        world_pose = actor.pose * shape.get_local_pose()
        center = np.asarray(world_pose.p, dtype=np.float64).flatten()
        top_z = center[2] + half[2]
        # Place points slightly below the true surface so that grasps
        # near the table remain feasible (the planner inflates obstacles
        # by the collision margin, so exact z=0 blocks nearby IK).
        table_z = top_z - 0.02
        # Generate grid of points on table surface
        xs = np.linspace(center[0] - half[0], center[0] + half[0], 50)
        ys = np.linspace(center[1] - half[1], center[1] + half[1], 50)
        xx, yy = np.meshgrid(xs, ys)
        zz = np.full_like(xx, table_z)
        points = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=-1)
        planner.update_point_cloud(points, resolution=0.02, name="table")
        logger.debug(
            "Added table collision: %d points at z=%.4f", len(points), top_z
        )
        return
    logger.warning("No table actor found in scene")


def add_collision_boxes(planner, boxes, resolution=0.01):
    """Add box obstacles to the planner as point clouds.

    Args:
        planner: mplib.Planner instance.
        boxes: List of (name, center, half_size) tuples, e.g. from
            ``env.unwrapped.get_collision_boxes()``.
        resolution: Point spacing on box surfaces (meters).
    """
    for name, center, half_size in boxes:
        center = np.asarray(center, dtype=np.float64)
        hs = np.asarray(half_size, dtype=np.float64)
        points = _box_surface_points(center, hs, resolution)
        planner.update_point_cloud(points, resolution=resolution, name=name)
        logger.debug("Added collision box '%s': %d points", name, len(points))


def _box_surface_points(center, half_size, res):
    """Generate a point cloud covering the 6 faces of an axis-aligned box."""
    cx, cy, cz = center
    hx, hy, hz = half_size
    faces = []

    # +/- X faces
    ys = np.arange(cy - hy, cy + hy + res, res)
    zs = np.arange(cz - hz, cz + hz + res, res)
    yy, zz = np.meshgrid(ys, zs)
    for sign in [+1, -1]:
        xx = np.full_like(yy, cx + sign * hx)
        faces.append(np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=-1))

    # +/- Y faces
    xs = np.arange(cx - hx, cx + hx + res, res)
    zs = np.arange(cz - hz, cz + hz + res, res)
    xx, zz = np.meshgrid(xs, zs)
    for sign in [+1, -1]:
        yy = np.full_like(xx, cy + sign * hy)
        faces.append(np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=-1))

    # +/- Z faces
    xs = np.arange(cx - hx, cx + hx + res, res)
    ys = np.arange(cy - hy, cy + hy + res, res)
    xx, yy = np.meshgrid(xs, ys)
    for sign in [+1, -1]:
        zz = np.full_like(xx, cz + sign * hz)
        faces.append(np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=-1))

    return np.concatenate(faces, axis=0)


def setup_planner(env) -> mplib.Planner:
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
        move_group=MOVE_GROUP,
    )

    base_pose = sapien_to_mplib_pose(agent.robot.pose)
    planner.set_base_pose(base_pose)

    planner.joint_vel_limits = np.asarray(planner.joint_vel_limits) * 0.9
    planner.joint_acc_limits = np.asarray(planner.joint_acc_limits) * 0.9

    _add_table_collision(env, planner)

    return planner


GRIPPER_LINK_NAMES = {"panda_hand", "panda_leftfinger", "panda_rightfinger"}


def _get_gripper_contacts(env):
    """Return contacts involving gripper links (hand + fingers).

    Returns a list of ``(contact, gripper_link_name, other_entity_name)``
    tuples for any contact where a gripper link touches a non-robot entity.
    """
    raw = env.unwrapped
    robot_link_names = {link.get_name() for link in raw.agent.robot.get_links()}

    results = []
    for contact in raw.scene.px.get_contacts():
        names = [contact.bodies[i].entity.name for i in range(2)]
        for idx in range(2):
            if names[idx] in GRIPPER_LINK_NAMES and names[1 - idx] not in robot_link_names:
                results.append((contact, names[idx], names[1 - idx]))
    return results


def follow_path(env, result, gripper_state, refine_steps=0,
                monitor_contacts=False, step_callback=None):
    """Execute a planned path, returning the last step result.

    Args:
        monitor_contacts: If True, log warnings when gripper fingers
            contact non-robot objects during trajectory execution.
        step_callback: Optional callable invoked after each env.step()
            (e.g. ``env.render_human`` for live viewer updates).
    """
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

        if step_callback is not None:
            step_callback()

        if monitor_contacts:
            for contact, finger, other in _get_gripper_contacts(env):
                force = sum(
                    np.linalg.norm(pt.impulse) for pt in contact.points
                ) / env.unwrapped.control_timestep
                if force > 0.01:  # low threshold to catch brushing contacts
                    logger.warning(
                        "Collision at step %d/%d: %s -> %s (%.2f N), aborting",
                        i, n_step, finger, other, force,
                    )
                    return -1
    return obs, reward, terminated, truncated, info


def actuate_gripper(env, planner, gripper_state, steps=6, step_callback=None):
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
        if step_callback is not None:
            step_callback()
    return obs, reward, terminated, truncated, info


def attach_object(planner, size, pose=None):
    """Tell the planner a box is attached to the end effector.

    Args:
        planner: mplib.Planner instance.
        size: (3,) array-like — full extents (x, y, z) of the box.
        pose: mplib.pymp.Pose — relative pose from the end-effector link
            to the object center.  Defaults to identity (centered on TCP).
    """
    if pose is None:
        pose = mplib.pymp.Pose()
    planner.update_attached_box(size, pose)
    logger.debug("Attached box (%.3f, %.3f, %.3f) to end effector", *size)


def detach_object(planner):
    """Remove the attached object from the planner."""
    planner.detach_object("attached_geom", also_remove=True)
    logger.debug("Detached object from end effector")


def move_to_pose(env, planner, pose, gripper_state, dry_run=False,
                  monitor_contacts=False, step_callback=None):
    """Plan and execute a motion to target pose.

    Tries ``plan_screw()`` first (greedy Cartesian interpolation).
    On failure, falls back to ``plan_pose()`` (OMPL RRTConnect with
    obstacle avoidance).

    Returns -1 on planning failure, the plan dict if dry_run=True,
    or the last (obs, reward, terminated, truncated, info) tuple.
    """
    goal = sapien_to_mplib_pose(pose)
    current_qpos = env.unwrapped.agent.robot.get_qpos().cpu().numpy()[0]
    result = planner.plan_screw(
        goal,
        current_qpos,
        time_step=env.unwrapped.control_timestep,
    )
    if result["status"] != "Success":
        logger.debug("plan_screw failed (%s), falling back to plan_pose (RRTConnect)", result["status"])
        result = planner.plan_pose(
            goal,
            current_qpos,
            time_step=env.unwrapped.control_timestep,
        )
        if result["status"] != "Success":
            logger.warning("Both plan_screw and plan_pose failed: %s", result["status"])
            return -1
        logger.debug("plan_pose succeeded")
    if dry_run:
        return result
    return follow_path(env, result, gripper_state,
                       monitor_contacts=monitor_contacts,
                       step_callback=step_callback)
