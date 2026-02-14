# Testing Patterns

**Analysis Date:** 2025-02-13

## Test Status

**No tests exist in this repository.**

As documented in `CLAUDE.md`: "No tests exist in this repo."

The codebase contains no test files, test configuration, or testing framework setup. Testing patterns are not yet established.

## Test Framework

**Runner:**
- Not configured
- No pytest.ini, setup.cfg, or pyproject.toml test configuration
- No test dependencies in `pyproject.toml`

**Assertion Library:**
- Not applicable (no tests)

**Run Commands:**
- No test commands configured

## Test File Organization

**Current Status:**
- No `tests/` directory exists
- No `*_test.py` or `test_*.py` files found

**Recommended Pattern (for future implementation):**
Use co-located test pattern:
- Place test files alongside source: `ps_bed/run_test.py` next to `ps_bed/run.py`
- Or use separate `tests/` directory: `tests/test_run.py`, `tests/test_env.py`, etc.

## Key Areas That Need Testing

Based on codebase analysis, these areas would benefit from test coverage:

### 1. Configuration and Entry Point (`ps_bed/run.py`)

**What should be tested:**
- Seed setting across all libraries (numpy, torch, random)
- Episode loop with vectorized environment
- Episode loop with single-env motion planner
- Policy selection (random vs pick_place)
- Summary statistics calculation
- Logging integration (WandB enable/disable)

**Current logic pattern to test:**
```python
def run_random(config: Config, logger: Logger):
    """Run episodes with random actions using the vectorized env."""
    # Tests should verify:
    # - Correct number of episodes collected
    # - All returns/lengths/successes tracked
    # - Early exit when target_episodes reached
    # - Proper handling of torch.Tensor conversions
```

### 2. Environment Factory (`ps_bed/env.py`)

**What should be tested:**
- `make_env()` creates vectorized environment with correct wrappers
- `make_single_env()` creates raw gym env without vectorization
- Video recording setup with RecordEpisode
- Render mode configuration
- sim_backend="cpu" only applied to single-env

**Example test areas:**
- Environment reset works and returns obs/info
- Action space sampling produces valid actions
- Step returns valid (obs, reward, terminated, truncated, info) tuples

### 3. Motion Planning (`ps_bed/skills/pick_place.py`)

**What should be tested:**
- SAPIEN-to-mplib pose conversion with batched tensors
- Planner initialization from environment
- Path following (trajectory execution)
- Gripper actuation (open/close)
- Screw motion planning with retry logic
- Full solve() sequence completes without exceptions

**Critical test case:**
```python
def test_sapien_to_mplib_pose_handles_batched():
    """Verify pose conversion flattens batched tensor dimensions."""
    # SAPIEN poses have shape (1, 3) for position
    # Must flatten to (3,) for mplib
    batched_pose = sapien.Pose(p=torch.zeros(1, 3), q=torch.zeros(1, 4))
    result = _sapien_to_mplib_pose(batched_pose)
    # assert result.p.shape == (3,)
```

**Retry logic test:**
```python
def test_move_to_pose_retries_on_failure():
    """Verify screw planning retries once on failure."""
    # Result with status != "Success" should trigger retry
    # Second retry failure should log and return -1
```

### 4. Custom Environment (`ps_bed/envs/stack_cube_distractor.py`)

**What should be tested:**
- Environment registers with correct ID and episode steps
- Blue distractor cube spawns at default location
- `force_close_distractor=True` places cube next to cubeA
- Observation includes cubeC_pose when obs_mode=="state"
- Inherits all StackCubeEnv behavior correctly

### 5. Logging (`ps_bed/logger.py`)

**What should be tested:**
- Logger initializes with WandB disabled by default
- `log_episode()` no-ops when WandB disabled
- `log_episode()` calls wandb.log() when enabled
- `log_summary()` updates wandb.run.summary
- `finish()` calls run.finish() when enabled

**Mock pattern:**
```python
def test_logger_respects_wandb_disable():
    """Logger should not initialize wandb when disabled."""
    config = Config(logging=LoggingConfig(use_wandb=False))
    logger = Logger(config)
    # assert logger._run is None
```

## Mocking Strategy (for future tests)

**What to Mock:**
- `gymnasium.make()` — return mock environment
- `mplib.Planner` — return mock planner with predictable plan results
- `wandb` module — prevent actual WandB initialization
- SAPIEN objects (`sapien.Pose`, `robot`, `scene`) — use fixtures

**What NOT to Mock:**
- Hydra configuration loading (or test with actual config)
- Dataclass instantiation
- Tensor/numpy operations (test with real values)

**Example mock structure:**
```python
@pytest.fixture
def mock_env():
    """Create a mock gym environment."""
    env = MagicMock()
    env.reset.return_value = (np.zeros((16, 100)), {})
    env.step.return_value = (
        np.zeros((16, 100)),  # obs
        np.ones(16),          # rewards
        np.zeros(16, dtype=bool),  # terminations
        np.zeros(16, dtype=bool),  # truncations
        {"success": np.ones(16, dtype=bool)}
    )
    return env

@pytest.fixture
def mock_single_env():
    """Create a mock gym environment for planner."""
    env = MagicMock()
    env.unwrapped.control_mode = "pd_joint_pos"
    env.reset.return_value = (np.zeros(100), {})
    env.step.return_value = (
        np.zeros(100),  # obs
        1.0,            # reward
        False,          # terminated
        False,          # truncated
        {"success": True}
    )
    return env
```

## Test Coverage Priorities

**Priority 1 - Critical Path (High Risk):**
1. Pose conversion `_sapien_to_mplib_pose()` — robotics-critical, easy to test
2. Episode loop termination logic in `run_random()` — off-by-one bugs common
3. Motion planner retry logic in `_move_to_pose_with_screw()` — planning robustness
4. Distractor environment cube placement — validation for research

**Priority 2 - Integration (Medium Risk):**
1. Full `solve()` sequence with mocked environment
2. Video recording enable/disable
3. WandB logging enable/disable
4. Configuration parsing and override

**Priority 3 - Utility (Low Risk):**
1. `seed_everything()` function
2. Logger initialization
3. Summary statistics calculation

## Recommended Test Structure

For future test implementation, use this pattern:

```
tests/
├── __init__.py
├── conftest.py                 # shared fixtures (mock_env, mock_planner, etc.)
├── unit/
│   ├── test_config.py         # Config dataclass parsing
│   ├── test_logger.py         # Logger class
│   ├── test_pick_place.py     # PickPlaceSkill methods
│   └── test_env.py            # Factory functions
└── integration/
    ├── test_run_random.py     # Full episode loop
    └── test_run_pick_place.py # Motion planner integration
```

## Async/Concurrency Testing

**Not applicable** — No async/await patterns in codebase. All code is synchronous.

## Fixture Patterns to Use

**Configuration fixtures:**
```python
@pytest.fixture
def default_config():
    """Return minimal Config for testing."""
    return Config()

@pytest.fixture
def pick_place_config():
    """Config for motion planner testing."""
    cfg = Config()
    cfg.run.policy = "pick_place"
    cfg.env.num_envs = 1
    return cfg
```

**Numpy array fixtures:**
```python
@pytest.fixture
def sample_qpos():
    """Sample joint positions for robot."""
    return np.array([0.0, 0.0, 0.0, -1.57, 0.0, 1.57, 0.0, 0.04, 0.04])
```

---

*Testing analysis: 2025-02-13*
