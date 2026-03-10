import gymnasium as gym

from mani_skill.utils.wrappers import RecordEpisode
from mani_skill.vector.wrappers.gymnasium import ManiSkillVectorEnv

import ps_bed.envs  # noqa: F401 — register custom envs
from ps_bed.config import EnvConfig


def make_env(cfg: EnvConfig):
    """Create a ManiSkill StackCube env with optional video recording and vectorization."""
    need_render = cfg.record_video or cfg.render_mode == "human"
    render_mode = cfg.render_mode if need_render else None

    env = gym.make(
        cfg.env_id,
        obs_mode=cfg.obs_mode,
        control_mode=cfg.control_mode,
        reward_mode=cfg.reward_mode,
        num_envs=cfg.num_envs,
        max_episode_steps=cfg.max_episode_steps,
        render_mode=render_mode,
        **cfg.extra_kwargs,
    )

    if cfg.record_video and cfg.render_mode != "human":
        env = RecordEpisode(
            env,
            output_dir="videos",
            save_trajectory=False,
            save_video=True,
            max_steps_per_video=cfg.max_episode_steps,
        )

    env = ManiSkillVectorEnv(env, auto_reset=True, record_metrics=True)
    return env


def make_single_env(cfg: EnvConfig):
    """Create a single raw gym env for use with the motion planner.

    Forces ``num_envs=1`` and ignores the vectorized wrapper so that
    ``PandaArmMotionPlanningSolver`` can access ``env.unwrapped`` attributes
    directly.
    """
    need_render = cfg.record_video or cfg.render_mode == "human"
    render_mode = cfg.render_mode if need_render else None

    env = gym.make(
        cfg.env_id,
        obs_mode=cfg.obs_mode,
        control_mode=cfg.control_mode,
        reward_mode=cfg.reward_mode,
        num_envs=1,
        max_episode_steps=cfg.max_episode_steps,
        render_mode=render_mode,
        sim_backend="cpu",
        **cfg.extra_kwargs,
    )

    if cfg.record_video and cfg.render_mode != "human":
        env = RecordEpisode(
            env,
            output_dir="videos",
            save_trajectory=False,
            save_video=True,
            save_on_reset=False,
            record_reward=False,
            video_fps=30,
        )

    return env
