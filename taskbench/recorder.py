"""State recorder for capturing simulation state at control frequency.

Saves demonstrations in HDF5 format with structured groups::

    episode.hdf5
    ├── metadata/          (attrs: control_freq, num_frames)
    ├── robot/
    │   ├── qpos           (num_frames, 9)
    │   ├── tcp_pos        (num_frames, 3)
    │   ├── tcp_quat       (num_frames, 4)
    │   └── gripper_qpos   (num_frames, 2)
    ├── objects/
    │   ├── cube_0/
    │   │   ├── pos        (num_frames, 3)
    │   │   └── quat       (num_frames, 4)
    │   └── cube_1/
    │       ├── pos        (num_frames, 3)
    │       └── quat       (num_frames, 4)
    └── skill              (num_frames,)  string labels

Usage::

    from taskbench.recorder import StateRecorder

    recorder = StateRecorder(
        env,
        objects={"cube_0": cube0, "cube_1": cube1},
        robot_fields=["qpos", "tcp_pos", "tcp_quat", "gripper_qpos"],
    )
    recorder.record()  # initial state

    # Pass recorder.record as step_callback to any skill
    ctx = SkillContext(env, step_callback=recorder.record)

    recorder.save("data/episode.hdf5")

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

import h5py
import numpy as np

logger = logging.getLogger("taskbench.recorder")

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
        """Save all recorded frames to an HDF5 file.

        Structure::

            /metadata          attrs: num_frames, control_freq
            /robot/<field>     (num_frames, ...) per robot field
            /objects/<name>/pos   (num_frames, 3)
            /objects/<name>/quat  (num_frames, 4)
            /skill             (num_frames,) string labels
        """
        if not self.frames:
            logger.warning("No frames recorded, skipping save")
            return

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        num_frames = len(self.frames)

        with h5py.File(path, "w") as f:
            # Metadata
            meta = f.create_group("metadata")
            meta.attrs["num_frames"] = num_frames
            meta.attrs["control_freq"] = self.raw.control_freq

            # Robot state
            if self.robot_fields:
                robot_grp = f.create_group("robot")
                for field in self.robot_fields:
                    data = np.stack([frame[field] for frame in self.frames])
                    robot_grp.create_dataset(field, data=data, compression="gzip")

            # Object poses
            if self.objects:
                obj_grp = f.create_group("objects")
                for name in self.objects:
                    name_grp = obj_grp.create_group(name)
                    pos = np.stack([frame[f"{name}_pos"] for frame in self.frames])
                    quat = np.stack([frame[f"{name}_quat"] for frame in self.frames])
                    name_grp.create_dataset("pos", data=pos, compression="gzip")
                    name_grp.create_dataset("quat", data=quat, compression="gzip")

            # Skill labels
            skills = [frame["skill"] for frame in self.frames]
            dt = h5py.string_dtype()
            f.create_dataset("skill", data=skills, dtype=dt)

        logger.info("Saved %d frames to %s", num_frames, path)

    def clear(self):
        """Discard all recorded frames."""
        self.frames = []
