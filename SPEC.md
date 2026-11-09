# SPEC: alternator routine-test station

Rev A, 0.1.0. Requirement IDs are referenced in [docs/traceability.md](docs/traceability.md).

## Scope
A test-bench PLC sequence for low-voltage synchronous alternators, with the recipe, the records and the analysis around it. Everything runs against a simulated alternator and bench. Limits are generic and illustrative.

## Functional requirements

| ID | Requirement |
|---|---|
| F01 | The sequence is one IEC 61131-3 Structured Text function block, compiled by a standard ST compiler (matiec) and run once per scan. |
| F02 | A production order selects a recipe: frame data, expected values, limits and options (CT, space heater, delta test connection, type test). |
| F03 | The sequence measures the four winding resistances and corrects them to 20 °C with the copper constant 235 (IEC 60034-1). |
| F04 | It measures insulation resistance after a fixed time. A result below the limit stops the test before HV and before rotation. |
| F05 | It applies the dielectric test voltage 1000 V + 2 Un, at least 1500 V (IEC 60034-1), ramped, held and discharged. A trip or excess leakage fails the check and stops the test. |
| F06 | With external DC excitation at rated speed and no load, it finds the field current for rated voltage in closed loop, and checks that current, the phase sequence, the voltage unbalance and the AVR supply voltage. |
| F07 | On load at PF 0.8 it finds the field current for rated voltage, then drops the load with that current held and checks the saturated voltage ratio. |
| F08 | It restarts with the AVR and records the frequency at which the voltage first passes the build-up level. |
| F09 | With the AVR it checks the no-load voltage and the voltage regulation at PF 0.8 and PF 1.0, plus the CT secondary current and polarity when a CT is fitted. |
| F10 | For machines tested in delta it reconnects to star only when de-excited and checks the star voltage. |
| F11 | With the excitation open it checks the remanent voltage. |
| F12 | Type tests add insulation after HV, 150 % overload for 30 s and 120 % overspeed for 2 min. |
| F13 | It checks the PT100, the PTC and the space heater resistance. |
| F14 | Each check latches its value and sets bits in chkDone / chkPass. The verdict is PASS only if every expected check is done and passed. |
| F15 | Units larger than the bench can load are tested at the bench limit, and this is shown on the report. |
| F16 | A unit without AVR voltage skips the load points and still finishes with remanence, run-down and probes. |
| F17 | Every unit gets a PDF + JSON report under its serial number and a row in the test database. Failed units also get a non-conformity with a likely cause and a route. |
| F18 | A Siemens TIA Portal SCL source is generated from the ST source and kept in step by a test. |
| F19 | Batch analysis reports fault detection, false rejects, escapes, Cpk per check and frame, a Pareto of causes, test time per frame and test benches needed at 1×–3× output. |
| F20 | Test times per frame are exported in the format the plant ramp-up model reads (test_times.json). |

## Safety and robustness requirements

| ID | Requirement |
|---|---|
| S01 | HV and the megger are only on with the gate closed and the rotor at rest. Opening the gate removes HV in the same scan and aborts. |
| S02 | The drive never runs while HV or the megger is applied, or while the HV source is not discharged. |
| S03 | Load and excitation are only on while the drive runs. |
| S04 | E-stop, operator abort, bench fault and drive fault abort in the same scan and put all outputs in the safe state. |
| S05 | Every step has a timeout. A timeout aborts with the step number recorded. |
| S06 | A test starts only on a rising start edge with the operator's pre-checks confirmed and the E-stop healthy. After an abort, a reset is needed before a new start. |

## Performance and verification requirements

| ID | Requirement |
|---|---|
| P01 | Every modelled fault is rejected by the check designed for it, on every frame where it can occur. |
| P02 | No faulty unit passes in the production batch (no escapes). |
| P03 | The PLC's pass/fail decisions agree with an independent Python re-evaluation on every check of every unit. |
| P04 | Simulating one unit takes under 1 s, so batches of hundreds of units run in CI. |
| P05 | Good units are rejected rarely. Measured: 2 of 361 (both tolerance-edge cases; see the README). |
