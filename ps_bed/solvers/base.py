from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SolverResult:
    """Structured result from a solver run.

    Replaces the loose (obs, reward, terminated, truncated, info) tuple
    with an explicit contract.
    """

    success: bool
    reward: float = 0.0
    elapsed_steps: int = 0
    info: dict = field(default_factory=dict)
    failure_reason: Optional[str] = None


class BaseSolver(ABC):
    """Abstract base class for task solvers.

    Subclasses must implement ``solve()``. Env config requirements (control_mode,
    num_envs, etc.) are declared in the solver's Hydra config group YAML, not here.
    """

    @abstractmethod
    def solve(self, env, seed=None) -> SolverResult:
        """Run the solver on a single raw gym env.

        Args:
            env: A gymnasium env (num_envs=1, cpu backend).
            seed: Random seed for env reset.

        Returns:
            SolverResult with success status, reward, and info dict.
        """
        ...
