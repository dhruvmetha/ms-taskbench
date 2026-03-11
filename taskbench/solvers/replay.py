"""Replay solver — re-execute a recorded skill program from an HDF5 demo.

Usage:
    uv run python -m taskbench.run solver=replay \\
        +run.solver_kwargs.demo_path=data/episode_seed43.hdf5

    # With video recording:
    uv run python -m taskbench.run solver=replay \\
        +run.solver_kwargs.demo_path=data/episode_seed43.hdf5 \\
        env.record_video=true
"""

import json
import logging

import h5py
import numpy as np
import sapien

from taskbench.skills.context import SkillContext
from taskbench.solver import BaseSolver, SolverResult, register_solver

logger = logging.getLogger("taskbench.solvers.replay")


def _deserialize_arg(value):
    """Convert a JSON-deserialized value back to its original type."""
    if isinstance(value, dict) and value.get("_type") == "pose":
        return sapien.Pose(
            np.array(value["p"], dtype=np.float32),
            np.array(value["q"], dtype=np.float32),
        )
    if isinstance(value, list):
        if len(value) > 0 and isinstance(value[0], dict):
            return [_deserialize_arg(v) for v in value]
        if len(value) > 0 and isinstance(value[0], list):
            # Tuple of arrays, e.g. (p, q) for PoseLike
            return tuple(np.array(v, dtype=np.float32) for v in value)
        return value
    return value


def _deserialize_kwargs(args_json):
    """Deserialize a JSON string of skill kwargs."""
    raw = json.loads(args_json)
    return {k: _deserialize_arg(v) for k, v in raw.items()}


@register_solver("replay")
class ReplaySolver(BaseSolver):
    """Replay a recorded skill program from an HDF5 demonstration.

    Args:
        demo_path: Path to the HDF5 file containing the recorded program.
    """

    def __init__(self, demo_path: str):
        self.demo_path = demo_path

    def solve(self, env, seed=None) -> SolverResult:
        with h5py.File(self.demo_path, "r") as f:
            demo_seed = int(f["metadata"].attrs["seed"])
            skill_names = [s.decode() if isinstance(s, bytes) else s
                           for s in f["program/skill"]]
            skill_args = [s.decode() if isinstance(s, bytes) else s
                          for s in f["program/args"]]

        logger.info(
            "Replaying %s: %d skill calls, seed=%d",
            self.demo_path, len(skill_names), demo_seed,
        )

        ctx = SkillContext(env)
        ctx.reset(seed=demo_seed)

        for i, (skill_name, args_json) in enumerate(zip(skill_names, skill_args)):
            kwargs = _deserialize_kwargs(args_json)
            logger.info("Step %d/%d: %s(%s)", i + 1, len(skill_names), skill_name, kwargs)

            skill_fn = getattr(ctx, skill_name, None)
            if skill_fn is None:
                logger.error("Unknown skill: %s", skill_name)
                return SolverResult(
                    success=False,
                    failure_reason=f"unknown_skill:{skill_name}",
                )

            result = skill_fn(**kwargs)
            if not result.success:
                logger.warning("Step %d failed: %s", i + 1, result.failure_reason)
                return SolverResult(
                    success=False,
                    failure_reason=result.failure_reason,
                    info={"steps_completed": i},
                )

        info = env.unwrapped.evaluate()
        success = bool(info["success"].item())
        logger.info("Replay complete: success=%s", success)
        return SolverResult(success=success)
