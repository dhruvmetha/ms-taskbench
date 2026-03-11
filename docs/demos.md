# Demo Recording and Replay

## Recording

The `StateRecorder` captures robot state, object poses, and skill programs at every control step, saving to HDF5.

```python
from taskbench.recorder import StateRecorder

recorder = StateRecorder(
    env,
    objects=ctx.objects,
    robot_fields=["qpos", "tcp_pos", "tcp_quat", "gripper_qpos"],
)
ctx.step_callback = recorder.record
recorder.record()  # initial frame

# Record skill calls before executing them
recorder.record_skill_call("pick", {"obj_name": "cube_1", "lift_height": 0.13})
ctx.pick("cube_1", lift_height=0.13)

recorder.record_skill_call("place", {"target_pose": target, "retract_height": 0.2})
ctx.place(target, retract_height=0.2)

recorder.save("data/success/episode.hdf5", metadata={
    "seed": 42,
    "solver": "my_solver",
    "success": True,
}, hydra_cfg=cfg)
```

Available `robot_fields`: `qpos`, `qvel`, `tcp_pos`, `tcp_quat`, `gripper_qpos`.

## HDF5 Structure

```
episode.hdf5
├── metadata/              attrs: seed, env_id, solver, success,
│                                 failure_reason, control_freq,
│                                 num_frames, hydra_config (YAML string)
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
├── skill                  (num_frames,)  per-frame skill labels
└── program/
    ├── skill              ["pick", "place", ...]  skill names
    ├── args               ['{"obj_name": "cube_1"}', ...]  JSON kwargs
    └── start_frame        [0, 142, ...]  frame index where each call started
```

## Parsing a Demo

```python
import h5py
import json

with h5py.File("data/success/episode_seed48.hdf5", "r") as f:
    # Metadata
    seed = int(f["metadata"].attrs["seed"])
    env_id = f["metadata"].attrs["env_id"]
    success = f["metadata"].attrs["success"]
    config_yaml = f["metadata"].attrs["hydra_config"]  # full resolved config

    # Robot trajectory
    qpos = f["robot/qpos"][:]            # (num_frames, 9)
    tcp_pos = f["robot/tcp_pos"][:]      # (num_frames, 3)
    tcp_quat = f["robot/tcp_quat"][:]    # (num_frames, 4)
    gripper = f["robot/gripper_qpos"][:] # (num_frames, 2)

    # Object trajectories
    for name in f["objects"]:
        pos = f[f"objects/{name}/pos"][:]    # (num_frames, 3)
        quat = f[f"objects/{name}/quat"][:]  # (num_frames, 4)

    # Skill program (what was executed)
    for skill, args, frame in zip(
        f["program/skill"], f["program/args"], f["program/start_frame"]
    ):
        name = skill.decode()
        kwargs = json.loads(args.decode())
        print(f"Frame {frame}: {name}({kwargs})")

    # Per-frame skill labels (which skill was active at each timestep)
    skill_labels = [s.decode() for s in f["skill"]]
```

## Replay

Replay re-executes the stored skill program on a fresh env with the same seed:

```bash
uv run python -m taskbench.run solver=replay \
    run.solver_kwargs.demo_path=data/success/episode_seed48.hdf5
```

The replay solver automatically reads `env_id` and `num_cubes` from the demo's stored Hydra config — no manual overrides needed.

### Replay from code

```python
import h5py
import json
import gymnasium as gym
from taskbench.skills.context import SkillContext
import taskbench.envs

with h5py.File("data/success/episode_seed48.hdf5", "r") as f:
    seed = int(f["metadata"].attrs["seed"])
    skills = [s.decode() for s in f["program/skill"]]
    args = [json.loads(a.decode()) for a in f["program/args"]]

env = gym.make("StackNCube-v1", num_cubes=5, control_mode="pd_joint_pos",
               num_envs=1, sim_backend="cpu", obs_mode="state", reward_mode="sparse")

ctx = SkillContext(env)
ctx.reset(seed=seed)

for skill_name, kwargs in zip(skills, args):
    result = getattr(ctx, skill_name)(**kwargs)
    if not result.success:
        print(f"{skill_name} failed: {result.failure_reason}")
        break

env.close()
```

## File Organization

Demos are saved by outcome:

```
data/
  success/
    episode_seed42.hdf5
    episode_seed45.hdf5
  failure/
    episode_seed43.hdf5
    episode_seed44.hdf5
```
