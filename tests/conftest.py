import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from station.plant import make_unit  # noqa: E402
from station.recipe import Order, build_recipe, load_frames  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_frames()


@pytest.fixture(scope="session")
def station(cfg):
    lib = ROOT / "build" / "plc" / "librt.so"
    if not lib.exists():
        pytest.exit("build/plc/librt.so missing: run scripts/build_plc.sh first", returncode=2)
    from station.runner import Station
    return Station(cfg)


@pytest.fixture
def run(cfg, station):
    """run(frame, fault=None, type_test=False, seed=1, **kw) -> (RunResult, unit, recipe)"""
    def _run(frame, fault=None, type_test=False, seed=1, recipe_override=None, **kw):
        rng = np.random.default_rng(seed)
        order = Order(f"T-{frame}-{fault}-{seed}", frame, type_test)
        unit = make_unit(frame, cfg["frames"][frame], order.serial, rng, fault)
        recipe = build_recipe(order, cfg)
        if recipe_override:
            recipe.update(recipe_override)
        res = station.run(unit, recipe, type_test, rng, **kw)
        return res, unit, recipe
    return _run
