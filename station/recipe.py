"""Production order -> PLC recipe values.

A production order names a frame and its options. The recipe holds the
expected values and limits the PLC compares against, the way a works order
carries them to the test bench.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .plant import field_for_load, dielectric_test_kv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRAMES = ROOT / "config" / "frames.json"


@dataclass
class Order:
    serial: str
    frame: str
    type_test: bool = False


def load_frames(path: Path = DEFAULT_FRAMES) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_recipe(order: Order, cfg: dict) -> dict:
    """Return PLC recipe inputs (upper-case names, as in the ST source)."""
    fr = cfg["frames"][order.frame]
    lim = fr["limits"]
    bench = cfg["bench"]
    p_rated = 0.8 * fr["kva"]
    p_test = min(p_rated, bench["max_kw"])
    if order.type_test and 1.5 * p_test > bench["max_kw"]:
        raise ValueError(
            f"{order.serial}: type test needs {1.5 * p_test:.0f} kW, bench has {bench['max_kw']:.0f} kW"
        )
    i_pu = p_test / 0.8 / fr["kva"]
    x_load = field_for_load(1.0, i_pu, 0.8, 1.0, fr["occ_c"], fr["xar"], fr["xl"])
    if fr["exc_type"] == 3:
        sup = fr["sup_nom"]
    else:
        sup = fr["sup_ratio"] * fr["un"]
    heater_r = fr["heater_v"] ** 2 / fr["heater_w"] if fr["heater_w"] > 0 else 0.0
    return {
        "RCUN": fr["un"],
        "RCFN": fr["fn"],
        "RCPOLES": fr["poles"],
        "RCPTESTKW": p_test,
        "RCEXCTYPE": fr["exc_type"],
        "RCTYPETEST": int(order.type_test),
        "RCCTFITTED": int(fr["ct_fitted"]),
        "RCTESTDELTA": int(fr["test_delta"]),
        "RCUNSTAR": fr["un_star"],
        "RCHEATERFITTED": int(fr["heater_w"] > 0),
        "RCHEATERR": heater_r,
        "RCHEATERTOLPCT": lim["heater_tol_pct"],
        "RCRSTATOR": fr["r_stator"],
        "RCRROTOR": fr["r_rotor"],
        "RCREXCST": fr["r_exc_st"],
        "RCREXCROT": fr["r_exc_rot"],
        "RCRTOLPCT": lim["r_tol_pct"],
        "RCIRKV": lim["ir_kv"],
        "RCIRTIME": lim["ir_time_s"],
        "RCIRMIN": lim["ir_min_mohm"],
        "RCHVKV": dielectric_test_kv(fr["un_star"]),
        "RCHVTIME": lim["hv_time_s"],
        "RCHVLEAKMAX": lim["hv_leak_max_ma"],
        "RCIF0NOM": fr["if0"],
        "RCIF0TOLPCT": lim["if0_tol_pct"],
        "RCIFLNOM": fr["if0"] * x_load,
        "RCIFLTOLPCT": lim["ifl_tol_pct"],
        "RCUNBALMAX": lim["unbal_max_pct"],
        "RCAVRSUPMIN": sup * (1.0 - lim["avr_sup_tol_pct"] / 100.0),
        "RCAVRSUPMAX": sup * (1.0 + lim["avr_sup_tol_pct"] / 100.0),
        "RCSATMIN": lim["sat_min"],
        "RCSATMAX": lim["sat_max"],
        "RCBUILDLVLPCT": lim["build_lvl_pct"],
        "RCBUILDMAXHZ": lim["build_max_hz"],
        "RCAVRUTOLPCT": lim["avr_u_tol_pct"],
        "RCREGTOLPCT": lim["reg_tol_pct"],
        "RCCTSECMIN": lim["ct_sec_min"] * i_pu,
        "RCCTSECMAX": lim["ct_sec_max"] * i_pu,
        "RCREMMINPCT": lim["rem_min_pct"],
        "RCPT100MIN": lim["pt100_min"],
        "RCPT100MAX": lim["pt100_max"],
        "RCPTCMIN": lim["ptc_min"],
        "RCPTCMAX": lim["ptc_max"],
        "RCSETTLE": fr["settle_s"],
        "RCOVERSPEEDTIME": lim["overspeed_s"],
        "RCOVERLOADTIME": lim["overload_s"],
        "RCSTEPTIMEOUT": lim["step_timeout_s"],
    }


def bench_limited(order: Order, cfg: dict) -> bool:
    fr = cfg["frames"][order.frame]
    return 0.8 * fr["kva"] > cfg["bench"]["max_kw"]
