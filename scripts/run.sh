#!/usr/bin/env bash
set -euo pipefail

# Defaults
python -m ps_bed.run

# Example overrides:
# python -m ps_bed.run env.num_envs=64 logging.use_wandb=true
# python -m ps_bed.run env.record_video=true
# python -m ps_bed.run seed=123 run.num_episodes=50
