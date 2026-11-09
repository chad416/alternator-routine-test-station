"""Command line.

  python -m station test --frame medium [--fault DIODE_OPEN] [--type-test] [--serial S1]
  python -m station batch [--n 300] [--seed 1]        production mix  -> results/production.json
  python -m station sweep [--reps 10] [--seed 7]      every fault     -> results/sweep.json
  python -m station analyse                           summary, plots, test_times.json
  python -m station gif                               docs/img/test_run.gif
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import analysis
from .batch import load, production_plan, run_plan, save, sweep_plan
from .plant import FAULTS
from .recipe import ROOT, load_frames

RESULTS = ROOT / "results"
IMG = ROOT / "docs" / "img"


def cmd_test(a) -> None:
    from .batch import _init, run_one
    from .records import Store, diagnose, write_report
    from . import batch as b

    cfg = load_frames()
    _init(cfg)
    item = {"serial": a.serial, "frame": a.frame, "fault": a.fault, "type_test": a.type_test, "seed": a.seed}
    # run once with a trace for the report plot
    from .plant import make_unit
    from .recipe import Order, build_recipe

    rng = np.random.default_rng(a.seed)
    order = Order(a.serial, a.frame, a.type_test)
    unit = make_unit(a.frame, cfg["frames"][a.frame], a.serial, rng, a.fault)
    res = b._station.run(unit, build_recipe(order, cfg), a.type_test, rng, trace_every_s=1.0)
    rec = run_one(item, cfg)   # same seed -> same unit and result, as a stored record
    assert rec["verdict"] == bool(res.outputs["VERDICTPASS"])
    store = Store(RESULTS / "station.db")
    nc = store.add(rec)
    store.close()
    pdf, js = write_report(rec, Path(a.out), res.trace)
    print(f"{rec['serial']}: {'PASS' if rec['verdict'] else 'FAIL'} in {rec['test_time_s'] / 60:.1f} min on the bench "
          f"({rec['wall_s']:.2f} s to simulate)")
    if nc:
        print(f"non-conformity #{nc}: {diagnose(rec)[0]} -> {diagnose(rec)[1]}")
    print(f"report: {pdf}\n        {js}")


def _slim(records: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if k not in ("events", "recipe")} | {"recipe": r["recipe"]} for r in records]


def cmd_batch(a) -> None:
    cfg = load_frames()
    plan = production_plan(cfg, a.n, a.seed)
    t0 = time.time()
    recs = run_plan(plan, cfg, a.workers)
    save(_slim(recs), RESULTS / "production.json")
    print(f"{len(recs)} units in {time.time() - t0:.1f} s -> results/production.json")


def cmd_sweep(a) -> None:
    cfg = load_frames()
    plan = sweep_plan(cfg, a.reps, a.seed)
    t0 = time.time()
    recs = run_plan(plan, cfg, a.workers)
    save(_slim(recs), RESULTS / "sweep.json")
    print(f"{len(recs)} units in {time.time() - t0:.1f} s -> results/sweep.json")


def cmd_analyse(a) -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    prod = load(RESULTS / "production.json")
    sweep = load(RESULTS / "sweep.json")
    cap_cfg = json.loads((ROOT / "config" / "capacity.json").read_text())
    det = analysis.detection(sweep)
    summ = analysis.production_summary(prod)
    capab = analysis.capability(prod)
    tt = analysis.test_times(prod, cap_cfg)
    analysis.plot_detection(det, IMG / "detection.png")
    analysis.plot_spc(prod, IMG / "spc.png")
    analysis.plot_pareto(summ, IMG / "pareto.png")
    cap_rows = analysis.plot_capacity(tt, cap_cfg, IMG / "capacity.png")
    sweep_disagree = sum(1 for r in sweep for c in r["checks"].values() if c["done"] and c["py_pass"] != c["pass"])
    out = {
        "detection": det,
        "sweep_units": len(sweep),
        "sweep_rejected": sum(not r["verdict"] for r in sweep),
        "sweep_target_check_hit": sum(1 for r in sweep if r["checks"][FAULTS[r["fault"]][1]]["done"]
                                      and not r["checks"][FAULTS[r["fault"]][1]]["pass"]),
        "sweep_plc_vs_python_disagreements": sweep_disagree,
        "production": summ,
        "capability": capab,
        "test_times": tt,
        "capacity": cap_rows,
    }
    analysis.save_json(out, RESULTS / "summary.json")
    analysis.save_json(tt, RESULTS / "test_times.json")
    print(json.dumps({k: out[k] for k in ("sweep_units", "sweep_rejected", "sweep_target_check_hit",
                                          "sweep_plc_vs_python_disagreements")}, indent=1))
    print(json.dumps({k: v for k, v in summ.items() if k != "pareto"}, indent=1))
    print(json.dumps(cap_rows, indent=1))


def cmd_gif(a) -> None:
    from .gif import make_gif

    make_gif(IMG / "test_run.gif", frame=a.frame, seed=a.seed)
    print(f"wrote {IMG / 'test_run.gif'}")


def main() -> None:
    p = argparse.ArgumentParser(prog="station")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test", help="run one unit and write its report")
    t.add_argument("--frame", default="medium", choices=["small", "medium", "large"])
    t.add_argument("--fault", default=None, choices=sorted(FAULTS))
    t.add_argument("--type-test", action="store_true")
    t.add_argument("--serial", default="DEMO-0001")
    t.add_argument("--seed", type=int, default=1)
    t.add_argument("--out", default=str(RESULTS / "reports"))
    t.set_defaults(fn=cmd_test)
    b = sub.add_parser("batch", help="production mix")
    b.add_argument("--n", type=int, default=300)
    b.add_argument("--seed", type=int, default=1)
    b.add_argument("--workers", type=int, default=None)
    b.set_defaults(fn=cmd_batch)
    s = sub.add_parser("sweep", help="every fault on every frame")
    s.add_argument("--reps", type=int, default=10)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--workers", type=int, default=None)
    s.set_defaults(fn=cmd_sweep)
    an = sub.add_parser("analyse", help="summary, plots and test_times.json")
    an.set_defaults(fn=cmd_analyse)
    g = sub.add_parser("gif", help="animated test run")
    g.add_argument("--frame", default="medium")
    g.add_argument("--seed", type=int, default=3)
    g.set_defaults(fn=cmd_gif)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
