#!/usr/bin/env bash
set -euo pipefail

# Defaults
python -m taskbench.run

# Example overrides:
# python -m taskbench.run env.num_envs=64 logging.use_wandb=true
# python -m taskbench.run env.record_video=true
# python -m taskbench.run seed=123 run.num_episodes=50
