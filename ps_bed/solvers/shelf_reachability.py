"""Shelf reachability solver — sweep a grid through the shelf interior.

Creates an empty shelf (num_objects=0), loads shelf collision geometry
into the motion planner, then attempts to move the end effector to a
dense grid of positions inside the shelf.  Reports and visualises which
cells are reachable.
"""

import logging

import numpy as np
import sapien
from PIL import Image

from ps_bed.skills.motion import (
    GRIPPER_OPEN,
    add_collision_boxes,
    follow_path,
    move_to_pose,
    setup_planner,
)
from ps_bed.solvers.base import BaseSolver, SolverResult

logger = logging.getLogger("ps_bed.solvers.shelf_reachability")

# Gripper pointing into shelf (+X direction), wxyz
Q_INTO_SHELF = [0.7071068, 0.0, 0.7071068, 0.0]


class ShelfReachabilitySolver(BaseSolver):
    """Sweep a grid through the shelf and report reachability."""

    def solve(self, env, seed=None) -> SolverResult:
        env.reset(seed=seed)
        raw = env.unwrapped

        # Get shelf geometry
        from ps_bed.envs.shelf_env import (
            SHELF_BACK_X,
            SHELF_CEIL_Z,
            SHELF_FRONT_X,
            SHELF_HALF_W,
            SHELF_SURFACE_Z,
        )

        boxes = raw.get_collision_boxes()

        # Grid resolution — finer Z sampling to find the reachable band
        nx, ny, nz = 5, 7, 8
        xs = np.linspace(SHELF_FRONT_X + 0.03, SHELF_BACK_X - 0.03, nx)
        ys = np.linspace(-SHELF_HALF_W + 0.03, SHELF_HALF_W - 0.03, ny)
        zs = np.linspace(SHELF_SURFACE_Z + 0.03, SHELF_CEIL_Z - 0.03, nz)

        total = nx * ny * nz
        reachable = 0
        results = np.zeros((nx, ny, nz), dtype=bool)

        logger.info(
            "Shelf reachability test: %d x %d x %d = %d grid points",
            nx, ny, nz, total,
        )
        logger.info(
            "X: [%.2f, %.2f], Y: [%.2f, %.2f], Z: [%.2f, %.2f]",
            xs[0], xs[-1], ys[0], ys[-1], zs[0], zs[-1],
        )

        for ix, x in enumerate(xs):
            for iy, y in enumerate(ys):
                for iz, z in enumerate(zs):
                    # Reset robot to home each time for clean start
                    env.reset(seed=seed)
                    planner = setup_planner(env)
                    add_collision_boxes(planner, boxes, resolution=0.02)

                    pose = sapien.Pose(p=[x, y, z], q=Q_INTO_SHELF)
                    result = move_to_pose(
                        env, planner, pose, GRIPPER_OPEN, dry_run=True,
                    )
                    ok = result != -1
                    results[ix, iy, iz] = ok
                    if ok:
                        reachable += 1

                    status = "OK" if ok else "FAIL"
                    logger.info(
                        "  [%d/%d] x=%.2f y=%+.2f z=%.2f -> %s",
                        ix * ny * nz + iy * nz + iz + 1,
                        total, x, y, z, status,
                    )

        # Print summary
        pct = 100 * reachable / total if total else 0
        logger.info("=" * 60)
        logger.info(
            "REACHABILITY: %d / %d (%.1f%%)", reachable, total, pct,
        )

        # Print per-Z-layer heatmap
        for iz, z in enumerate(zs):
            layer = results[:, :, iz]
            count = layer.sum()
            logger.info(
                "\nZ = %.3f  (%d/%d reachable):", z, count, nx * ny,
            )
            # Print grid: rows = X (front to back), cols = Y (left to right)
            header = "       " + "  ".join(f"y={y:+.2f}" for y in ys)
            logger.info(header)
            for ix, x in enumerate(xs):
                row = "  ".join(
                    "  OK  " if layer[ix, iy] else " FAIL " for iy in range(ny)
                )
                logger.info("x=%.2f  %s", x, row)

        # Execute one reachable point to verify it works in sim
        if reachable > 0:
            idx = np.argwhere(results)
            ix, iy, iz = idx[0]
            x, y, z = xs[ix], ys[iy], zs[iz]
            logger.info(
                "\nExecuting motion to first reachable point: "
                "x=%.2f y=%.2f z=%.2f", x, y, z,
            )
            env.reset(seed=seed)
            planner = setup_planner(env)
            add_collision_boxes(planner, boxes, resolution=0.02)
            pose = sapien.Pose(p=[x, y, z], q=Q_INTO_SHELF)
            step_result = move_to_pose(
                env, planner, pose, GRIPPER_OPEN,
            )
            if step_result != -1:
                try:
                    img = env.render()
                    img_np = img[0].cpu().numpy()
                    if img_np.max() <= 1.0:
                        img_np = (img_np * 255).astype(np.uint8)
                    Image.fromarray(img_np).save(
                        "videos/shelf_reachability_demo.png"
                    )
                    logger.info(
                        "Snapshot saved: videos/shelf_reachability_demo.png"
                    )
                except RuntimeError:
                    logger.info("Snapshot skipped (no render_mode set)")

        return SolverResult(
            success=reachable > 0,
            info={
                "reachable": reachable,
                "total": total,
                "reachable_pct": pct,
                "grid_shape": (nx, ny, nz),
            },
        )
