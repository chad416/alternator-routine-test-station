# Changelog

## 0.1.0 (2026-11-09)

First version.
- ST function block `ROUTINE_TEST` with 25 checks, interlocks, aborts and step timeouts, compiled with matiec.
- Simulated alternator and test bench with 19 injectable faults and three generic frames (100, 800 and 2500 kVA).
- Recipe per production order, PDF/JSON reports, an SQLite test database and non-conformity routing.
- Batch analysis: fault detection matrix, SPC/Cpk, Pareto, test time, test-bench capacity, and `test_times.json` for the ramp-up model.
- TIA Portal SCL source generated from the ST source (not yet compiled in TIA).
- 84 tests, CI with a pinned matiec build.
