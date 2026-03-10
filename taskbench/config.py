from dataclasses import dataclass, field
from typing import Any, Dict

from hydra.core.config_store import ConfigStore


@dataclass
class EnvConfig:
    env_id: str = "StackCube-v1"
    obs_mode: str = "state"
    control_mode: str = "pd_ee_delta_pose"
    reward_mode: str = "normalized_dense"
    num_envs: int = 16
    max_episode_steps: int = 100
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)
    record_video: bool = False
    render_mode: str = "rgb_array"


@dataclass
class LoggingConfig:
    use_wandb: bool = False
    project: str = "taskbench"
    group: str = "stackcube"


@dataclass
class RunConfig:
    num_episodes: int = 100
    solver: str = "random"


@dataclass
class Config:
    seed: int = 42
    env: EnvConfig = field(default_factory=EnvConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    run: RunConfig = field(default_factory=RunConfig)


cs = ConfigStore.instance()
cs.store(name="config", node=Config)
