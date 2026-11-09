"""ctypes wrapper around the compiled ST function block (build/plc/librt.so)."""

from __future__ import annotations

import ctypes
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "plc"


def _struct(name: str, fields: list[list[str]]) -> type[ctypes.Structure]:
    return type(name, (ctypes.Structure,), {"_fields_": [(n, getattr(ctypes, t)) for n, t in fields]})


class Plc:
    """One instance of FUNCTION_BLOCK ROUTINE_TEST.

    The shared library holds a single static instance, so each process gets
    exactly one PLC. Batch runs use one process per worker.
    """

    def __init__(self, build_dir: Path = BUILD):
        io = json.loads((build_dir / "io_map.json").read_text())
        self.In = _struct("rt_in_t", io["inputs"])
        self.Out = _struct("rt_out_t", io["outputs"])
        self.constants: dict[str, int] = io["constants"]
        self.lib = ctypes.CDLL(str(build_dir / "librt.so"))
        assert self.lib.rt_sizeof_in() == ctypes.sizeof(self.In), "io_map does not match librt.so"
        assert self.lib.rt_sizeof_out() == ctypes.sizeof(self.Out), "io_map does not match librt.so"
        self.lib.rt_scan.argtypes = [ctypes.POINTER(self.In), ctypes.POINTER(self.Out)]
        self.inp = self.In()
        self.out = self.Out()
        self.input_names = {n for n, _ in io["inputs"]}
        self.output_names = [n for n, _ in io["outputs"]]
        self.lib.rt_init()

    def reset(self) -> None:
        self.lib.rt_init()
        ctypes.memset(ctypes.byref(self.inp), 0, ctypes.sizeof(self.In))

    def set(self, **values: float) -> None:
        for k, v in values.items():
            name = k.upper()
            if name not in self.input_names:
                raise KeyError(f"unknown PLC input {k}")
            setattr(self.inp, name, v)

    def scan(self) -> None:
        self.lib.rt_scan(ctypes.byref(self.inp), ctypes.byref(self.out))

    def get(self, name: str):
        return getattr(self.out, name.upper())

    def outputs(self) -> dict:
        return {n: getattr(self.out, n) for n in self.output_names}

    def check_ids(self) -> dict[str, int]:
        """Check name -> bit number, from the C_* constants in the ST source."""
        return {k[2:]: v for k, v in self.constants.items() if k.startswith("C_")}

    def step_names(self) -> dict[int, str]:
        return {v: k[2:] for k, v in self.constants.items() if k.startswith("S_")}

    def abort_names(self) -> dict[int, str]:
        return {v: k[2:] for k, v in self.constants.items() if k.startswith("A_")}
