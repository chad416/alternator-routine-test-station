"""Test records: SQLite store, non-conformity routing and the per-unit
routine test report (PDF + JSON)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from .checks import BY_NAME, CHECKS  # noqa: E402

# Ordered rules: (checks that must all have failed, likely cause, where the unit goes)
DIAGNOSIS = [
    ({"IR_BEFORE"}, "Insulation resistance low: dry the winding and retest; rewind if it stays low", "DRYING"),
    ({"IR_AFTER"}, "Insulation degraded by the HV test: inspect the winding", "REPAIR"),
    ({"HV"}, "Dielectric breakdown: locate the flaw, rewind", "REPAIR"),
    ({"IF_NOLOAD", "IF_LOAD"}, "Excitation needs too much field current: check rotating diodes and exciter", "REPAIR"),
    ({"BUILDUP", "REMANENT"}, "Residual magnetism too low: re-magnetise the rotor (field flash) and retest", "RETEST"),
    ({"AVR_SUPPLY"}, "AVR supply voltage wrong: check the supply winding tap and wiring", "REPAIR"),
    ({"SAT"}, "Saturation curve out of range: check lamination grade and core stack", "ENGINEERING"),
    ({"UNBAL"}, "Phase voltages unbalanced: look for a shorted turn or a wrong coil connection", "REPAIR"),
    ({"PHASE_SEQ"}, "Wrong phase sequence: correct the output lead marking", "REWORK"),
    ({"R_STATOR"}, "Stator resistance out of tolerance: check joints and coil connections", "REPAIR"),
    ({"R_ROTOR"}, "Main rotor resistance out of tolerance: check turns and joints", "REPAIR"),
    ({"R_EXC_ST"}, "Exciter stator resistance out of tolerance: check coil and wire size", "REPAIR"),
    ({"R_EXC_ROT"}, "Exciter rotor resistance out of tolerance: check crimps and leads", "REPAIR"),
    ({"AVR_U"}, "AVR voltage setting or sensing wrong: re-set the AVR and retest", "RETEST"),
    ({"REG_PF08"}, "Voltage drops with reactive load: check the AVR droop setting", "RETEST"),
    ({"REG_PF10"}, "Voltage regulation out of tolerance at PF 1.0: check AVR settings", "RETEST"),
    ({"CT"}, "CT orientation or ratio wrong: refit the CT (P1 towards the machine)", "REWORK"),
    ({"U_STAR"}, "Wrong voltage after star reconnection: check the star links", "REWORK"),
    ({"IF_NOLOAD"}, "No-load field current out of tolerance: check exciter and air gap, retest", "RETEST"),
    ({"IF_LOAD"}, "On-load field current out of tolerance: check air gap and winding data, retest", "RETEST"),
    ({"BUILDUP"}, "Slow voltage build-up: check remanence and AVR supply, retest", "RETEST"),
    ({"REMANENT"}, "Remanent voltage low: re-magnetise the rotor and retest", "RETEST"),
    ({"OVERLOAD"}, "Voltage collapsed under overload: check excitation ceiling", "ENGINEERING"),
    ({"OVERSPEED"}, "Overspeed not held: check the bench drive and the rotor", "ENGINEERING"),
    ({"PT100"}, "PT100 open or out of range: check the sensor wiring", "REWORK"),
    ({"PTC"}, "PTC out of range: check the thermistor wiring", "REWORK"),
    ({"HEATER"}, "Space heater out of range: check the element and its wiring", "REWORK"),
]


def failed_checks(rec: dict) -> list[str]:
    return [k for k, c in rec["checks"].items() if c["done"] and not c["pass"]]


def missing_checks(rec: dict) -> list[str]:
    return [k for k, c in rec["checks"].items() if c["expected"] and not c["done"]]


def diagnose(rec: dict) -> tuple[str, str]:
    failed = set(failed_checks(rec))
    if rec.get("aborted"):
        return "Test aborted: see abort code", "RETEST"
    for need, cause, route in DIAGNOSIS:
        if need <= failed:
            return cause, route
    if missing_checks(rec):
        return "Test incomplete", "RETEST"
    return "", ""


SCHEMA = """
CREATE TABLE IF NOT EXISTS units (
  serial TEXT PRIMARY KEY, frame TEXT, type_test INTEGER, verdict INTEGER,
  aborted INTEGER, first_fail TEXT, test_time_s REAL, bench_limited INTEGER);
CREATE TABLE IF NOT EXISTS results (
  serial TEXT, check_name TEXT, value REAL, lo REAL, hi REAL, pass INTEGER,
  PRIMARY KEY (serial, check_name));
CREATE TABLE IF NOT EXISTS nonconformities (
  id INTEGER PRIMARY KEY AUTOINCREMENT, serial TEXT, failed TEXT, cause TEXT, route TEXT);
"""


class Store:
    """SQLite stand-in for the plant's MES / test database."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def add(self, rec: dict) -> int | None:
        """Store one unit; returns the non-conformity id if it failed."""
        cur = self.db.cursor()
        cur.execute("DELETE FROM results WHERE serial = ?", (rec["serial"],))
        cur.execute(
            "INSERT OR REPLACE INTO units VALUES (?,?,?,?,?,?,?,?)",
            (rec["serial"], rec["frame"], int(rec["type_test"]), int(rec["verdict"]), int(rec["aborted"]),
             rec["first_fail"], rec["test_time_s"], int(rec["bench_limited"])),
        )
        for name, c in rec["checks"].items():
            if c["done"]:
                cur.execute("INSERT INTO results VALUES (?,?,?,?,?,?)",
                            (rec["serial"], name, c["value"], c["lo"], c["hi"], int(c["pass"])))
        nc_id = None
        if not rec["verdict"]:
            cause, route = diagnose(rec)
            cur.execute("INSERT INTO nonconformities (serial, failed, cause, route) VALUES (?,?,?,?)",
                        (rec["serial"], ",".join(failed_checks(rec) + [f"missing:{m}" for m in missing_checks(rec)]),
                         cause, route))
            nc_id = cur.lastrowid
        self.db.commit()
        return nc_id

    def close(self) -> None:
        self.db.close()


def _fmt(v):
    if v is None:
        return ""
    a = abs(v)
    if a == 0:
        return "0"
    if a >= 1000:
        return f"{v:.0f}"
    if a >= 10:
        return f"{v:.2f}"
    if a >= 0.1:
        return f"{v:.3f}"
    return f"{v:.5f}"


def write_report(rec: dict, out_dir: Path, trace: dict | None = None) -> tuple[Path, Path]:
    """One-page routine test report (PDF) plus the same data as JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / f"{rec['serial']}.json"
    jrec = {k: v for k, v in rec.items() if k != "events"}
    cause, route = diagnose(rec) if not rec["verdict"] else ("", "")
    jrec["nonconformity"] = {"cause": cause, "route": route} if cause else None
    jpath.write_text(json.dumps(jrec, indent=1), encoding="utf-8")

    ppath = out_dir / f"{rec['serial']}.pdf"
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.07, 0.955, "Routine test report", fontsize=17, weight="bold")
    fig.text(0.07, 0.932, "Low-voltage alternator, production test bench (simulation)", fontsize=9, color="0.35")
    rc = rec["recipe"]
    head = [
        ("Serial", rec["serial"]), ("Frame", rec["frame"]),
        ("Test connection", f"{rc['RCUN']:.0f} V {'delta' if rc['RCTESTDELTA'] else 'star'}, {rc['RCFN']:.0f} Hz"),
        ("Test load", f"{rc['RCPTESTKW']:.0f} kW" + (" (bench limit, rated load extrapolated)" if rec["bench_limited"] else "")),
        ("Test type", "type test" if rec["type_test"] else "routine test"),
        ("Duration on bench", f"{rec['test_time_s'] / 60:.1f} min"),
    ]
    for i, (k, v) in enumerate(head):
        fig.text(0.07, 0.90 - i * 0.018, k, fontsize=9, color="0.35")
        fig.text(0.27, 0.90 - i * 0.018, v, fontsize=9)
    ok = rec["verdict"]
    fig.text(0.70, 0.885, "PASS" if ok else "FAIL", fontsize=30, weight="bold",
             color="#1a7f37" if ok else "#c62828")

    rows = []
    for c in CHECKS:
        r = rec["checks"][c.name]
        if not r["expected"]:
            continue
        if not r["done"]:
            res = "not run"
        else:
            res = "OK" if r["pass"] else "FAIL"
        val = "" if r["value"] is None or not r["done"] else _fmt(r["value"])
        if c.name == "PHASE_SEQ" and r["done"]:
            val = "correct" if r["pass"] else "wrong"
        lim = ""
        if r["lo"] is not None and r["hi"] is not None:
            lim = f"{_fmt(r['lo'])} .. {_fmt(r['hi'])}"
        elif r["lo"] is not None:
            lim = f">= {_fmt(r['lo'])}"
        elif r["hi"] is not None:
            lim = f"<= {_fmt(r['hi'])}"
        rows.append([c.title, val, c.unit, lim, res])
    ax = fig.add_axes([0.05, 0.30 if trace else 0.10, 0.90, 0.48 if trace else 0.68])
    ax.axis("off")
    tbl = ax.table(cellText=rows, colLabels=["Check", "Value", "Unit", "Limits", "Result"],
                   colWidths=[0.47, 0.13, 0.07, 0.21, 0.10], loc="upper center", cellLoc="left")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7.5)
    tbl.scale(1, 1.25)
    for (r_i, c_i), cell in tbl.get_celld().items():
        cell.set_edgecolor("0.85")
        if r_i == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("0.94")
        elif c_i == 4 and cell.get_text().get_text() != "OK":
            cell.set_text_props(color="#c62828", weight="bold")

    if trace and trace.get("t"):
        t = [x / 60 for x in trace["t"]]
        a1 = fig.add_axes([0.10, 0.08, 0.80, 0.18])
        a1.plot(t, trace["speed"], color="0.4", lw=1, label="speed [rpm]")
        a1.plot(t, trace["u"], color="#1f6feb", lw=1, label="voltage [V]")
        a1.set_xlabel("time on bench [min]", fontsize=8)
        a1.tick_params(labelsize=7)
        a2 = a1.twinx()
        a2.plot(t, trace["iexc"], color="#d97706", lw=1, label="exciter current [A]")
        a2.tick_params(labelsize=7)
        lines = a1.get_lines() + a2.get_lines()
        a1.legend(lines, [ln.get_label() for ln in lines], fontsize=7, loc="upper right")
        a1.grid(alpha=0.3)

    if not ok:
        fig.text(0.07, 0.035, f"Non-conformity: {cause}  ->  {route}", fontsize=8.5, color="#c62828")
    fig.text(0.07, 0.018, "Simulated unit and bench. Generic limits, not a manufacturer's values.",
             fontsize=7, color="0.5")
    with PdfPages(ppath) as pdf:
        pdf.savefig(fig)
    plt.close(fig)
    return ppath, jpath


def title_of(check: str) -> str:
    return BY_NAME[check].title
