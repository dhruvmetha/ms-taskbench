from importlib import import_module

SOLVER_REGISTRY = {
    "stack_cubes": "ps_bed.solvers.stack_cubes:StackCubesSolver",
    "demo_recorder": "ps_bed.solvers.demo_recorder:DemoRecorderSolver",
    "shelf_reachability": "ps_bed.solvers.shelf_reachability:ShelfReachabilitySolver",
}


def get_solver(name):
    """Lazy-import and instantiate a solver by registry name.

    Raises KeyError if the name is not in SOLVER_REGISTRY.
    """
    if name not in SOLVER_REGISTRY:
        available = ", ".join(sorted(SOLVER_REGISTRY))
        raise KeyError(f"Unknown solver {name!r}. Available: {available}")

    module_path, cls_name = SOLVER_REGISTRY[name].rsplit(":", 1)
    module = import_module(module_path)
    cls = getattr(module, cls_name)
    return cls()
