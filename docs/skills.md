# Skills

Skills are composable manipulation primitives. Use them through `SkillContext` — it bundles the env, motion planner, and object references so you only pass task-specific parameters.

## SkillContext

```python
from taskbench.skills.context import SkillContext

ctx = SkillContext(env, step_callback=recorder.record)
ctx.reset(seed=42)

# Skills are ready
pick_result = ctx.pick("cube_1", lift_height=0.15)
if pick_result.success:
    ctx.place(target_pose, retract_height=0.2)
```

`ctx.reset(seed)` handles: env reset, planner creation, object discovery, and skill re-initialization. You must call it before using any skills.

After reset, `ctx.objects` is a `dict[str, Actor]` mapping object names to SAPIEN actors (from the env's `get_objects()` method).

## Available Skills

### pick

```python
pick_result = ctx.pick(obj_name, *, lift_height=0.1, verify_grasp=True)
```

Grasp an object by name and lift it. Tries multiple grasp angles (6 candidates around the Z-axis) until one succeeds.

**Parameters:**
- `obj_name` — string name of the object (resolved via `ctx.objects`)
- `lift_height` — how high to lift after grasping (meters)
- `verify_grasp` — check that the object is actually held after closing fingers

**Returns:** `PickResult` with:
- `success`, `failure_reason`
- `grasp_pose` — the pose used for grasping
- `lift_pose` — the pose after lifting (useful for computing place targets)
- `obj_size` — bounding box of the grasped object

### place

```python
place_result = ctx.place(target_pose, *, settling_steps=10, retract_height=None)
```

Move to a target pose, release the object, wait for it to settle, then retract.

**Parameters:**
- `target_pose` — where to place. Accepts `sapien.Pose` or `(position, quaternion)` tuple
- `settling_steps` — steps to wait after releasing
- `retract_height` — Z height to retract to after placing (default: lift back up)

**Returns:** `PlaceResult` with `success`, `failure_reason`

### move

```python
move_result = ctx.move(target_pose, *, gripper_open=True, monitor_contacts=True)
```

Move the end-effector to a target pose using screw-based motion planning.

**Parameters:**
- `target_pose` — target end-effector pose
- `gripper_open` — gripper state during motion
- `monitor_contacts` — abort if unexpected contacts occur

**Returns:** `MoveResult` with `success`, `failure_reason`

### push

```python
push_result = ctx.push(approach_pose, push_pose, *, clearance_height=0.1, lift_height=0.1)
```

Approach an object and sweep it to a target position.

**Parameters:**
- `approach_pose` — where to position before pushing
- `push_pose` — where to push to
- `clearance_height` — height to lift before approaching
- `lift_height` — height to lift after pushing

**Returns:** `PushResult` with `success`, `failure_reason`

## PoseLike

All skills accept poses as either `sapien.Pose` or `(position, quaternion)` tuples:

```python
ctx.place(sapien.Pose([0.1, 0.0, 0.2], [1, 0, 0, 0]))
ctx.place(([0.1, 0.0, 0.2], [1, 0, 0, 0]))
```

Quaternion format is `[w, x, y, z]` (SAPIEN convention).

## Result Dataclasses

All skills return a `SkillResult` subclass:

```python
@dataclass
class SkillResult:
    success: bool
    failure_reason: Optional[str] = None
    step_result: Optional[tuple] = None  # last (obs, rew, term, trunc, info)
```

`PickResult` adds `grasp_pose`, `lift_pose`, and `obj_size` — used by downstream skills (e.g., computing where to place).

## RobotConfig

Robot-specific constants (move group, finger length, gripper links) are stored in `RobotConfig`, not hardcoded:

```python
from taskbench.skills.robot_config import ROBOT_CONFIGS

ROBOT_CONFIGS = {
    "panda": RobotConfig(move_group="panda_hand_tcp", finger_length=0.025, ...),
    "panda_wristcam": RobotConfig(...),
}
```

`SkillContext` auto-detects the robot from `env.unwrapped.agent.uid`.

## Motion Primitives (Lower Level)

`taskbench/skills/motion.py` provides the functions that skills are built on:

| Function | Description |
|----------|-------------|
| `setup_planner(env, robot_config)` | Create mplib Planner from env's robot |
| `move_to_pose(env, planner, pose, gripper_state, robot_config, ...)` | Plan + execute straight-line screw motion |
| `follow_path(env, result, gripper_state, robot_config, ...)` | Execute a pre-planned trajectory |
| `actuate_gripper(env, planner, gripper_state, steps=6)` | Open/close gripper |
| `build_action(env, qpos, gripper_state)` | Build action array for pd_joint_pos |
| `attach_object(planner, size)` / `detach_object(planner)` | Inform planner about held objects |
