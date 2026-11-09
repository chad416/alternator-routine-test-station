"""Batch analysis: fault detection, false rejects, SPC / Cpk, test time and
test-bench capacity."""

from __future__ import annotations

import collections
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import __version__  # noqa: E402
from .checks import CHECKS  # noqa: E402
from .plant import FAULTS  # noqa: E402
from .records import diagnose, failed_checks  # noqa: E402

CHECK_ORDER = [c.name for c in CHECKS]
FRAME_ORDER = ["small", "medium", "large"]
INK = "#24292f"
BLUE = "#1f6feb"
RED = "#c62828"
GREEN = "#1a7f37"
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


# ---------------------------------------------------------------- detection
def detection(sweep: list[dict]) -> dict:
    """Per injected fault: share of units rejected, and how often each check
    failed."""
    by = collections.defaultdict(list)
    for r in sweep:
        by[r["fault"]].append(r)
    out = {}
    for fault, recs in by.items():
        counts = collections.Counter(c for r in recs for c in failed_checks(r))
        out[fault] = {
            "units": len(recs),
            "rejected": sum(not r["verdict"] for r in recs),
            "aborted": sum(r["aborted"] for r in recs),
            "target_check": FAULTS[fault][1],
            "target_hits": counts.get(FAULTS[fault][1], 0),
            "checks": dict(counts),
            "routes": dict(collections.Counter(diagnose(r)[1] for r in recs if not r["verdict"])),
        }
    return out


def plot_detection(det: dict, path: Path) -> None:
    faults = [f for f in FAULTS if f in det]
    checks = [c for c in CHECK_ORDER if any(c in det[f]["checks"] for f in faults)]
    m = np.zeros((len(faults), len(checks)))
    for i, f in enumerate(faults):
        for j, c in enumerate(checks):
            m[i, j] = det[f]["checks"].get(c, 0) / det[f]["units"]
    fig, ax = plt.subplots(figsize=(9.5, 6.4))
    ax.imshow(m, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(checks)), checks, rotation=60, ha="right", fontsize=8)
    ylabels = [f"{f}  ({det[f]['rejected']}/{det[f]['units']})" for f in faults]
    ax.set_yticks(range(len(faults)), ylabels, fontsize=8)
    for i in range(len(faults)):
        for j in range(len(checks)):
            if m[i, j] > 0:
                ax.text(j, i, f"{m[i, j] * 100:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if m[i, j] > 0.6 else INK)
    ax.set_title("Injected fault vs failed check (% of units). Rejected / tested in brackets", loc="left")
    for s in ax.spines.values():
        s.set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------- production
def production_summary(prod: list[dict]) -> dict:
    good = [r for r in prod if r["fault"] is None]
    bad = [r for r in prod if r["fault"] is not None]
    false_rejects = [r for r in good if not r["verdict"]]
    escapes = [r for r in bad if r["verdict"]]
    pareto = collections.Counter()
    for r in prod:
        if not r["verdict"]:
            pareto[diagnose(r)[0]] += 1
    times = collections.defaultdict(list)
    for r in prod:
        if r["verdict"]:
            times[(r["frame"], r["type_test"])].append(r["test_time_s"])
    return {
        "units": len(prod),
        "faulty_units": len(bad),
        "passed": sum(r["verdict"] for r in prod),
        "false_rejects": [{"serial": r["serial"], "frame": r["frame"], "failed": failed_checks(r)} for r in false_rejects],
        "escapes": [{"serial": r["serial"], "fault": r["fault"]} for r in escapes],
        "aborted": sum(r["aborted"] for r in prod),
        "pareto": pareto.most_common(),
        "test_time_s": {f"{f}{' type' if tt else ''}": {"n": len(v), "mean": float(np.mean(v)), "max": float(np.max(v))}
                        for (f, tt), v in sorted(times.items())},
        "plc_vs_python_disagreements": sum(1 for r in prod for c in r["checks"].values()
                                           if c["done"] and c["py_pass"] != c["pass"]),
    }


NO_CPK = {"PHASE_SEQ", "IR_BEFORE", "IR_AFTER", "OVERSPEED"}

SPC_CHECKS = ["IF_NOLOAD", "IF_LOAD", "SAT", "UNBAL", "R_STATOR", "REG_PF08", "BUILDUP", "REMANENT"]


def _norm(c: dict) -> float | None:
    """Value as a position in its tolerance band: -1 = lower limit, +1 =
    upper limit (one-sided limits use 0 = limit)."""
    v, lo, hi = c["value"], c["lo"], c["hi"]
    if v is None:
        return None
    if lo is not None and hi is not None:
        mid, half = (lo + hi) / 2, (hi - lo) / 2
        return (v - mid) / half
    return v


def cpk(values: list[float], lo, hi) -> float | None:
    if len(values) < 10:
        return None
    mu, sd = float(np.mean(values)), float(np.std(values, ddof=1))
    if sd <= 0:
        return None
    parts = []
    if hi is not None:
        parts.append((hi - mu) / (3 * sd))
    if lo is not None:
        parts.append((mu - lo) / (3 * sd))
    return min(parts) if parts else None


def capability(prod: list[dict]) -> dict:
    """Cpk per check and frame, on units built without an injected fault."""
    out: dict = {}
    for frame in FRAME_ORDER:
        recs = [r for r in prod if r["frame"] == frame and r["fault"] is None]
        for name in CHECK_ORDER:
            vals = [r["checks"][name]["value"] for r in recs if r["checks"][name]["done"]]
            # insulation resistance is log-normal and one-sided: Cpk would mislead
            if not vals or name in NO_CPK:
                continue
            c0 = next(r["checks"][name] for r in recs if r["checks"][name]["done"])
            k = cpk(vals, c0["lo"], c0["hi"])
            if k is None:
                continue
            out.setdefault(name, {})[frame] = {"n": len(vals), "mean": float(np.mean(vals)),
                                                "sd": float(np.std(vals, ddof=1)), "cpk": round(k, 2)}
    return out


def plot_spc(prod: list[dict], path: Path) -> None:
    """Individuals charts: each value as a position in its tolerance band, in
    test order, with the injected faults marked."""
    fig, axes = plt.subplots(4, 2, figsize=(11, 9.5), sharex=True)
    for ax, name in zip(axes.flat, SPC_CHECKS):
        xs, ys, cols = [], [], []
        for i, r in enumerate(prod):
            c = r["checks"][name]
            if not c["done"]:
                continue
            y = _norm(c)
            if y is None:
                continue
            xs.append(i)
            ys.append(y)
            cols.append(RED if r["fault"] else (BLUE if c["pass"] else "#d97706"))
        ax.scatter(xs, ys, s=6, c=cols, linewidths=0)
        c0 = next(r["checks"][name] for r in prod if r["checks"][name]["done"])
        two_sided = c0["lo"] is not None and c0["hi"] is not None
        if two_sided:
            for y in (-1, 1):
                ax.axhline(y, color=RED, lw=0.8, ls="--")
            good = [y for y, col in zip(ys, cols) if col != RED]
            if len(good) > 10:
                mu, sd = np.mean(good), np.std(good, ddof=1)
                ax.axhline(mu, color=INK, lw=0.6)
                for y in (mu - 3 * sd, mu + 3 * sd):
                    ax.axhline(y, color="0.5", lw=0.6, ls=":")
            ax.set_ylim(-2.2, 2.2)
            ax.set_ylabel("in band (-1..+1)", fontsize=7)
        else:
            lim = c0["lo"] if c0["lo"] is not None else c0["hi"]
            ax.axhline(lim, color=RED, lw=0.8, ls="--")
            ax.set_ylabel(next(c.unit for c in CHECKS if c.name == name), fontsize=7)
        ax.set_title(f"{name}: {next(c.title for c in CHECKS if c.name == name)}", fontsize=8.5, loc="left")
        ax.grid(alpha=0.25)
    for ax in axes[-1]:
        ax.set_xlabel("unit in test order")
    fig.suptitle("SPC: blue = built OK and passed, orange = built OK but rejected, red = injected fault. "
                 "Dashed = limits, dotted = mean +/- 3 sigma", fontsize=9, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_pareto(summary: dict, path: Path) -> None:
    items = summary["pareto"][:10]
    if not items:
        return
    labels = [k if len(k) < 70 else k[:67] + "..." for k, _ in items][::-1]
    counts = [v for _, v in items][::-1]
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.barh(labels, counts, color=BLUE)
    for i, v in enumerate(counts):
        ax.text(v + 0.1, i, str(v), va="center", fontsize=8)
    ax.set_xlabel("rejected units")
    ax.set_title(f"Non-conformity causes, {summary['units']} units tested", loc="left")
    ax.tick_params(axis="y", labelsize=7.5)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------- capacity
def test_times(prod: list[dict], cap_cfg: dict) -> dict:
    """Average sequence time per frame (passed units), plus the extra time of
    a type test, for the plant ramp-up model."""
    out = {"source": f"alternator-routine-test-station v{__version__}", "frames": {},
           "changeover_s": cap_cfg["changeover_s"],
           "note": "routine_s = mean PLC sequence time of passed units (simulated). handling_s = mounting, "
                   "coupling, wiring and removal per unit, an assumption from config/capacity.json; bench "
                   "occupation = routine_s + handling_s. type_test_extra_s = 0 where the bench cannot run "
                   "the type test (load above bench power)."}
    for frame in FRAME_ORDER:
        rt = [r["test_time_s"] for r in prod if r["frame"] == frame and r["verdict"] and not r["type_test"]]
        tt = [r["test_time_s"] for r in prod if r["frame"] == frame and r["verdict"] and r["type_test"]]
        if not rt:
            continue
        seq = float(np.mean(rt))
        hand = float(cap_cfg["handling_s"][frame])
        out["frames"][frame] = {
            "routine_s": round(seq, 1),
            "handling_s": hand,
            "type_test_extra_s": round(float(np.mean(tt)) - seq, 1) if tt else 0.0,
            "type_test_on_this_bench": bool(tt),
            "n": len(rt),
        }
    return out


def benches_needed(tt: dict, cap_cfg: dict, multiplier: float, handling_scale: float = 1.0) -> dict:
    """Bench hours per day at `multiplier` x today's demand. `handling_scale`
    shrinks mounting/coupling/wiring time (e.g. 0.5 = quick-connect fixtures)."""
    hours = cap_cfg["shifts_per_day"] * cap_cfg["hours_per_shift"] * cap_cfg["bench_availability"]
    seq_s = hand_s = 0.0
    for frame, per_day in cap_cfg["demand_per_day"].items():
        f = tt["frames"][frame]
        n = per_day * multiplier * (1.0 + cap_cfg["retest_rate"])
        seq_s += n * f["routine_s"]
        hand_s += n * f["handling_s"] * handling_scale
    chg_s = cap_cfg["changeovers_per_day"] * tt["changeover_s"]
    total = seq_s + hand_s + chg_s
    need = total / 3600.0 / hours
    return {"multiplier": multiplier, "handling_scale": handling_scale,
            "sequence_h": round(seq_s / 3600.0, 1), "handling_h": round(hand_s / 3600.0, 1),
            "changeover_h": round(chg_s / 3600.0, 1), "bench_hours_per_day": round(total / 3600.0, 1),
            "utilisation_one_bench": round(need, 2), "benches": math.ceil(need - 1e-9)}


def plot_capacity(tt: dict, cap_cfg: dict, path: Path) -> list[dict]:
    mults = (1.0, 2.0, 3.0)
    rows = [benches_needed(tt, cap_cfg, m) for m in mults]
    rows_q = [benches_needed(tt, cap_cfg, m, handling_scale=0.5) for m in mults]
    hours = cap_cfg["shifts_per_day"] * cap_cfg["hours_per_shift"] * cap_cfg["bench_availability"]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    w = 0.36
    for k, (rs, dx, tag) in enumerate(((rows, -w / 2 - 0.02, "today's handling"),
                                       (rows_q, w / 2 + 0.02, "handling halved"))):
        x = np.arange(len(mults)) + dx
        seq = [r["sequence_h"] / hours for r in rs]
        hand = [r["handling_h"] / hours for r in rs]
        chg = [r["changeover_h"] / hours for r in rs]
        a = 1.0 if k == 0 else 0.55
        ax.bar(x, seq, w, color=BLUE, alpha=a, label="test sequence (PLC)" if k == 0 else None)
        ax.bar(x, hand, w, bottom=seq, color="#d97706", alpha=a, label="mounting, coupling, wiring" if k == 0 else None)
        ax.bar(x, chg, w, bottom=np.add(seq, hand), color="0.6", alpha=a, label="changeovers" if k == 0 else None)
        for xi, r in zip(x, rs):
            ax.text(xi, r["utilisation_one_bench"] + 0.04, f"{r['benches']}", ha="center", fontsize=9, weight="bold")
            ax.text(xi, -0.16, tag.split()[0] if k == 0 else "halved", ha="center", fontsize=7, color="0.4")
    ax.set_xticks(range(len(mults)), [f"{m:g}x output" for m in mults])
    ax.tick_params(axis="x", pad=14)
    ax.set_ylabel("benches of work (bold = benches needed)")
    ax.set_ylim(0, max(r["utilisation_one_bench"] for r in rows) * 1.25)
    ax.legend(fontsize=8, loc="upper left", frameon=False)
    ax.set_title(f"Test-bench load per day ({cap_cfg['shifts_per_day']} shifts, {hours:.1f} productive h per bench). "
                 "Left bar: today's handling, right bar: handling halved", loc="left", fontsize=8.5)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return rows + rows_q


def save_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1), encoding="utf-8")
