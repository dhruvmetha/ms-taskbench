from abc import ABC, abstractmethod


class BaseSolver(ABC):
    """Abstract base class for task solvers.

    Subclasses must implement ``solve()``. Env config requirements (control_mode,
    num_envs, etc.) are declared in the solver's Hydra config group YAML, not here.
    """

    @abstractmethod
    def solve(self, env, seed=None):
        """Run the solver on a single raw gym env.

        Args:
            env: A gymnasium env (num_envs=1, cpu backend).
            seed: Random seed for env reset.

        Returns:
            (obs, reward, terminated, truncated, info) tuple.
        """
        ...
