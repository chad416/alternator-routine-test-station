"""Run one unit and print the step log and results (development helper)."""

import sys

import numpy as np

from station.plant import make_unit
from station.recipe import Order, build_recipe, load_frames
from station.runner import Station

frame = sys.argv[1] if len(sys.argv) > 1 else "small"
fault = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
tt = len(sys.argv) > 3 and sys.argv[3] == "tt"
cfg = load_frames()
rng = np.random.default_rng(1)
order = Order("DEV-1", frame, tt)
unit = make_unit(frame, cfg["frames"][frame], order.serial, rng, fault)
st = Station(cfg)
res = st.run(unit, build_recipe(order, cfg), tt, rng)
for e in res.events:
    print(e)
o = res.outputs
ids = st.plc.check_ids()
print("verdict", o["VERDICTPASS"], "aborted", o["ABORTED"], "code", o["ABORTCODE"], "at", o["ABORTSTEP"],
      "firstFail", o["FIRSTFAIL"])
for name, bit in sorted(ids.items(), key=lambda kv: kv[1]):
    exp = (o["CHKEXPECTED"] >> bit) & 1
    dn = (o["CHKDONE"] >> bit) & 1
    ok = (o["CHKPASS"] >> bit) & 1
    print(f"{bit:2d} {name:12s} exp={exp} done={dn} pass={ok}")
print({k: round(v, 4) for k, v in o.items() if k.startswith("RS")})
print(f"sim {res.sim_time_s:.0f} s, wall {res.wall_time_s:.2f} s, scans {res.scans}")
