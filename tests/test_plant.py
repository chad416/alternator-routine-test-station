"""Plant model and recipe arithmetic (no PLC needed)."""

import math

import numpy as np
import pytest

from station.plant import Bench, field_for_load, make_unit, occ, occ_inv, pt100_ohm, dielectric_test_kv
from station.recipe import Order, bench_limited, build_recipe


def test_occ_is_one_at_no_load_field():
    for c in (0.3, 0.6, 0.9):
        assert occ(1.0, c) == pytest.approx(1.0)


def test_occ_inverse():
    for c in (0.35, 0.6):
        for e in (0.1, 0.8, 1.0, 1.2, 1.3):
            assert occ(occ_inv(e, c), c) == pytest.approx(e, rel=1e-9)


def test_field_for_load_at_no_load_equals_occ_inverse():
    assert field_for_load(1.0, 0.0, 0.8, 1.0, 0.6, 2.2, 0.1) == pytest.approx(1.0)


def test_field_for_load_grows_with_current_and_lagging_pf():
    x08 = field_for_load(1.0, 1.0, 0.8, 1.0, 0.6, 2.2, 0.1)
    x10 = field_for_load(1.0, 1.0, 1.0, 1.0, 0.6, 2.2, 0.1)
    assert x08 > x10 > 1.0
    # saturated voltage at the PF 0.8 field lies in the generic 1.25..1.40 band
    assert 1.25 < occ(x08, 0.6) < 1.40


def test_dielectric_test_voltage_iec_60034_1():
    assert dielectric_test_kv(400.0) == pytest.approx(1.8)
    assert dielectric_test_kv(690.0) == pytest.approx(2.38)
    assert dielectric_test_kv(100.0) == pytest.approx(1.5)   # minimum 1500 V


def test_pt100_iec_60751():
    assert pt100_ohm(0.0) == pytest.approx(100.0)
    assert pt100_ohm(100.0) == pytest.approx(138.5055, abs=1e-3)


def test_bench_open_circuit_voltage_follows_field_and_speed(cfg):
    fr = cfg["frames"]["small"]
    unit = make_unit("small", fr, "U1", np.random.default_rng(0))
    b = Bench(unit=unit, bench=cfg["bench"], rng=np.random.default_rng(0))
    b.speed = unit.n_nom
    b.x = 1.0
    v, i = b._terminal_voltage(1.0)
    assert i == 0.0
    assert v == pytest.approx(unit.un, rel=1e-9)
    v_half, _ = b._terminal_voltage(0.5)
    assert v_half == pytest.approx(0.5 * unit.un, rel=1e-9)


def test_bench_voltage_drops_under_load_at_fixed_field(cfg):
    fr = cfg["frames"]["medium"]
    unit = make_unit("medium", fr, "U2", np.random.default_rng(0))
    b = Bench(unit=unit, bench=cfg["bench"], rng=np.random.default_rng(0))
    b.x = 1.0
    b.load_kw_set, b.load_frac, b.load_pf = 640.0, 1.0, 0.8
    v, i = b._terminal_voltage(1.0)
    assert 0.3 * unit.un < v < unit.un
    # the solved point is consistent: field needed for (v, i) equals the field applied
    i_pu = i / (unit.kva * 1000 / (math.sqrt(3) * unit.un))
    assert field_for_load(v / unit.un, i_pu, 0.8, 1.0, unit.occ_c, unit.xar, unit.xl) == pytest.approx(1.0, rel=1e-6)


def test_recipe_bench_limit_and_type_test(cfg):
    assert bench_limited(Order("x", "large"), cfg)
    rc = build_recipe(Order("x", "large"), cfg)
    assert rc["RCPTESTKW"] == cfg["bench"]["max_kw"]
    assert rc["RCHVKV"] == pytest.approx(2.38)
    with pytest.raises(ValueError):
        build_recipe(Order("x", "large", type_test=True), cfg)
    rc = build_recipe(Order("x", "medium", type_test=True), cfg)
    assert rc["RCTYPETEST"] == 1 and rc["RCHEATERR"] == pytest.approx(230.0 ** 2 / 250.0)
