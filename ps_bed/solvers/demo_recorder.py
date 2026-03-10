"""Interactive demo recorder: compose skill programs by clicking cubes in the SAPIEN viewer.

Usage:
    uv run python -m ps_bed.run solver=demo_recorder env.env_id=StackNCube-v1 \
        +env.extra_kwargs.num_cubes=3 run.num_episodes=1

Keyboard shortcuts:
    Click  — select a cube in the viewer
    1      — pick the selected cube
    2      — place held cube on top of selected cube
    3      — push: click cube, drag gizmo → Enter (start), drag → Enter (end)
    Escape — cancel push
    s      — save demo
    r      — reset scene
    q      — quit
"""

import json
import logging

import numpy as np
import sapien
import sapien.render
from transforms3d.euler import euler2quat

from ps_bed.skills.motion import setup_planner
from ps_bed.skills.primitives import Pick, Place, Push
from ps_bed.solvers.base import BaseSolver, SolverResult

logger = logging.getLogger("ps_bed.solvers.demo_recorder")

HELP_TEXT = """
╔══════════════════════════════════════════════╗
║          Interactive Demo Recorder           ║
╠══════════════════════════════════════════════╣
║  Click   — select a cube                    ║
║  1       — pick selected cube                ║
║  2       — place on selected cube            ║
║  3       — push: click cube for gizmo, then  ║
║            drag → Enter (start, green)       ║
║            drag → Enter (end, red)           ║
║  Escape  — cancel push                      ║
║  s       — save demo                         ║
║  r       — reset scene                       ║
║  q       — quit                              ║
╚══════════════════════════════════════════════╝
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_cube_list(env):
    """Return cube list for any supported env."""
    raw = env.unwrapped
    if hasattr(raw, "cubes"):
        return raw.cubes
    return [raw.cubeB, raw.cubeA]


def _resolve_selected_cube(viewer, cubes):
    """Match the viewer's selected entity to one of our cubes."""
    entity = viewer.selected_entity
    if entity is None:
        return None, None
    for i, cube in enumerate(cubes):
        if entity.name.endswith(cube.name):
            return cube, f"cube_{i}"
    return None, None


_HIDDEN = np.array([99, 99, 99], dtype=np.float32)


def _create_marker(env, color, name):
    """Create a kinematic sphere marker, hidden off-screen until shown."""
    sapien_scene = env.unwrapped.scene.sub_scenes[0]
    material = sapien.render.RenderMaterial(base_color=[*color[:3], 1.0])
    builder = sapien.ActorBuilder()
    builder.set_scene(sapien_scene)
    builder.set_initial_pose(sapien.Pose(_HIDDEN))
    builder.add_sphere_visual(radius=0.01, material=material)
    return builder.build_kinematic(name=name)


def _show_marker(marker, position):
    """Move marker to a visible position."""
    marker.set_pose(sapien.Pose(np.array(position, dtype=np.float32)))


def _hide_marker(marker):
    """Move marker off-screen."""
    marker.set_pose(sapien.Pose(_HIDDEN))


def _save_demo(scene_config, program_steps, path="demo_record.json"):
    """Write the scene config and program to a JSON file."""
    program = [{"step": i, **step} for i, step in enumerate(program_steps)]
    demo = {
        "scene": scene_config,
        "program": program,
        "all_succeeded": all(s.get("success", False) for s in program_steps),
    }
    with open(path, "w") as f:
        json.dump(demo, f, indent=2)
    print(f"Demo saved to {path} ({len(program_steps)} steps)")


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

class DemoRecorderSolver(BaseSolver):
    """Interactive solver: compose skill programs by clicking cubes."""

    def solve(self, env, seed=None) -> SolverResult:
        env.reset(seed=seed)
        planner = setup_planner(env)
        raw = env.unwrapped
        cubes = _get_cube_list(env)

        scene_config = {
            "env_id": raw.spec.id,
            "num_cubes": len(cubes),
            "initial_poses": {
                f"cube_{i}": cube.pose.p[0].cpu().numpy().tolist()
                for i, cube in enumerate(cubes)
            },
        }

        viewer = env.render_human()

        # Enable the gizmo (TransformWindow) — disabled by default
        transform_window = None
        for plugin in viewer.plugins:
            if type(plugin).__name__ == "TransformWindow":
                transform_window = plugin
                transform_window.enabled = True
                break

        print(HELP_TEXT)
        render = lambda: env.render_human()

        # Initialize skills with shared context
        pick = Pick(env, planner, step_callback=render)
        place = Place(env, planner, step_callback=render)
        push = Push(env, planner, step_callback=render)

        # Create push markers once (hidden off-screen until needed)
        start_marker = _create_marker(env, color=[0.0, 1.0, 0.0], name="_push_start")
        end_marker = _create_marker(env, color=[1.0, 0.0, 0.0], name="_push_end")

        # State
        program_steps = []
        held_cube = None       # (actor, name, pick_result) when holding
        state = "idle"         # idle | awaiting_push_start | awaiting_push_end
        push_start_pose = None

        while not viewer.closed:
            env.render_human()

            # --- IDLE: pick / place / push entry ---
            if state == "idle":
                if viewer.window.key_press("1"):  # PICK
                    cube, cube_name = _resolve_selected_cube(viewer, cubes)
                    if cube is None:
                        print("[!] Click a cube first")
                        continue
                    if held_cube is not None:
                        print("[!] Already holding — place it first")
                        continue
                    print(f"[pick] Picking {cube_name}...")
                    result = pick(cube)
                    if result.success:
                        held_cube = (cube, cube_name, result)
                        print(f"[pick] OK")
                    else:
                        print(f"[pick] Failed: {result.failure_reason}")
                    program_steps.append({
                        "skill": "pick", "args": {"obj": cube_name},
                        "success": result.success,
                    })

                elif viewer.window.key_press("2"):  # PLACE
                    if held_cube is None:
                        print("[!] Nothing held — pick first (1)")
                        continue
                    target_cube, target_name = _resolve_selected_cube(viewer, cubes)
                    if target_cube is None:
                        print("[!] Click the target cube first")
                        continue
                    print(f"[place] Placing on {target_name}...")
                    cube_height = (raw.cube_half_size[2] * 2).item()
                    _, _, pick_result = held_cube
                    goal_pose = target_cube.pose * sapien.Pose([0, 0, cube_height])
                    held_actor = held_cube[0]
                    offset = (goal_pose.p - held_actor.pose.p).cpu().numpy()[0]
                    release_pose = sapien.Pose(
                        pick_result.lift_pose.p + offset,
                        pick_result.lift_pose.q,
                    )
                    result = place(
                        release_pose,
                        retract_height=pick_result.lift_pose.p[2],
                    )
                    if result.success:
                        print(f"[place] OK")
                    else:
                        print(f"[place] Failed: {result.failure_reason}")
                    held_cube = None
                    program_steps.append({
                        "skill": "place", "args": {"target": target_name},
                        "success": result.success,
                    })

                elif viewer.window.key_press("3"):  # PUSH
                    if held_cube is not None:
                        print("[!] Place the held cube first (2)")
                        continue
                    if transform_window is None:
                        print("[!] TransformWindow plugin not found")
                        continue
                    if viewer.selected_entity is None:
                        print("[!] Click a cube first to show the gizmo, then press 3")
                        continue
                    transform_window.follow = False
                    state = "awaiting_push_start"
                    print("[push] Drag gizmo to sweep START → press Enter")

            # --- PUSH: confirm start ---
            elif state == "awaiting_push_start":
                if viewer.window.key_press("escape"):
                    print("[push] Cancelled")
                    state = "idle"
                elif viewer.window.key_press("enter"):
                    pos = np.array(transform_window._gizmo_pose.p[:3],
                                   dtype=np.float32)
                    tcp_quat = np.array(euler2quat(0, np.pi, 0),
                                        dtype=np.float32)
                    push_start_pose = sapien.Pose(pos, tcp_quat)
                    _show_marker(start_marker, pos)
                    state = "awaiting_push_end"
                    print(f"[push] Start: [{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}] (green)")
                    print("[push] Drag gizmo to sweep END → press Enter")

            # --- PUSH: confirm end & execute ---
            elif state == "awaiting_push_end":
                if viewer.window.key_press("escape"):
                    print("[push] Cancelled")
                    _hide_marker(start_marker)
                    push_start_pose = None
                    state = "idle"
                elif viewer.window.key_press("enter"):
                    pos = np.array(transform_window._gizmo_pose.p[:3],
                                   dtype=np.float32)
                    tcp_quat = np.array(euler2quat(0, np.pi, 0),
                                        dtype=np.float32)
                    push_end_pose = sapien.Pose(pos, tcp_quat)
                    _show_marker(end_marker, pos)
                    print(f"[push] End: [{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}] (red)")
                    print("[push] Executing...")
                    result = push(push_start_pose, push_end_pose)
                    if result.success:
                        print("[push] OK")
                    else:
                        print(f"[push] Failed: {result.failure_reason}")
                    program_steps.append({
                        "skill": "push",
                        "args": {
                            "start_pose": push_start_pose.p.tolist(),
                            "end_pose": pos.tolist(),
                        },
                        "success": result.success,
                    })
                    _hide_marker(start_marker)
                    _hide_marker(end_marker)
                    push_start_pose = None
                    state = "idle"

            # --- Global keys ---
            if viewer.window.key_press("s"):
                _save_demo(scene_config, program_steps)

            elif viewer.window.key_press("r"):
                print("[reset] Resetting...")
                _hide_marker(start_marker)
                _hide_marker(end_marker)
                if hasattr(env, "flush_video"):
                    env.flush_video()
                env.reset(seed=seed)
                planner = setup_planner(env)
                cubes = _get_cube_list(env)
                scene_config["initial_poses"] = {
                    f"cube_{i}": cube.pose.p[0].cpu().numpy().tolist()
                    for i, cube in enumerate(cubes)
                }
                # Re-initialize skills with new planner
                pick = Pick(env, planner, step_callback=render)
                place = Place(env, planner, step_callback=render)
                push = Push(env, planner, step_callback=render)
                held_cube = None
                program_steps = []
                state = "idle"
                push_start_pose = None
                print("[reset] Done")

            elif viewer.window.key_press("q"):
                if program_steps:
                    _save_demo(scene_config, program_steps)
                print("[quit] Exiting...")
                break

        info = raw.evaluate()
        success = bool(info["success"])
        return SolverResult(success=success, info=dict(info))
