"""State recorder for capturing simulation state at control frequency (20 Hz).

Usage with any solver::

    from ps_bed.recorder import StateRecorder

    recorder = StateRecorder(
        env,
        objects={"cube_0": cube0, "cube_1": cube1},
        robot_fields=["qpos", "tcp_pos", "tcp_quat", "gripper_qpos"],
    )
    recorder.record()  # initial state

    # Pass recorder.record as step_callback to any skill
    pick(env, planner, obj, step_callback=recorder.record)
    place(env, planner, pose, step_callback=recorder.record)

    recorder.save("data/episode.npz")

Available robot_fields:
    - ``qpos``         — all joint positions (arm + fingers)
    - ``qvel``         — all joint velocities
    - ``tcp_pos``      — end-effector position (3,)
    - ``tcp_quat``     — end-effector orientation (4,)
    - ``gripper_qpos`` — finger joint positions (2,)
"""

import logging
import os
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("ps_bed.recorder")

# Each extractor takes (raw_env,) and returns a numpy array
_ROBOT_FIELD_EXTRACTORS = {
    "qpos": lambda raw: raw.agent.robot.get_qpos()[0].cpu().numpy(),
    "qvel": lambda raw: raw.agent.robot.get_qvel()[0].cpu().numpy(),
    "tcp_pos": lambda raw: raw.agent.tcp.pose.p[0].cpu().numpy(),
    "tcp_quat": lambda raw: raw.agent.tcp.pose.q[0].cpu().numpy(),
    "gripper_qpos": lambda raw: raw.agent.robot.get_qpos()[0].cpu().numpy()[-2:],
}


class StateRecorder:
    """Records simulation state at every control step.

    Args:
        env: Gym env (raw or wrapped — accesses ``env.unwrapped``).
        objects: Dict mapping name → SAPIEN actor to track poses of.
            If None, no object poses are recorded.
        robot_fields: List of robot state fields to record.
            See module docstring for available fields.
            If None, nothing about the robot is recorded.
    """

    def __init__(
        self,
        env,
        objects: Optional[Dict[str, object]] = None,
        robot_fields: Optional[List[str]] = None,
    ):
        self.env = env
        self.raw = env.unwrapped
        self.objects = objects or {}
        self.robot_fields = robot_fields or []
        self.frames = []
        self._skill = ""

        # Validate robot fields
        for field in self.robot_fields:
            if field not in _ROBOT_FIELD_EXTRACTORS:
                available = ", ".join(sorted(_ROBOT_FIELD_EXTRACTORS))
                raise ValueError(
                    f"Unknown robot field {field!r}. Available: {available}"
                )

    def set_skill(self, label):
        """Set the current skill label stamped on subsequent frames.

        Args:
            label: String like ``"pick(cube_1)"`` or ``"settle"``.
        """
        self._skill = label

    def record(self):
        """Capture one frame of state. Call after every env.step()."""
        raw = self.raw
        frame = {"skill": self._skill}

        # Robot fields
        for field in self.robot_fields:
            frame[field] = _ROBOT_FIELD_EXTRACTORS[field](raw)

        # Tracked object poses
        for name, actor in self.objects.items():
            frame[f"{name}_pos"] = actor.pose.p[0].cpu().numpy()
            frame[f"{name}_quat"] = actor.pose.q[0].cpu().numpy()

        self.frames.append(frame)

    def save(self, path):
        """Save all recorded frames to a compressed .npz file.

        Each key becomes an array of shape ``(num_frames, ...)``.
        Also stores ``num_frames`` and ``control_freq`` as scalars.
        """
        if not self.frames:
            logger.warning("No frames recorded, skipping save")
            return

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        arrays = {}
        for key in self.frames[0]:
            if key == "skill":
                arrays[key] = np.array([f[key] for f in self.frames])
            else:
                arrays[key] = np.stack([f[key] for f in self.frames])

        arrays["num_frames"] = np.array(len(self.frames))
        arrays["control_freq"] = np.array(20)

        np.savez_compressed(path, **arrays)
        logger.info("Saved %d frames to %s", len(self.frames), path)

    def clear(self):
        """Discard all recorded frames."""
        self.frames = []
