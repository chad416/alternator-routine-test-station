"""Run many simulated units in parallel and collect their records.

Two plans:
  production  a mix of frames, about 12 % of units with one injected fault
  sweep       every applicable fault on every frame, `reps` times each
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
from pathlib import Path

import numpy as np

from .checks import CHECKS, decode, reevaluate
from .plant import FAULTS, make_unit
from .recipe import Order, bench_limited, build_recipe

FRAME_MIX = {"small": 0.5, "medium": 0.3, "large": 0.2}
FAULT_RATE = 0.12
TYPE_TEST_RATE = 0.05

_station = None


def applicable_faults(frame: dict) -> list[str]:
    out = []
    for f in FAULTS:
        if f == "STAR_LINK" and not frame["test_delta"]:
            continue
        if f == "CT_REVERSED" and not frame["ct_fitted"]:
            continue
        if f == "HEATER_OPEN" and frame["heater_w"] <= 0:
            continue
        out.append(f)
    return out


def production_plan(cfg: dict, n: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    frames = list(FRAME_MIX)
    probs = np.array([FRAME_MIX[f] for f in frames])
    plan = []
    for i in range(n):
        frame = str(rng.choice(frames, p=probs))
        fr = cfg["frames"][frame]
        fault = str(rng.choice(applicable_faults(fr))) if rng.random() < FAULT_RATE else None
        p_test = min(0.8 * fr["kva"], cfg["bench"]["max_kw"])
        type_test = 1.5 * p_test <= cfg["bench"]["max_kw"] and rng.random() < TYPE_TEST_RATE
        plan.append({"serial": f"S{seed:02d}-{i + 1:04d}", "frame": frame, "fault": fault,
                     "type_test": bool(type_test), "seed": seed * 100000 + i})
    return plan


def sweep_plan(cfg: dict, reps: int, seed: int) -> list[dict]:
    plan = []
    i = 0
    for frame, fr in cfg["frames"].items():
        for fault in applicable_faults(fr):
            for r in range(reps):
                plan.append({"serial": f"F{seed:02d}-{i + 1:04d}", "frame": frame, "fault": fault,
                             "type_test": False, "seed": seed * 100000 + i})
                i += 1
    return plan


def _init(cfg: dict) -> None:
    global _station
    from .runner import Station
    _station = Station(cfg)


def run_one(item: dict, cfg: dict) -> dict:
    st = _station
    rng = np.random.default_rng(item["seed"])
    order = Order(item["serial"], item["frame"], item["type_test"])
    unit = make_unit(item["frame"], cfg["frames"][item["frame"]], item["serial"], rng, item["fault"])
    recipe = build_recipe(order, cfg)
    res = st.run(unit, recipe, item["type_test"], rng)
    ids = st.plc.check_ids()
    bits = decode(res.outputs, ids)
    py = reevaluate(res.outputs, recipe, res.context)
    o = res.outputs
    checks = {}
    for c in CHECKS:
        b = bits[c.name]
        lo, hi = c.limits(recipe)
        checks[c.name] = {
            "expected": b["expected"], "done": b["done"], "pass": b["pass"],
            "value": float(o[c.result]) if c.result else None,
            "lo": lo, "hi": hi, "py_pass": py[c.name] if b["done"] else None,
        }
    first = int(o["FIRSTFAIL"])
    first_name = next((k for k, v in ids.items() if v == first), None) if first else None
    return {
        **item,
        "verdict": bool(o["VERDICTPASS"]),
        "aborted": bool(o["ABORTED"]),
        "abort_code": int(o["ABORTCODE"]),
        "first_fail": first_name,
        "test_time_s": float(o["TESTTIME"]),
        "wall_s": res.wall_time_s,
        "recipe": recipe,
        "checks": checks,
        "events": res.events,
        "bench_limited": bench_limited(Order("", item["frame"]), cfg),
        "t_amb": unit.t_amb,
    }


def _worker(args):
    item, cfg = args
    return run_one(item, cfg)


def run_plan(plan: list[dict], cfg: dict, workers: int | None = None) -> list[dict]:
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    if workers == 1:
        _init(cfg)
        return [run_one(it, cfg) for it in plan]
    ctx = mp.get_context("fork")
    with ctx.Pool(workers, initializer=_init, initargs=(cfg,)) as pool:
        return pool.map(_worker, [(it, cfg) for it in plan], chunksize=4)


def save(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=0), encoding="utf-8")


def load(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
