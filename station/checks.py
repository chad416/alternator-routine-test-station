"""Independent re-evaluation of the PLC's pass/fail decisions.

The PLC decides pass/fail itself. This module recomputes every decision in
Python from the latched results and the recipe, so the two can be compared
unit by unit (tests/test_crosscheck.py). It also gives the report its
limits and units.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

CU_K = 235.0


@dataclass(frozen=True)
class Check:
    name: str
    title: str
    result: str              # PLC output holding the latched value
    unit: str
    limits: Callable[[dict], tuple[float | None, float | None]]
    passes: Callable[[float, dict, dict], bool]


def _band(nom_key: str, tol_key: str):
    def lim(rc):
        n, t = rc[nom_key], rc[tol_key]
        return n * (1 - t / 100.0), n * (1 + t / 100.0)
    return lim


def _in(lo_hi):
    def f(v, rc, o):
        lo, hi = lo_hi(rc)
        return (lo is None or v >= lo) and (hi is None or v <= hi)
    return f


def _abs_le(tol_key: str):
    return lambda v, rc, o: abs(v) <= rc[tol_key]


CHECKS: list[Check] = [
    Check("R_STATOR", "Stator winding resistance at 20 degC", "RSRSTATOR", "ohm",
          _band("RCRSTATOR", "RCRTOLPCT"), _in(_band("RCRSTATOR", "RCRTOLPCT"))),
    Check("R_ROTOR", "Main rotor resistance at 20 degC", "RSRROTOR", "ohm",
          _band("RCRROTOR", "RCRTOLPCT"), _in(_band("RCRROTOR", "RCRTOLPCT"))),
    Check("R_EXC_ST", "Exciter stator resistance at 20 degC", "RSREXCST", "ohm",
          _band("RCREXCST", "RCRTOLPCT"), _in(_band("RCREXCST", "RCRTOLPCT"))),
    Check("R_EXC_ROT", "Exciter rotor resistance at 20 degC", "RSREXCROT", "ohm",
          _band("RCREXCROT", "RCRTOLPCT"), _in(_band("RCREXCROT", "RCRTOLPCT"))),
    Check("IR_BEFORE", "Insulation resistance before HV", "RSIRBEFORE", "Mohm",
          lambda rc: (rc["RCIRMIN"], None), lambda v, rc, o: v >= rc["RCIRMIN"]),
    Check("HV", "Dielectric withstand, peak leakage", "RSHVLEAK", "mA",
          lambda rc: (None, rc["RCHVLEAKMAX"]),
          lambda v, rc, o: v <= rc["RCHVLEAKMAX"] and not o.get("_hv_tripped", False)),
    Check("IR_AFTER", "Insulation resistance after HV (type test)", "RSIRAFTER", "Mohm",
          lambda rc: (rc["RCIRMIN"], None), lambda v, rc, o: v >= rc["RCIRMIN"]),
    Check("PHASE_SEQ", "Phase sequence", "", "", lambda rc: (None, None),
          lambda v, rc, o: bool(o.get("_phase_seq_ok", True))),
    Check("UNBAL", "Voltage unbalance, no load", "RSUNBAL", "%",
          lambda rc: (None, rc["RCUNBALMAX"]), lambda v, rc, o: v <= rc["RCUNBALMAX"]),
    Check("IF_NOLOAD", "Exciter field current, no load at Un", "RSIF0", "A",
          _band("RCIF0NOM", "RCIF0TOLPCT"), _in(_band("RCIF0NOM", "RCIF0TOLPCT"))),
    Check("AVR_SUPPLY", "AVR supply voltage at no load", "RSAVRSUP", "V",
          lambda rc: (rc["RCAVRSUPMIN"], rc["RCAVRSUPMAX"]),
          _in(lambda rc: (rc["RCAVRSUPMIN"], rc["RCAVRSUPMAX"]))),
    Check("IF_LOAD", "Exciter field current on load at Un", "RSIFLOAD", "A",
          _band("RCIFLNOM", "RCIFLTOLPCT"), _in(_band("RCIFLNOM", "RCIFLTOLPCT"))),
    Check("SAT", "Load cut-off voltage / Un", "RSSAT", "-",
          lambda rc: (rc["RCSATMIN"], rc["RCSATMAX"]), _in(lambda rc: (rc["RCSATMIN"], rc["RCSATMAX"]))),
    Check("BUILDUP", "Voltage build-up frequency with AVR", "RSBUILDHZ", "Hz",
          lambda rc: (None, rc["RCBUILDMAXHZ"]),
          lambda v, rc, o: v <= rc["RCBUILDMAXHZ"]),
    Check("AVR_U", "No-load voltage with AVR, deviation", "RSAVRU", "%",
          lambda rc: (-rc["RCAVRUTOLPCT"], rc["RCAVRUTOLPCT"]), _abs_le("RCAVRUTOLPCT")),
    Check("REG_PF08", "Voltage regulation at PF 0.8", "RSREGPF08", "%",
          lambda rc: (-rc["RCREGTOLPCT"], rc["RCREGTOLPCT"]), _abs_le("RCREGTOLPCT")),
    Check("REG_PF10", "Voltage regulation at PF 1.0", "RSREGPF10", "%",
          lambda rc: (-rc["RCREGTOLPCT"], rc["RCREGTOLPCT"]), _abs_le("RCREGTOLPCT")),
    Check("CT", "CT secondary current and polarity", "RSCTSEC", "A",
          lambda rc: (rc["RCCTSECMIN"], rc["RCCTSECMAX"]),
          lambda v, rc, o: o.get("_ct_pol_ok", True) and rc["RCCTSECMIN"] <= v <= rc["RCCTSECMAX"]),
    Check("U_STAR", "Star voltage after reconnection, deviation", "RSUSTAR", "%",
          lambda rc: (-rc["RCAVRUTOLPCT"], rc["RCAVRUTOLPCT"]), _abs_le("RCAVRUTOLPCT")),
    Check("REMANENT", "Remanent voltage / Un", "RSREM", "%",
          lambda rc: (rc["RCREMMINPCT"], None), lambda v, rc, o: v >= rc["RCREMMINPCT"]),
    Check("OVERLOAD", "Overload 150 %, lowest voltage (type test)", "RSOVERLOAD", "%",
          lambda rc: (90.0, None), lambda v, rc, o: v >= 90.0),
    Check("OVERSPEED", "Overspeed 120 %, highest speed (type test)", "RSOVERSPEED", "%",
          lambda rc: (118.0, 122.0), lambda v, rc, o: 118.0 <= v <= 122.0),
    Check("PT100", "PT100 resistance", "RSPT100", "ohm",
          lambda rc: (rc["RCPT100MIN"], rc["RCPT100MAX"]), _in(lambda rc: (rc["RCPT100MIN"], rc["RCPT100MAX"]))),
    Check("PTC", "PTC resistance", "RSPTC", "ohm",
          lambda rc: (rc["RCPTCMIN"], rc["RCPTCMAX"]), _in(lambda rc: (rc["RCPTCMIN"], rc["RCPTCMAX"]))),
    Check("HEATER", "Space heater resistance", "RSHEATER", "ohm",
          _band("RCHEATERR", "RCHEATERTOLPCT"), _in(_band("RCHEATERR", "RCHEATERTOLPCT"))),
]

BY_NAME = {c.name: c for c in CHECKS}


def decode(outputs: dict, ids: dict[str, int]) -> dict[str, dict]:
    """Per check: expected / done / pass bits as the PLC reported them."""
    res = {}
    for name, bit in ids.items():
        res[name] = {
            "expected": bool((outputs["CHKEXPECTED"] >> bit) & 1),
            "done": bool((outputs["CHKDONE"] >> bit) & 1),
            "pass": bool((outputs["CHKPASS"] >> bit) & 1),
        }
    return res


def reevaluate(outputs: dict, recipe: dict, context: dict) -> dict[str, bool]:
    """Python decision for every check the PLC marked as done. `context`
    carries the bench's boolean signals that are not latched as numbers
    (phase-sequence relay, CT polarity, HV trip)."""
    o = {**outputs, **context}
    out = {}
    for c in CHECKS:
        v = outputs.get(c.result, 0.0) if c.result else 0.0
        out[c.name] = bool(c.passes(v, recipe, o))
    return out
