"""Animated test run for the README: what the bench does, step by step."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402

from .plant import make_unit  # noqa: E402
from .recipe import Order, build_recipe, load_frames  # noqa: E402
from .runner import Station  # noqa: E402

LABELS = {
    "PRECHECK": "Pre-checks", "RES": "Winding resistances", "IR_BEFORE": "Insulation resistance",
    "HV_RAMP": "Dielectric test", "HV_HOLD": "Dielectric test", "HV_DOWN": "Discharge",
    "IR_AFTER": "Insulation after HV", "RUNUP_EXT": "Run-up, external excitation",
    "NOLOAD_EXT": "No load: field current for Un", "ONLOAD_EXT": "On load PF 0.8: field current",
    "CUTOFF": "Load cut-off: saturated voltage", "STOP_EXT": "De-excite, stop",
    "RUNUP_AVR": "Run-up with AVR: build-up", "AVR_NOLOAD": "AVR no-load voltage",
    "PF08": "AVR on load PF 0.8", "PF10": "AVR on load PF 1.0", "OVERLOAD": "Overload 150 %",
    "UNLOAD": "Unload", "STAR_DEEXC": "Reconnect to star", "STAR_CHECK": "Star voltage",
    "REMANENT": "Remanent voltage", "OVERSPEED_UP": "Overspeed 120 %", "OVERSPEED_HOLD": "Overspeed 120 %",
    "RUNDOWN": "Run-down", "PROBES": "PT100 / PTC / heater", "FINISH": "Report", "DONE": "Done",
}


def make_gif(path: Path, frame: str = "medium", seed: int = 3, n_frames: int = 90) -> None:
    cfg = load_frames()
    st = Station(cfg)
    rng = np.random.default_rng(seed)
    order = Order("GIF-0001", frame, False)
    unit = make_unit(frame, cfg["frames"][frame], order.serial, rng, None)
    res = st.run(unit, build_recipe(order, cfg), False, rng, trace_every_s=0.5)
    tr = {k: np.asarray(v) for k, v in res.trace.items()}
    names = st.plc.step_names()
    t_min = tr["t"] / 60.0
    end = t_min[-1]

    fig, axes = plt.subplots(4, 1, figsize=(8, 6.2), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1, 1, 1]})
    series = [
        ("speed", "speed\n[rpm]", "#57606a"),
        ("u", "voltage\n[V]", "#1f6feb"),
        ("iexc", "exciter\n[A]", "#d97706"),
        ("p_kw", "load [kW]\nHV [kV x100]", "#1a7f37"),
    ]
    lines = []
    for ax, (key, label, col) in zip(axes, series):
        ax.plot(t_min, tr[key], color=col, lw=0.6, alpha=0.18)
        ln, = ax.plot([], [], color=col, lw=1.3)
        lines.append(ln)
        ax.set_ylabel(label, fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    hv_line, = axes[3].plot([], [], color="#c62828", lw=1.3)
    axes[3].plot(t_min, tr["hv_kv"] * 100, color="#c62828", lw=0.6, alpha=0.18)
    axes[-1].set_xlabel("time on the bench [min]", fontsize=8)
    axes[-1].set_xlim(0, end)
    title = fig.suptitle("", x=0.02, ha="left", fontsize=11, weight="bold")
    fig.text(0.02, 0.935, f"{unit.kva:.0f} kVA alternator, PLC sequence in Structured Text (simulated bench)",
             fontsize=8, color="0.4")
    fig.tight_layout(rect=(0, 0, 1, 0.93))

    idx = np.linspace(1, len(t_min) - 1, n_frames).astype(int)

    def draw(k):
        i = idx[k]
        for ln, (key, _, _) in zip(lines, series):
            ln.set_data(t_min[:i], tr[key][:i])
        hv_line.set_data(t_min[:i], tr["hv_kv"][:i] * 100)
        step = names.get(int(tr["step"][i]), "")
        title.set_text(f"{t_min[i]:4.1f} min   {LABELS.get(step, step)}")
        return lines

    anim = FuncAnimation(fig, draw, frames=n_frames, blit=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    anim.save(path, writer=PillowWriter(fps=8), dpi=80)
    plt.close(fig)
