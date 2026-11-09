# Sequence

Step numbers as in `plc/st/routine_test.st` (`S_*` constants). From any busy step, an abort condition goes to `ABORTED (900)`, which needs a reset to return to `IDLE`.

```mermaid
stateDiagram-v2
    direction TB
    IDLE: 0 IDLE
    PRE: 10 PRECHECK
    RES: 20 RES (4 channels)
    IRB: 30 IR_BEFORE
    HVR: 31 HV_RAMP
    HVH: 32 HV_HOLD
    HVD: 33 HV_DOWN
    IRA: 34 IR_AFTER (type test)
    RUX: 40 RUNUP_EXT
    NLX: 41 NOLOAD_EXT
    OLX: 43 ONLOAD_EXT
    CUT: 44 CUTOFF
    STX: 45 STOP_EXT
    RUA: 50 RUNUP_AVR
    ANL: 51 AVR_NOLOAD
    P08: 52 PF08
    P10: 53 PF10
    OVL: 54 OVERLOAD (type test)
    UNL: 55 UNLOAD
    SDX: 56 STAR_DEEXC
    SCK: 57 STAR_CHECK
    REM: 58 REMANENT
    OSU: 60 OVERSPEED_UP (type test)
    OSH: 61 OVERSPEED_HOLD
    RDN: 62 RUNDOWN
    PRB: 70 PROBES
    FIN: 90 FINISH
    DONE: 99 DONE

    IDLE --> PRE: start edge, operator checks OK
    PRE --> RES: drive + load ready, gate closed, rotor at rest
    RES --> IRB
    IRB --> HVR: IR >= limit
    IRB --> FIN: IR low (stop early)
    HVR --> HVH: at test voltage
    HVH --> HVD: time done, or trip / leakage
    HVD --> IRA: type test
    HVD --> RUX: routine test
    HVD --> FIN: after HV failure
    IRA --> RUX
    RUX --> NLX: at rated speed
    NLX --> OLX: field current settled
    OLX --> CUT: settled on load
    CUT --> STX
    STX --> RUA: speed < 5 %
    RUA --> ANL: at rated speed (build-up frequency latched)
    ANL --> P08: AVR voltage present
    ANL --> REM: no AVR voltage (skip load points)
    P08 --> P10
    P10 --> OVL: type test
    P10 --> UNL
    OVL --> UNL
    UNL --> SDX: delta test connection
    UNL --> REM
    SDX --> SCK: de-excited, switch to star
    SCK --> REM
    REM --> OSU: type test
    REM --> RDN
    OSU --> OSH
    OSH --> RDN
    RDN --> PRB: rotor at rest
    PRB --> FIN
    FIN --> DONE
    DONE --> PRE: next start
```

## Output stage (every scan, after the step logic)

1. In IDLE, DONE, FINISH and ABORTED, all outputs go to their safe values.
2. HV and the megger are only allowed with the gate closed and the speed below 1 rpm.
3. The drive is only allowed with HV and the megger off and the HV source discharged.
4. Load and excitation are only allowed with the drive running.
