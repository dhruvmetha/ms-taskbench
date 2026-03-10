"""Robot-specific constants for motion planning and skill execution.

Each supported robot has a ``RobotConfig`` entry in ``ROBOT_CONFIGS``.
Use ``get_robot_config(env)`` to look up the config for the current robot.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RobotConfig:
    """Hardware-specific constants that skills and motion planning need."""

    move_group: str  # mplib move group name (from SRDF)
    finger_length: float  # depth of gripper fingers (meters)
    gripper_link_names: frozenset[str]  # links for contact detection
    gripper_open: float = 1.0  # action value for open
    gripper_closed: float = -1.0  # action value for closed


ROBOT_CONFIGS: dict[str, RobotConfig] = {
    "panda": RobotConfig(
        move_group="panda_hand_tcp",
        finger_length=0.025,
        gripper_link_names=frozenset(
            {"panda_hand", "panda_leftfinger", "panda_rightfinger"}
        ),
    ),
    "panda_wristcam": RobotConfig(
        move_group="panda_hand_tcp",
        finger_length=0.025,
        gripper_link_names=frozenset(
            {"panda_hand", "panda_leftfinger", "panda_rightfinger"}
        ),
    ),
}


def get_robot_config(env) -> RobotConfig:
    """Look up the RobotConfig for the env's robot.

    Reads ``env.unwrapped.agent.uid`` and looks it up in ``ROBOT_CONFIGS``.
    """
    uid = env.unwrapped.agent.uid
    if uid not in ROBOT_CONFIGS:
        available = ", ".join(sorted(ROBOT_CONFIGS))
        raise KeyError(
            f"No RobotConfig for robot {uid!r}. Available: {available}"
        )
    return ROBOT_CONFIGS[uid]
