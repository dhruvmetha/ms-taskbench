"""Base class for taskbench environments."""

from abc import ABCMeta, abstractmethod

from mani_skill.envs.sapien_env import BaseEnv


class TaskEnv(BaseEnv, metaclass=ABCMeta):
    """Base class for all taskbench custom environments.

    Subclasses must implement ``get_objects()`` to expose their
    manipulable objects with canonical names.
    """

    @abstractmethod
    def get_objects(self) -> dict[str, object]:
        """Return a name→actor mapping for all manipulable objects."""
        ...
