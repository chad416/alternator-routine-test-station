"""The compiled ST sequence against the simulated bench."""

import pytest

from station.batch import applicable_faults
from station.checks import CHECKS, decode
from station.plant import FAULTS

FRAMES = ["small", "medium", "large"]


def bits(res, station):
    return decode(res.outputs, station.plc.check_ids())


@pytest.mark.parametrize("frame", FRAMES)
def test_good_unit_passes_every_expected_check(run, station, frame):
    res, unit, rc = run(frame)
    o = res.outputs
    assert o["VERDICTPASS"] == 1 and o["ABORTED"] == 0 and o["FIRSTFAIL"] == 0
    assert o["CHKDONE"] == o["CHKEXPECTED"] == o["CHKPASS"]
    b = bits(res, station)
    assert b["CT"]["expected"] == unit.ct_fitted
    assert b["U_STAR"]["expected"] == unit.test_delta
    assert b["HEATER"]["expected"] == (unit.heater_w > 0)
    assert not b["OVERSPEED"]["expected"]
    # every step of a routine test ran, in order, and the run ended in DONE
    names = [e[2] for e in res.events]
    assert names[0] == "PRECHECK" and names[-1] == "DONE"
    assert names.index("HV_HOLD") < names.index("RUNUP_EXT") < names.index("RUNUP_AVR") < names.index("PROBES")


@pytest.mark.parametrize("frame", ["small", "medium"])
def test_type_test_adds_three_checks(run, station, frame):
    res, _, _ = run(frame, type_test=True)
    b = bits(res, station)
    for name in ("IR_AFTER", "OVERLOAD", "OVERSPEED"):
        assert b[name]["expected"] and b[name]["done"] and b[name]["pass"]
    assert res.outputs["VERDICTPASS"] == 1
    assert 118.0 <= res.outputs["RSOVERSPEED"] <= 122.0


CASES = [(f, fault) for f in FRAMES for fault in FAULTS if fault in applicable_faults(
    __import__("station.recipe", fromlist=["load_frames"]).load_frames()["frames"][f])]


@pytest.mark.parametrize("frame,fault", CASES)
def test_each_fault_is_rejected_by_its_check(run, station, frame, fault):
    res, _, _ = run(frame, fault, seed=11)
    target = FAULTS[fault][1]
    b = bits(res, station)
    assert res.outputs["VERDICTPASS"] == 0
    assert res.outputs["ABORTED"] == 0
    assert b[target]["done"] and not b[target]["pass"], f"{fault} not caught by {target}"


def test_insulation_fail_skips_hv_and_running(run, station):
    res, _, _ = run("medium", "IR_LOW")
    names = [e[2] for e in res.events]
    assert "HV_RAMP" not in names and "RUNUP_EXT" not in names
    assert res.outputs["FIRSTFAIL"] == station.plc.check_ids()["IR_BEFORE"]
    assert res.outputs["VERDICTPASS"] == 0


def test_dead_avr_skips_load_points(run, station):
    res, _, _ = run("small", "WEAK_REMANENCE")
    names = [e[2] for e in res.events]
    assert "PF08" not in names and "REMANENT" in names and res.outputs["ABORTED"] == 0


# ---------------------------------------------------------------- interlocks
def test_gate_opened_during_hv_aborts_and_removes_hv_in_the_same_scan(run, station):
    seen = {}

    def hooks(t, bench, hmi):
        if bench.hv_kv > 1.0 and "t_open" not in seen:
            seen["t_open"] = t
            hmi["GATECLOSED"] = 0

    def observer(t, bench, out):
        if "t_open" in seen and "hv_after" not in seen:
            seen["hv_after"] = (out.QHVON, out.QHVKVSP, out.STEPNO)

    res, _, _ = run("medium", hooks=hooks, observer=observer)
    assert seen["hv_after"][0] == 0 and seen["hv_after"][1] == 0.0
    assert res.outputs["ABORTED"] == 1
    assert res.outputs["ABORTCODE"] == station.plc.constants["A_GATE"]


def test_estop_while_running_stops_drive_load_and_excitation(run, station):
    seen = {}

    def hooks(t, bench, hmi):
        if bench.load_frac > 0.5 and "t" not in seen:
            seen["t"] = t
            hmi["ESTOPOK"] = 0

    def observer(t, bench, out):
        if "t" in seen and "out" not in seen:
            seen["out"] = (out.QDRIVERUN, out.QLOADON, out.QEXCMODE, out.QSPEEDSP)

    res, _, _ = run("small", hooks=hooks, observer=observer)
    assert seen["out"] == (0, 0, 0, 0.0)
    assert res.outputs["ABORTCODE"] == station.plc.constants["A_ESTOP"]
    assert res.outputs["VERDICTPASS"] == 0


def test_step_timeout_aborts(run, station):
    def hooks(t, bench, hmi):
        hmi["DRIVEREADY"] = 0          # pre-checks can never complete

    res, _, _ = run("small", hooks=hooks, recipe_override={"RCSTEPTIMEOUT": 20.0})
    assert res.outputs["ABORTCODE"] == station.plc.constants["A_TIMEOUT"]
    assert res.outputs["ABORTSTEP"] == station.plc.constants["S_PRECHECK"]
    assert 19.0 < res.sim_time_s < 22.0


def test_no_start_without_operator_checks(run, station):
    def hooks(t, bench, hmi):
        hmi["OPCHECKSOK"] = 0

    res, _, _ = run("small", hooks=hooks, max_sim_s=5.0)
    assert res.outputs["BUSY"] == 0 and res.outputs["STEPNO"] == 0


@pytest.mark.parametrize("frame", ["small", "large"])
def test_hv_drive_and_load_never_overlap(run, frame):
    bad = []

    def observer(t, bench, out):
        if out.QHVON and (bench.speed >= 1.0 or out.QDRIVERUN):
            bad.append(("hv while turning", t))
        if out.QIRON and out.QDRIVERUN:
            bad.append(("megger while driving", t))
        if out.QLOADON and not out.QDRIVERUN:
            bad.append(("load without drive", t))
        if out.QCONNDELTA != getattr(observer, "conn", out.QCONNDELTA) and bench.v > 0.25 * bench.unit.un:
            bad.append(("reconnected while excited", t))
        observer.conn = out.QCONNDELTA

    run(frame, observer=observer)
    assert bad == []


def test_reset_after_abort_allows_a_new_test(run, station):
    """Abort, reset, and start again inside one PLC instance."""
    state = {"phase": 0}

    def hooks(t, bench, hmi):
        if state["phase"] == 0 and t > 5.0:
            hmi["CMDABORT"] = 1
            state["phase"] = 1
        elif state["phase"] == 1 and t > 6.0:
            hmi["CMDABORT"] = 0
            hmi["CMDRESET"] = 1
            state["phase"] = 2
        elif state["phase"] == 2 and t > 7.0:
            hmi["CMDRESET"] = 0
            hmi["CMDSTART"] = 1
            state["phase"] = 3
        elif state["phase"] == 3 and t > 7.5:
            hmi["CMDSTART"] = 0

    def observer(t, bench, out):
        if out.ABORTED:
            state["was_aborted"] = True

    res, _, _ = run("small", hooks=hooks, observer=observer, stop_on_done=False, max_sim_s=400.0)
    assert state.get("was_aborted")
    assert res.outputs["VERDICTPASS"] == 1 and res.outputs["ABORTED"] == 0


def test_check_names_match_plc_constants(station):
    assert set(station.plc.check_ids()) == {c.name for c in CHECKS}
