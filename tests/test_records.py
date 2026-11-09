"""Records, reports, PLC-vs-Python cross-check and the capacity arithmetic."""

import json

import pytest

from station.analysis import benches_needed, cpk
from station.batch import _init, run_one, sweep_plan
from station.records import Store, diagnose, write_report


@pytest.fixture(scope="module")
def sweep_records(cfg):
    _init(cfg)
    plan = sweep_plan(cfg, reps=1, seed=3)
    return [run_one(it, cfg) for it in plan]


def test_plc_and_python_agree_on_every_check(sweep_records):
    disagree = [(r["serial"], k) for r in sweep_records for k, c in r["checks"].items()
                if c["done"] and c["py_pass"] != c["pass"]]
    assert disagree == []


def test_diagnosis_routes(sweep_records):
    by_fault = {r["fault"]: r for r in sweep_records if r["frame"] == "medium"}
    cause, route = diagnose(by_fault["DIODE_OPEN"])
    assert "diodes" in cause and route == "REPAIR"
    assert diagnose(by_fault["IR_LOW"])[1] == "DRYING"
    assert diagnose(by_fault["WEAK_REMANENCE"])[1] == "RETEST"


def test_store_and_report(sweep_records, tmp_path):
    rec = next(r for r in sweep_records if r["fault"] == "SHORTED_TURN")
    store = Store(tmp_path / "t.db")
    nc = store.add(rec)
    assert nc is not None
    row = store.db.execute("SELECT failed, route FROM nonconformities WHERE id = ?", (nc,)).fetchone()
    assert "UNBAL" in row[0] and row[1] == "REPAIR"
    n = store.db.execute("SELECT COUNT(*) FROM results WHERE serial = ?", (rec["serial"],)).fetchone()[0]
    assert n == sum(c["done"] for c in rec["checks"].values())
    store.add(rec)   # re-test of the same serial replaces its results
    n2 = store.db.execute("SELECT COUNT(*) FROM results WHERE serial = ?", (rec["serial"],)).fetchone()[0]
    assert n2 == n
    store.close()
    pdf, js = write_report(rec, tmp_path)
    assert pdf.read_bytes()[:4] == b"%PDF"
    data = json.loads(js.read_text())
    assert data["verdict"] is False and data["nonconformity"]["route"] == "REPAIR"


def test_cpk_hand_example():
    vals = [9.0, 10.0, 11.0] * 5
    sd = (sum((v - 10.0) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
    assert cpk(vals, 7.0, 14.0) == pytest.approx((10.0 - 7.0) / (3 * sd))


def test_benches_needed_hand_example():
    tt = {"frames": {"a": {"routine_s": 600.0, "handling_s": 1200.0}}, "changeover_s": 0.0}
    cap = {"demand_per_day": {"a": 10}, "retest_rate": 0.0, "changeovers_per_day": 0,
           "shifts_per_day": 3, "hours_per_shift": 7.5, "bench_availability": 0.8}
    r = benches_needed(tt, cap, 2.0)
    # 20 units x 30 min = 10 h, against 18 productive hours per bench
    assert r["bench_hours_per_day"] == pytest.approx(10.0)
    assert r["utilisation_one_bench"] == pytest.approx(10.0 / 18.0, abs=0.01)
    assert r["benches"] == 1
    assert benches_needed(tt, cap, 4.0)["benches"] == 2
