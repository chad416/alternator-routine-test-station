"""Simulated alternator on a production test bench.

Steady-state machine model with first-order dynamics where they matter for
the test sequence (field current, speed ramp, load bank, HV source). Units:
volts, amps, kW, rpm, ohm, megaohm, kV, mA, degC.

Model summary (per unit values in brackets are relative to rated values):
  * Open-circuit characteristic (OCC): E = (1 + c) x / (c + x), with x the
    main field current relative to the no-load field current, so E(1) = 1.
  * Brushless excitation: main field follows the exciter field current,
    scaled by speed, with time constant td.
  * Load: field current from the ASA method,
        x_load = sqrt((x_v + xar i sin(phi))^2 + (xar i cos(phi))^2),
    x_v = OCC^-1(|V + j xl i|). The terminal voltage for a given field is
    found by bisection.
  * Remanence: the voltage never falls below rem_pct of rated (at speed).
  * Generic AVR: PI on sensed voltage, V/f below 96 % of rated frequency,
    active only when its supply is above `ir_operate_v` (self-excitation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

SQRT3 = math.sqrt(3.0)

FAULTS = {
    # name: (description, check expected to catch it)
    "R_STATOR_JOINT": ("high-resistance joint in the stator winding", "R_STATOR"),
    "R_ROTOR_TURNS": ("main rotor wound with too few turns", "R_ROTOR"),
    "R_EXC_STATOR": ("exciter stator coil with wrong wire size", "R_EXC_ST"),
    "R_EXC_ROTOR": ("exciter rotor lead badly crimped", "R_EXC_ROT"),
    "IR_LOW": ("moisture in the stator winding", "IR_BEFORE"),
    "HV_WEAK": ("insulation flaw that breaks down under test voltage", "HV"),
    "SHORTED_TURN": ("shorted turn in one stator phase", "UNBAL"),
    "PHASE_ORDER": ("output leads connected in the wrong order", "PHASE_SEQ"),
    "DIODE_OPEN": ("one rotating rectifier diode open", "IF_NOLOAD"),
    "CORE_SATURATION": ("wrong lamination grade: core saturates early", "SAT"),
    "WEAK_REMANENCE": ("rotor lost its residual magnetism", "REMANENT"),
    "AVR_SENSING": ("AVR voltage setting or sensing off by about 2 %", "AVR_U"),
    "AVR_DROOP": ("AVR droop set far too high", "REG_PF08"),
    "AUX_WIRING": ("AVR supply winding tapped wrongly", "AVR_SUPPLY"),
    "CT_REVERSED": ("current transformer fitted the wrong way round", "CT"),
    "STAR_LINK": ("star links missing after reconnection", "U_STAR"),
    "PT100_OPEN": ("PT100 lead broken", "PT100"),
    "PTC_SHORT": ("PTC thermistor leads shorted", "PTC"),
    "HEATER_OPEN": ("space heater element open", "HEATER"),
}


def occ(x: float, c: float) -> float:
    x = max(x, 0.0)
    return (1.0 + c) * x / (c + x)


def occ_inv(e: float, c: float) -> float:
    e = min(max(e, 0.0), (1.0 + c) * 0.999)
    return c * e / ((1.0 + c) - e)


def field_for_load(v_pu: float, i_pu: float, pf: float, n_pu: float, c: float, xar: float, xl: float) -> float:
    """Main field (relative to no-load field) needed for terminal voltage v_pu
    at current i_pu and lagging power factor pf, at relative speed n_pu."""
    sin_phi = math.sqrt(max(0.0, 1.0 - pf * pf))
    x_l = xl * n_pu
    # |V + j xl I| with I lagging V by phi
    ep = math.hypot(v_pu + x_l * i_pu * sin_phi, x_l * i_pu * pf)
    x_v = occ_inv(ep / max(n_pu, 1e-6), c)
    return math.hypot(x_v + xar * i_pu * sin_phi, xar * i_pu * pf)


@dataclass
class Unit:
    """One alternator as built: frame values with manufacturing spread and
    at most one injected fault."""

    frame: str
    serial: str
    fault: str | None
    kva: float
    un: float            # test connection line voltage
    un_star: float
    test_delta: bool
    fn: float
    poles: int
    exc_type: int
    ct_fitted: bool
    heater_w: float
    heater_v: float
    r20: dict            # stator, rotor, exc_st, exc_rot at 20 degC
    if0: float           # exciter field current for rated no-load voltage
    occ_c: float
    xar: float
    xl: float
    td: float
    rem_pct: float
    sup_ratio: float
    sup_nom: float
    cap_nf: float
    ir_mohm: float
    hv_breakdown_kv: float
    delta: tuple         # per-phase voltage deviation (relative)
    phase_order_ok: bool
    diode_factor: float
    avr_sense_err: float
    avr_droop: float
    aux_factor: float
    ct_polarity_ok: bool
    star_ok: bool
    pt100_open: bool
    ptc_ohm: float
    heater_ohm: float
    t_amb: float
    ramp_rpm_s: float

    @property
    def n_nom(self) -> float:
        return 120.0 * self.fn / self.poles


def make_unit(frame_name: str, frame: dict, serial: str, rng: np.random.Generator, fault: str | None = None) -> Unit:
    if fault is not None and fault not in FAULTS:
        raise ValueError(f"unknown fault {fault}")

    def spread(nominal: float, rel_sd: float) -> float:
        return float(nominal * (1.0 + rel_sd * rng.standard_normal()))

    r20 = {
        "stator": spread(frame["r_stator"], 0.012),
        "rotor": spread(frame["r_rotor"], 0.012),
        "exc_st": spread(frame["r_exc_st"], 0.012),
        "exc_rot": spread(frame["r_exc_rot"], 0.012),
    }
    delta = tuple(float(d) for d in 0.0008 * rng.standard_normal(3))
    u = Unit(
        frame=frame_name, serial=serial, fault=fault,
        kva=frame["kva"], un=frame["un"], un_star=frame["un_star"], test_delta=frame["test_delta"],
        fn=frame["fn"], poles=frame["poles"], exc_type=frame["exc_type"],
        ct_fitted=frame["ct_fitted"], heater_w=frame["heater_w"], heater_v=frame["heater_v"],
        r20=r20,
        if0=spread(frame["if0"], 0.025),
        occ_c=spread(frame["occ_c"], 0.03),
        xar=spread(frame["xar"], 0.025),
        xl=frame["xl"], td=frame["td"],
        rem_pct=float(np.clip(rng.normal(frame["rem_pct"], 1.0), 6.0, 20.0)),
        sup_ratio=frame["sup_ratio"], sup_nom=frame["sup_nom"],
        cap_nf=spread(frame["cap_nf"], 0.05),
        ir_mohm=float(frame["ir_typ_mohm"] * math.exp(0.5 * rng.standard_normal())),
        hv_breakdown_kv=math.inf,
        delta=delta, phase_order_ok=True, diode_factor=1.0,
        avr_sense_err=float(0.002 * rng.standard_normal()), avr_droop=0.0, aux_factor=spread(1.0, 0.02),
        ct_polarity_ok=True, star_ok=True, pt100_open=False,
        ptc_ohm=float(np.clip(rng.normal(90.0, 15.0), 40.0, 160.0)),
        heater_ohm=spread(frame["heater_v"] ** 2 / frame["heater_w"], 0.02) if frame["heater_w"] > 0 else math.inf,
        t_amb=float(rng.uniform(17.0, 28.0)),
        ramp_rpm_s=frame["ramp_rpm_s"],
    )
    hv_kv = dielectric_test_kv(u.un_star)
    match fault:
        case "R_STATOR_JOINT":
            u.r20["stator"] *= float(rng.uniform(1.08, 1.20))
        case "R_ROTOR_TURNS":
            u.r20["rotor"] *= float(rng.uniform(0.86, 0.93))
        case "R_EXC_STATOR":
            u.r20["exc_st"] *= float(rng.uniform(1.08, 1.18))
        case "R_EXC_ROTOR":
            u.r20["exc_rot"] *= float(rng.uniform(1.10, 1.30))
        case "IR_LOW":
            u.ir_mohm = float(rng.uniform(15.0, 80.0))
        case "HV_WEAK":
            u.hv_breakdown_kv = hv_kv * float(rng.uniform(0.6, 0.95))
        case "SHORTED_TURN":
            d = list(u.delta)
            d[int(rng.integers(3))] -= float(rng.uniform(0.010, 0.025))
            u.delta = tuple(d)
        case "PHASE_ORDER":
            u.phase_order_ok = False
        case "DIODE_OPEN":
            u.diode_factor = float(rng.uniform(0.68, 0.78))
        case "CORE_SATURATION":
            u.occ_c = float(rng.uniform(0.30, 0.38))
        case "WEAK_REMANENCE":
            u.rem_pct = float(rng.uniform(3.0, 7.0))
        case "AVR_SENSING":
            u.avr_sense_err = float(rng.choice([-1, 1]) * rng.uniform(0.018, 0.03))
        case "AVR_DROOP":
            u.avr_droop = float(rng.uniform(0.04, 0.08))
        case "AUX_WIRING":
            u.aux_factor = float(rng.uniform(0.55, 0.75))
        case "CT_REVERSED":
            u.ct_polarity_ok = False
        case "STAR_LINK":
            u.star_ok = False
        case "PT100_OPEN":
            u.pt100_open = True
        case "PTC_SHORT":
            u.ptc_ohm = float(rng.uniform(0.2, 2.0))
        case "HEATER_OPEN":
            u.heater_ohm = math.inf
    return u


def dielectric_test_kv(un_star: float) -> float:
    """Dielectric test voltage for windings rated below 1 kV: 1000 V + 2 Un,
    at least 1500 V (IEC 60034-1)."""
    return max(1.5, (1000.0 + 2.0 * un_star) / 1000.0)


def pt100_ohm(t: float) -> float:
    """IEC 60751 PT100 above 0 degC."""
    return 100.0 * (1.0 + 3.9083e-3 * t - 5.775e-7 * t * t)


@dataclass
class Bench:
    """Test bench + alternator state. `step()` takes the PLC outputs and
    advances the simulation; `measure()` returns what the bench instruments
    read."""

    unit: Unit
    bench: dict
    rng: np.random.Generator
    speed: float = 0.0
    x: float = 0.0                  # main field, relative to no-load field
    iexc: float = 0.0               # exciter field current [A]
    load_kw_set: float = 0.0
    load_frac: float = 0.0          # load bank contactor state, 0..1
    load_pf: float = 1.0
    hv_kv: float = 0.0
    hv_trip: bool = False
    ir_t: float = 0.0               # time the megger has been applied [s]
    avr_int: float = 0.0
    avr_active: bool = False
    delta_conn: bool = False
    v: float = 0.0                  # terminal line voltage (balanced value)
    i_load: float = 0.0
    p_kw: float = 0.0
    cmd: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    def _u_conn(self) -> float:
        """Rated line voltage of the present connection."""
        u = self.unit
        if not u.test_delta:
            return u.un
        if self.delta_conn:
            return u.un
        # star connection: rated voltage only if the star links are right
        return u.un_star if u.star_ok else u.un

    def _i_rated(self) -> float:
        return self.unit.kva * 1000.0 / (SQRT3 * self._u_conn())

    def _terminal_voltage(self, n_pu: float) -> tuple[float, float]:
        """Solve terminal voltage and current for the present field and load."""
        u = self.unit
        u_conn = self._u_conn()
        e_rem = u.rem_pct / 100.0 * n_pu
        e_open = max(occ(self.x, u.occ_c) * n_pu, e_rem)
        p_set = self.load_kw_set * self.load_frac
        if p_set <= 0.0 or n_pu < 0.05:
            return e_open * u_conn, 0.0
        # constant-impedance load bank, rated at the connection voltage
        s_pu_at_rated = p_set / max(self.load_pf, 1e-3) / u.kva
        pf = self.load_pf
        lo, hi = 0.0, e_open
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            i_pu = s_pu_at_rated * mid       # current of a constant impedance
            need = field_for_load(mid, i_pu, pf, n_pu, u.occ_c, u.xar, u.xl)
            if need > self.x:
                hi = mid
            else:
                lo = mid
        v_pu = max(lo, 0.0)
        return v_pu * u_conn, s_pu_at_rated * v_pu * self._i_rated()

    def _avr_supply(self, n_pu: float) -> float:
        u = self.unit
        if u.exc_type == 3:      # permanent-magnet pilot exciter
            return u.sup_nom * n_pu * u.aux_factor
        # shunt tap or auxiliary winding: proportional to the output voltage
        return u.sup_ratio * self.v * u.aux_factor

    # ------------------------------------------------------------------
    def step(self, cmd: dict, dt: float) -> None:
        u = self.unit
        self.cmd = cmd
        n_nom = u.n_nom
        # drive: ramp to set point
        sp = cmd["QSPEEDSP"] if cmd["QDRIVERUN"] else 0.0
        dn = sp - self.speed
        lim = u.ramp_rpm_s * dt
        self.speed += max(-lim, min(lim, dn))
        if self.speed < 0.0:
            self.speed = 0.0
        n_pu = self.speed / n_nom
        f = self.speed * u.poles / 120.0

        # connection (only changes the machine when de-excited is the PLC's job)
        self.delta_conn = bool(cmd["QCONNDELTA"])

        # excitation
        mode = cmd["QEXCMODE"]
        if mode == 1:
            target = cmd["QIEXCSP"]
            self.iexc += (target - self.iexc) * min(1.0, dt / 0.1)
            self.avr_active = False
            self.avr_int = 0.0
        elif mode == 2:
            sup = self._avr_supply(n_pu)
            self.avr_active = sup >= self.bench["ir_operate_v"]
            if self.avr_active:
                usp = cmd["QAVRUSP"]
                f_knee = 0.96 * u.fn
                usp_eff = usp * min(1.0, f / f_knee) if f > 0 else 0.0
                i_rated = self._i_rated()
                i_q = (self.i_load / i_rated) * math.sqrt(max(0.0, 1.0 - self.load_pf ** 2)) if i_rated > 0 else 0.0
                sensed = self.v * (1.0 + u.avr_sense_err) * (1.0 + u.avr_droop * i_q)
                err = (usp_eff - sensed) / max(usp, 1.0)
                kp, ki = 4.0 * u.if0, 6.0 * u.if0
                self.avr_int = min(max(self.avr_int + ki * err * dt, 0.0), 6.0 * u.if0)
                ceiling = 6.0 * u.if0 * min(1.0, sup / 100.0)
                self.iexc = min(max(kp * err + self.avr_int, 0.0), ceiling)
            else:
                self.iexc = 0.0
                self.avr_int = 0.0
        else:
            self.iexc = 0.0
            self.avr_active = False
            self.avr_int = 0.0

        # main field follows the exciter (output proportional to speed)
        x_target = self.iexc / u.if0 * n_pu * u.diode_factor
        self.x += (x_target - self.x) * min(1.0, dt / u.td)

        # load bank: contactor plus a short ramp, capped by the bench
        self.load_kw_set = min(cmd["QLOADKW"], self.bench["max_kw"])
        self.load_pf = min(max(cmd["QLOADPF"], 0.1), 1.0)
        target_frac = 1.0 if cmd["QLOADON"] else 0.0
        self.load_frac += (target_frac - self.load_frac) * min(1.0, dt / 0.5)

        self.v, self.i_load = self._terminal_voltage(n_pu)
        self.p_kw = SQRT3 * self.v * self.i_load * self.load_pf / 1000.0

        # HV source and megger
        if cmd["QHVON"] and not self.hv_trip:
            self.hv_kv += (cmd["QHVKVSP"] - self.hv_kv) * min(1.0, dt / 0.2)
            if self.hv_kv >= u.hv_breakdown_kv or self._hv_leak_ma() > self.bench["hv_trip_ma"]:
                self.hv_trip = True
        else:
            self.hv_kv += (0.0 - self.hv_kv) * min(1.0, dt / 0.3)
            if not cmd["QHVON"]:
                self.hv_trip = False
        if self.hv_trip:
            self.hv_kv = 0.0
        self.ir_t = self.ir_t + dt if cmd["QIRON"] else 0.0

    def _hv_leak_ma(self) -> float:
        u = self.unit
        cap = 2.0 * math.pi * 50.0 * u.cap_nf * 1e-9 * self.hv_kv * 1000.0 * 1000.0
        res = self.hv_kv * 1000.0 / (u.ir_mohm * 1e6) * 1000.0
        return math.hypot(cap, res)

    def measure(self) -> dict:
        u = self.unit
        g = self.rng.standard_normal
        n_pu = self.speed / u.n_nom
        f = self.speed * u.poles / 120.0
        v = self.v
        m = {
            "MSPEED": self.speed + 0.2 * g(),
            "MFREQ": f,
            "MU12": v * (1.0 + u.delta[0]) * (1.0 + 0.0003 * g()),
            "MU23": v * (1.0 + u.delta[1]) * (1.0 + 0.0003 * g()),
            "MU31": v * (1.0 + u.delta[2]) * (1.0 + 0.0003 * g()),
            "MILOAD": self.i_load,
            "MPKW": self.p_kw * (1.0 + 0.002 * g()),
            "MIEXC": self.iexc * (1.0 + 0.002 * g()),
            "MTWIND": u.t_amb,
            "MHVKV": max(self.hv_kv, 0.0),
            "MHVLEAK": self._hv_leak_ma() if self.hv_kv > 0.01 else 0.0,
            "MHVTRIP": int(self.hv_trip),
            "MPHASESEQOK": int(u.phase_order_ok and v > 0.05 * u.un),
            "MAVRSUP": self._avr_supply(n_pu) * (1.0 + 0.003 * g()),
            "MDRIVEFAULT": 0,
        }
        # winding resistance meter (4-wire), reading at winding temperature
        ch = self.cmd.get("QRCH", 0)
        key = {1: "stator", 2: "rotor", 3: "exc_st", 4: "exc_rot"}.get(ch)
        if key:
            r_t = u.r20[key] * (235.0 + u.t_amb) / 255.0
            m["MR"] = r_t * (1.0 + 0.001 * g())
        else:
            m["MR"] = 0.0
        # insulation resistance: polarisation current makes it rise with time
        if self.cmd.get("QIRON"):
            m["MIR"] = u.ir_mohm * (1.0 - 0.5 * math.exp(-self.ir_t / 15.0)) * (1.0 + 0.01 * g())
        else:
            m["MIR"] = 0.0
        # CT on one phase, 1 A secondary at rated current
        if u.ct_fitted:
            i_rated = self._i_rated()
            m["MCTSEC"] = self.i_load / i_rated * (1.0 + 0.004 * g())
            m["MCTPOLOK"] = int(u.ct_polarity_ok or self.i_load < 0.05 * i_rated)
        else:
            m["MCTSEC"] = 0.0
            m["MCTPOLOK"] = 0
        probe = self.cmd.get("QPROBECH", 0)
        m["MPT100"] = (1e6 if u.pt100_open else pt100_ohm(u.t_amb) * (1.0 + 0.0005 * g())) if probe == 1 else 0.0
        m["MPTC"] = u.ptc_ohm * (1.0 + 0.002 * g()) if probe == 2 else 0.0
        if probe == 3:
            m["MHEATER"] = 1e6 if math.isinf(u.heater_ohm) else u.heater_ohm * (1.0 + 0.002 * g())
        else:
            m["MHEATER"] = 0.0
        return m
