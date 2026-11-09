"""Scan loop: bench measurements -> PLC -> bench commands -> plant."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .plant import Bench, Unit
from .plc import Plc

COMMANDS = ("QDRIVERUN", "QSPEEDSP", "QEXCMODE", "QIEXCSP", "QAVRUSP", "QLOADON", "QLOADKW",
            "QLOADPF", "QHVON", "QHVKVSP", "QIRON", "QIRKV", "QRCH", "QPROBECH", "QCONNDELTA")


@dataclass
class RunResult:
    serial: str
    frame: str
    fault: str | None
    type_test: bool
    outputs: dict                # PLC outputs at the end (results, verdict, bits)
    recipe: dict
    sim_time_s: float
    wall_time_s: float
    scans: int
    trace: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    context: dict = field(default_factory=dict)   # bench boolean signals for checks.reevaluate


class Station:
    def __init__(self, cfg: dict, plc: Plc | None = None):
        self.cfg = cfg
        self.plc = plc or Plc()
        self.dt = cfg["bench"]["scan_s"]
        self.step_names = self.plc.step_names()

    def run(self, unit: Unit, recipe: dict, type_test: bool, rng: np.random.Generator,
            trace_every_s: float = 0.0, max_sim_s: float = 3600.0, hooks=None, observer=None,
            stop_on_done: bool = True) -> RunResult:
        """Run one complete routine test.

        hooks(t, bench, hmi)        may change bench or HMI signals before each scan
        observer(t, bench, out)     sees the PLC outputs after each scan
        (both are used by the interlock tests)."""
        plc = self.plc
        plc.reset()
        bench = Bench(unit=unit, bench=self.cfg["bench"], rng=rng)
        hmi = {"CMDSTART": 0, "CMDABORT": 0, "CMDRESET": 0, "OPCHECKSOK": 1,
               "ESTOPOK": 1, "GATECLOSED": 1, "DRIVEREADY": 1, "LOADREADY": 1, "BENCHFAULT": 0}
        plc.set(CYCLETIME=self.dt, **recipe)
        cmd = {k: 0 for k in COMMANDS}
        cmd["QLOADPF"] = 1.0
        trace = {k: [] for k in ("t", "step", "speed", "u", "iexc", "p_kw", "hv_kv", "freq")}
        events: list = []
        t = 0.0
        next_trace = 0.0
        scans = 0
        last_step = -1
        started = False
        hv_tripped = False
        wall0 = time.perf_counter()
        while t < max_sim_s:
            hmi["CMDSTART"] = 1 if scans < 3 else 0
            if hooks:
                hooks(t, bench, hmi)
            meas = bench.measure()
            plc.set(**hmi, **meas)
            plc.scan()
            out = plc.out
            for k in COMMANDS:
                cmd[k] = getattr(out, k)
            step = out.STEPNO
            if step != last_step:
                events.append((round(t, 3), int(step), self.step_names.get(int(step), str(step))))
                last_step = step
            if observer:
                observer(t, bench, out)
            if out.BUSY:
                started = True
            if started and out.DONE and stop_on_done:
                break
            bench.step(cmd, self.dt)
            hv_tripped = hv_tripped or bench.hv_trip
            if trace_every_s and t >= next_trace:
                trace["t"].append(t)
                trace["step"].append(int(step))
                trace["speed"].append(bench.speed)
                trace["u"].append(bench.v)
                trace["iexc"].append(bench.iexc)
                trace["p_kw"].append(bench.p_kw)
                trace["hv_kv"].append(bench.hv_kv)
                trace["freq"].append(bench.speed * unit.poles / 120.0)
                next_trace += trace_every_s
            t += self.dt
            scans += 1
        return RunResult(
            serial=unit.serial, frame=unit.frame, fault=unit.fault, type_test=type_test,
            outputs=plc.outputs(), recipe=dict(recipe), sim_time_s=t,
            wall_time_s=time.perf_counter() - wall0, scans=scans, trace=trace, events=events,
            context={"_phase_seq_ok": unit.phase_order_ok, "_ct_pol_ok": unit.ct_polarity_ok,
                     "_hv_tripped": hv_tripped},
        )
