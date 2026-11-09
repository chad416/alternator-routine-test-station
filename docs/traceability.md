# Traceability: requirement → test or evidence

| ID | Covered by |
|---|---|
| F01 | `scripts/build_plc.sh` (iec2c + gcc in CI) · every test in `tests/test_sequence.py` runs the compiled block |
| F02 | `tests/test_plant.py::test_recipe_bench_limit_and_type_test` · `test_good_unit_passes_every_expected_check` (expected bits follow the options) |
| F03 | `test_each_fault_is_rejected_by_its_check[*-R_*]` · plant meter reads at winding temperature, PLC corrects (`station/plant.py`, `RES` step) |
| F04 | `test_each_fault_is_rejected_by_its_check[*-IR_LOW]` · `test_insulation_fail_skips_hv_and_running` |
| F05 | `test_dielectric_test_voltage_iec_60034_1` · `test_each_fault_is_rejected_by_its_check[*-HV_WEAK]` |
| F06 | faults DIODE_OPEN, PHASE_ORDER, SHORTED_TURN, AUX_WIRING in `test_each_fault_is_rejected_by_its_check` |
| F07 | `test_field_for_load_grows_with_current_and_lagging_pf` · fault CORE_SATURATION |
| F08 | fault WEAK_REMANENCE on small/medium (BUILDUP fails); detection matrix `docs/img/detection.png` |
| F09 | faults AVR_SENSING, AVR_DROOP, CT_REVERSED |
| F10 | fault STAR_LINK · `test_hv_drive_and_load_never_overlap[large]` (no reconnection while excited) |
| F11 | fault WEAK_REMANENCE (all frames) |
| F12 | `test_type_test_adds_three_checks` |
| F13 | faults PT100_OPEN, PTC_SHORT, HEATER_OPEN |
| F14 | `test_good_unit_passes_every_expected_check` (CHKDONE = CHKEXPECTED = CHKPASS) · every fault test (verdict FAIL) |
| F15 | `test_recipe_bench_limit_and_type_test` · report header (`docs/examples`) |
| F16 | `test_dead_avr_skips_load_points` |
| F17 | `tests/test_records.py::test_store_and_report` · `test_diagnosis_routes` · `docs/examples/*.pdf` |
| F18 | `tests/test_scl.py::test_scl_is_up_to_date` · `test_scl_dialect` |
| F19 | `test_cpk_hand_example` · `test_benches_needed_hand_example` · `results/summary.json` · CI step "Fault detection and cross-check must hold" |
| F20 | `results/test_times.json`, read by generator-plant-rampup-sim (`rampup/config.py::load_test_times`) |
| S01 | `test_gate_opened_during_hv_aborts_and_removes_hv_in_the_same_scan` · `test_hv_drive_and_load_never_overlap` |
| S02 | `test_hv_drive_and_load_never_overlap` |
| S03 | `test_hv_drive_and_load_never_overlap` |
| S04 | `test_estop_while_running_stops_drive_load_and_excitation` |
| S05 | `test_step_timeout_aborts` |
| S06 | `test_no_start_without_operator_checks` · `test_reset_after_abort_allows_a_new_test` |
| P01 | `test_each_fault_is_rejected_by_its_check` (57 cases) · sweep 530/530 in `results/summary.json` · CI assertion |
| P02 | production batch: escapes = 0 (`results/summary.json`) · CI assertion |
| P03 | `test_plc_and_python_agree_on_every_check` · 0 disagreements in batch and sweep · CI assertion |
| P04 | batch timing in the README (0.3 s per unit) |
| P05 | `results/summary.json` → `production.false_rejects` |
