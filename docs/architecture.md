# Taskbench Architecture

Taskbench is a robotics research testbed for evaluating solvers on ManiSkill3 manipulation tasks. It provides a pluggable framework for defining environments, composing manipulation skills, and recording demonstrations.

## Directory Structure

```
taskbench/                          # Core framework
  run.py                            # Entry point (@hydra.main)
  solver.py                         # BaseSolver ABC, SolverResult, @register_solver, auto-discovery
  recorder.py                       # StateRecorder for episode capture (HDF5)
  logger.py                         # WandB logging wrapper
  envs/
    base.py                         # TaskEnv — base class with get_objects()
    factory.py                      # make_env() / make_single_env()
    __init__.py                     # get_objects() dispatch + env registration
    stack_n_cube.py                 # StackNCube-v1 (parameterized N-cube)
    stack_cube_distractor.py        # StackCubeDistractor-v1 (2-cube + distractor)
    shelf_env.py                    # ShelfEnv-v1 (enclosed shelf with cylinders)
    bin_with_objects.py             # BinWithObjects-v1 (bin of primitives + YCB)
  skills/
    robot_config.py                 # RobotConfig dataclass + registry
    context.py                      # SkillContext — bundles env + planner + skills
    motion.py                       # Low-level mplib helpers
    primitives.py                   # Composable skill objects (Pick, Place, etc.)

  solvers/
    stack_n_cubes.py                # StackCubesSolver (@register_solver)
    replay.py                       # ReplaySolver (@register_solver)
    demo_recorder.py                # DemoRecorderSolver (@register_solver)
    shelf_reachability.py           # ShelfReachabilitySolver (@register_solver)

configs/
  default.yaml                      # Default Hydra config (YAML-only, no Python dataclasses)
  solver/                           # Hydra config group (one YAML per solver)
    random.yaml
    stack_cubes.yaml
    replay.yaml
    demo_recorder.yaml
    shelf_reachability.yaml
```

## Core Flow

`taskbench/run.py` is the entry point (`@hydra.main`). It dispatches based on `cfg.run.solver`:

- `"random"` -> `run_random()` — creates a vectorized env via `make_env()`, samples random actions
- Any other value -> `run_solver()` — looks up the solver via `get_solver()`, creates a single CPU env via `make_single_env()`, calls `solver.solve()` per episode

```bash
uv run python -m taskbench.run                                      # random baseline
uv run python -m taskbench.run solver=stack_cubes                   # registered solver
uv run python -m taskbench.run solver=stack_cubes env.num_cubes=4
```

---

## Skills

Skills are composable objects that bind shared context (env, planner, robot config, object references) at construction, exposing only task-specific parameters at call time.

### SkillContext (Recommended)

`SkillContext` eliminates boilerplate by bundling env + planner + objects + pre-bound skills:

```python
from taskbench.skills.context import SkillContext

ctx = SkillContext(env, step_callback=recorder.record)
ctx.reset(seed=42)

# Skills are ready to use
pick_result = ctx.pick("cube_1", lift_height=0.15)
if pick_result.success:
    ctx.place(target_pose, retract_height=0.2)
```

`SkillContext.reset(seed)` handles: env reset, planner creation, object discovery, and skill re-initialization.

### Skill Base Class

```python
class Skill(ABC):
    def __init__(self, env, planner, *, robot_config=None, objects=None, step_callback=None):
        self.env = env                          # gym env
        self.planner = planner                  # mplib.Planner
        self.robot_config = robot_config or get_robot_config(env)  # RobotConfig
        self.objects = objects or {}             # {"cube_0": actor, ...}
        self.step_callback = step_callback      # called after each env.step()

    @abstractmethod
    def __call__(self, *args, **kwargs) -> SkillResult: ...
```

### Available Skills

| Skill | Signature | Returns | Description |
|-------|-----------|---------|-------------|
| **Move** | `(target_pose: PoseLike, *, gripper_open=True, monitor_contacts=True)` | `MoveResult` | Move end-effector to a target pose |
| **Pick** | `(obj_name: str, *, lift_height=0.1, verify_grasp=True)` | `PickResult` | Grasp an object by name and lift it |
| **Place** | `(target_pose: PoseLike, *, settling_steps=10, retract_height=None)` | `PlaceResult` | Move to pose, release, settle, retract |
| **Push** | `(approach_pose: PoseLike, push_pose: PoseLike, *, clearance_height=0.1, lift_height=0.1)` | `PushResult` | Lift, approach, sweep, lift, open |

### PoseLike Type

Skills accept poses as either `sapien.Pose` objects or plain `(position, quaternion)` tuples. The conversion is handled internally via `to_sapien_pose()`:

```python
# Both are valid:
ctx.place(sapien.Pose([0.1, 0.0, 0.2], [1, 0, 0, 0]))
ctx.place(([0.1, 0.0, 0.2], [1, 0, 0, 0]))
```

### Object Resolution

Skills that need actors (e.g. `Pick`) resolve them by string name through the `objects` dict, which comes from the environment's `get_objects()` method:

```python
ctx.pick("cube_1")  # resolves via ctx.objects["cube_1"]
```

### Result Dataclasses

All skills return a `SkillResult` subclass with at minimum:

```python
@dataclass
class SkillResult:
    success: bool
    failure_reason: Optional[str] = None
    step_result: Optional[tuple] = None     # last (obs, rew, term, trunc, info)
```

`PickResult` adds `grasp_pose`, `lift_pose`, and `obj_size` — used by downstream skills (e.g. computing the place target).

### RobotConfig

Robot-specific constants (move group, finger length, gripper link names) are stored in `RobotConfig` dataclasses, not hardcoded. This means skills work with any supported robot:

```python
from taskbench.skills.robot_config import ROBOT_CONFIGS

# Currently supported:
ROBOT_CONFIGS = {
    "panda": RobotConfig(move_group="panda_hand_tcp", finger_length=0.025, ...),
    "panda_wristcam": RobotConfig(...),  # same hardware, different sensors
}
```

`SkillContext` auto-detects the robot config from `env.unwrapped.agent.uid`. To add a new robot, add an entry to `ROBOT_CONFIGS`.

### Motion Primitives (Lower Level)

`taskbench/skills/motion.py` provides the low-level functions that skills are built on. All motion functions take a `robot_config` parameter:

| Function | Description |
|----------|-------------|
| `setup_planner(env, robot_config)` | Create mplib Planner from env's robot, add table collision |
| `move_to_pose(env, planner, pose, gripper_state, robot_config, ...)` | Plan + execute straight-line motion (screw interpolation) |
| `follow_path(env, result, gripper_state, robot_config, ...)` | Execute a pre-planned trajectory |
| `actuate_gripper(env, planner, gripper_state, steps=6)` | Open/close gripper for N steps |
| `build_action(env, qpos, gripper_state, qvel=None)` | Build action array for pd_joint_pos or pd_joint_pos_vel |
| `attach_object(planner, size)` / `detach_object(planner)` | Inform planner about held objects |
| `add_collision_boxes(planner, boxes, resolution=0.01)` | Add box obstacles as point clouds |

---

## Environments

### TaskEnv Base Class

All custom environments inherit from `TaskEnv` and must implement `get_objects()`:

```python
from taskbench.envs.base import TaskEnv

class TaskEnv(BaseEnv, metaclass=ABCMeta):
    @abstractmethod
    def get_objects(self) -> dict[str, object]:
        """Return a name -> actor mapping for all manipulable objects."""
        ...
```

### Registered Environments

| Env ID | Class | get_objects() | Notes |
|--------|-------|---------------|-------|
| `StackCube-v1` | Built-in ManiSkill | `{"cube_0": cubeB, "cube_1": cubeA}` | 2-cube stacking (fallback in `get_objects()` dispatch) |
| `StackNCube-v1` | `StackNCubeEnv` | `{"cube_0": ..., "cube_N": ...}` | Parameterized N-cube (2-6), cube_0 is always green (base), any tower order valid. `env.num_cubes=N` |
| `StackCubeDistractor-v1` | `StackCubeDistractorEnv` | `{"cube_0": green, "cube_1": red, "cube_2": blue}` | 2-cube stacking + blue distractor |
| `ShelfEnv-v1` | `ShelfEnv` | `{"cyl_0": ..., "cyl_19": ...}` | Enclosed shelf, 19 blue + 1 red cylinder |
| `BinWithObjects-v1` | `BinWithObjectsEnv` | `{obj.name: obj, ...}` | Bin with ~30 random primitives + YCB objects |

### Environment Factories

```python
from taskbench.envs.factory import make_env, make_single_env

# Vectorized env for RL (multiple parallel envs, GPU backend)
env = make_env(cfg.env)

# Single raw env for motion planner (num_envs=1, CPU backend, no vector wrapper)
env = make_single_env(cfg.env)
```

Motion-planner solvers **must** use `make_single_env()` because mplib requires `num_envs=1`, `sim_backend="cpu"`, and direct access to `env.unwrapped`.

---

## Solvers

### BaseSolver and @register_solver

```python
from taskbench.solver import BaseSolver, SolverResult, register_solver

@register_solver("my_task")
class MyTaskSolver(BaseSolver):
    def solve(self, env, seed=None) -> SolverResult:
        ...
```

The `@register_solver` decorator adds the class to `SOLVER_REGISTRY`. Solvers under `taskbench/solvers/` are auto-discovered via `pkgutil.walk_packages` on first call to `get_solver()` — no manual imports needed.

### SolverResult

```python
@dataclass
class SolverResult:
    success: bool                           # task success
    reward: float = 0.0                     # cumulative reward
    elapsed_steps: int = 0                  # steps taken
    info: dict = field(default_factory=dict) # task-specific data
    failure_reason: Optional[str] = None    # human-readable reason
```

---

## Adding a New Task

A "task" consists of up to three pieces: an environment, a solver, and a Hydra config. **No edits to core files required.**

### 1. Create the Environment

Create `taskbench/envs/my_task.py`:

```python
import torch
import sapien
from mani_skill.utils.registration import register_env
from taskbench.envs.base import TaskEnv

@register_env("MyTask-v1", max_episode_steps=200)
class MyTaskEnv(TaskEnv):
    SUPPORTED_ROBOTS = ["panda"]

    def __init__(self, *args, robot_uids="panda", **kwargs):
        super().__init__(*args, robot_uids=robot_uids, **kwargs)

    def get_objects(self) -> dict[str, object]:
        return {"target": self.target_obj}

    def _load_scene(self, options: dict):
        # Build scene actors
        ...

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        # Randomize object poses each episode
        ...

    def evaluate(self):
        # Return {"success": torch.tensor([bool], device=self.device)}
        ...

    def _get_obs_extra(self, info: dict):
        return dict(tcp_pose=self.agent.tcp.pose.raw_pose)

    def compute_dense_reward(self, obs, action, info):
        return torch.zeros(self.num_envs, device=self.device)

    def compute_normalized_dense_reward(self, obs, action, info):
        return torch.zeros(self.num_envs, device=self.device)
```

Register the env by adding an import to `taskbench/envs/__init__.py`:

```python
import taskbench.envs.my_task  # noqa: F401
```

### 2. Create the Solver

Create `taskbench/solvers/my_task.py`:

```python
from taskbench.skills.context import SkillContext
from taskbench.solver import BaseSolver, SolverResult, register_solver

@register_solver("my_task")
class MyTaskSolver(BaseSolver):
    def solve(self, env, seed=None) -> SolverResult:
        ctx = SkillContext(env)
        ctx.reset(seed=seed)

        pick_result = ctx.pick("target")
        if not pick_result.success:
            return SolverResult(success=False, failure_reason=pick_result.failure_reason)

        place_result = ctx.place(goal_pose)
        if not place_result.success:
            return SolverResult(success=False, failure_reason=place_result.failure_reason)

        info = env.unwrapped.evaluate()
        return SolverResult(success=bool(info["success"].item()))
```

### 3. Create the Hydra Config

`configs/solver/my_task.yaml`:

```yaml
# @package _global_
run:
  solver: my_task

env:
  env_id: MyTask-v1
  control_mode: pd_joint_pos
  num_envs: 1
  reward_mode: none
```

### 4. Run

```bash
uv run python -m taskbench.run solver=my_task
```

The solver is auto-discovered from `taskbench/solvers/my_task.py` (no registry edits). The config is found by Hydra in `configs/solver/` (no searchpath edits).

---

## State Recording

`StateRecorder` captures simulation state at control frequency and saves to HDF5:

```python
from taskbench.recorder import StateRecorder
from taskbench.skills.context import SkillContext

recorder = StateRecorder(
    env,
    objects=get_objects(env),
    robot_fields=["qpos", "tcp_pos", "tcp_quat", "gripper_qpos"],
)

ctx = SkillContext(env, step_callback=recorder.record)
ctx.reset(seed=42)
recorder.record()  # initial state

recorder.set_skill("pick(cube_1)")
ctx.pick("cube_1")

recorder.save("data/episode.hdf5")
```

Available `robot_fields`: `qpos`, `qvel`, `tcp_pos`, `tcp_quat`, `gripper_qpos`.

HDF5 structure:

```
episode.hdf5
├── metadata/              attrs: num_frames, control_freq
├── robot/
│   ├── qpos               (num_frames, 9)
│   ├── tcp_pos            (num_frames, 3)
│   ├── tcp_quat           (num_frames, 4)
│   └── gripper_qpos       (num_frames, 2)
├── objects/
│   ├── cube_0/
│   │   ├── pos            (num_frames, 3)
│   │   └── quat           (num_frames, 4)
│   └── cube_1/
│       ├── pos            (num_frames, 3)
│       └── quat           (num_frames, 4)
└── skill                  (num_frames,) string labels
```

---

## Configuration

All config is YAML-only (no Python dataclasses). `configs/default.yaml` defines the schema; solver configs in `configs/solver/` override env-specific fields.

Override any field from the command line:

```bash
uv run python -m taskbench.run seed=123 env.record_video=true run.num_episodes=10
uv run python -m taskbench.run solver=stack_cubes env.num_cubes=5
```

---

## Constraints

- **mplib 0.2.x**: uses `mplib.pymp.Pose` objects (not numpy). SAPIEN poses are batched — must `.flatten()` before passing to mplib.
- **Motion planner requires**: `num_envs=1`, `sim_backend="cpu"`, `pd_joint_pos` control mode.
- **Video recording with planner**: use `save_on_reset=False` on `RecordEpisode`, call `env.flush_video()` manually.
- **numpy < 2.0** required by mplib 0.2.1.
