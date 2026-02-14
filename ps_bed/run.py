import random

import hydra
import numpy as np
import torch
from omegaconf import OmegaConf

from ps_bed.config import Config
from ps_bed.env import make_env, make_single_env
from ps_bed.logger import Logger


def seed_everything(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def run_random(config: Config, logger: Logger):
    """Run episodes with random actions using the vectorized env."""
    env = make_env(config.env)
    num_envs = config.env.num_envs
    target_episodes = config.run.num_episodes

    episodes_done = 0
    all_returns = []
    all_lengths = []
    all_successes = []

    obs, info = env.reset(seed=config.seed)
    ep_returns = np.zeros(num_envs)
    ep_lengths = np.zeros(num_envs, dtype=int)
    ep_success_once = np.zeros(num_envs, dtype=bool)

    while episodes_done < target_episodes:
        actions = env.action_space.sample()
        obs, rewards, terminations, truncations, infos = env.step(actions)

        if config.env.render_mode == "human":
            env.render()

        if isinstance(rewards, torch.Tensor):
            rewards = rewards.cpu().numpy()
        if isinstance(terminations, torch.Tensor):
            terminations = terminations.cpu().numpy()
        if isinstance(truncations, torch.Tensor):
            truncations = truncations.cpu().numpy()

        ep_returns += rewards
        ep_lengths += 1

        if "success" in infos:
            success = infos["success"]
            if isinstance(success, torch.Tensor):
                success = success.cpu().numpy()
            ep_success_once |= success.astype(bool)

        dones = terminations | truncations
        done_indices = np.where(dones)[0]

        for idx in done_indices:
            if episodes_done >= target_episodes:
                break
            episodes_done += 1
            ep_ret = float(ep_returns[idx])
            ep_len = int(ep_lengths[idx])
            ep_succ = bool(ep_success_once[idx])

            all_returns.append(ep_ret)
            all_lengths.append(ep_len)
            all_successes.append(ep_succ)

            logger.log_episode(
                {"episode/return": ep_ret, "episode/length": ep_len, "episode/success": int(ep_succ)},
                step=episodes_done,
            )

            if episodes_done % 20 == 0 or episodes_done == target_episodes:
                print(f"[Episode {episodes_done}/{target_episodes}]  return={ep_ret:.2f}  len={ep_len}  success={ep_succ}")

            ep_returns[idx] = 0.0
            ep_lengths[idx] = 0
            ep_success_once[idx] = False

    env.close()
    return all_returns, all_lengths, all_successes


def run_pick_place(config: Config, logger: Logger):
    """Run episodes with the motion-planned pick-place skill."""
    from ps_bed.skills.pick_place import PickPlaceSkill

    # Override settings required by the motion planner
    env_cfg = config.env
    env_cfg.control_mode = "pd_joint_pos"
    env_cfg.num_envs = 1

    env = make_single_env(env_cfg)
    skill = PickPlaceSkill()
    target_episodes = config.run.num_episodes

    all_returns = []
    all_lengths = []
    all_successes = []

    recording = config.env.record_video

    # Check if env supports the force_close_distractor flag
    has_distractor_flag = hasattr(env.unwrapped, "force_close_distractor")

    for ep in range(1, target_episodes + 1):
        # Alternate close/far placement for distractor envs
        if has_distractor_flag:
            env.unwrapped.force_close_distractor = (ep % 2 == 0)

        res = skill.solve(env, seed=config.seed + ep)

        # res is the last (obs, reward, terminated, truncated, info) from the planner
        obs, reward, terminated, truncated, info = res

        success = False
        if "success" in info:
            s = info["success"]
            if isinstance(s, torch.Tensor):
                success = bool(s.item())
            else:
                success = bool(s)

        # Manually flush video since save_on_reset=False
        if recording:
            env.flush_video()

        all_returns.append(0.0)  # planner doesn't accumulate reward
        all_lengths.append(0)
        all_successes.append(success)

        logger.log_episode(
            {"episode/return": 0.0, "episode/length": 0, "episode/success": int(success)},
            step=ep,
        )

        close_tag = ""
        if has_distractor_flag:
            close_tag = " [CLOSE]" if (ep % 2 == 0) else " [FAR]"
        rate = np.mean(all_successes)
        print(f"[Episode {ep}/{target_episodes}]{close_tag}  success={success}  cumulative_rate={rate:.2f}")

    env.close()
    return all_returns, all_lengths, all_successes


@hydra.main(version_base="1.3", config_path="../configs", config_name="default")
def main(cfg: Config) -> None:
    cfg = OmegaConf.to_object(cfg)
    from ps_bed.config import Config as CfgClass, EnvConfig, LoggingConfig, RunConfig

    config = CfgClass(
        seed=cfg["seed"],
        env=EnvConfig(**cfg["env"]),
        logging=LoggingConfig(**cfg["logging"]),
        run=RunConfig(**cfg["run"]),
    )

    seed_everything(config.seed)
    logger = Logger(config)

    policy = config.run.policy
    if policy == "random":
        all_returns, all_lengths, all_successes = run_random(config, logger)
    elif policy == "pick_place":
        all_returns, all_lengths, all_successes = run_pick_place(config, logger)
    else:
        raise ValueError(f"Unknown policy: {policy!r}. Choose 'random' or 'pick_place'.")

    # Summary
    summary = {
        "mean_return": float(np.mean(all_returns)),
        "std_return": float(np.std(all_returns)),
        "mean_length": float(np.mean(all_lengths)),
        "success_rate": float(np.mean(all_successes)),
        "num_episodes": len(all_returns),
    }

    print("\n===== Summary =====")
    for k, v in summary.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    logger.log_summary(summary)
    logger.finish()


if __name__ == "__main__":
    main()
