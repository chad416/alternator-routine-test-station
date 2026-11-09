"""The TIA Portal SCL file is generated from the ST source and must stay in step."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_scl_is_up_to_date(tmp_path):
    out = tmp_path / "RoutineTest.scl"
    subprocess.run([sys.executable, str(ROOT / "plc" / "st_to_scl.py"),
                    str(ROOT / "plc" / "st" / "routine_test.st"), str(out)], check=True)
    committed = (ROOT / "plc" / "scl" / "RoutineTest.scl").read_bytes()
    assert out.read_bytes() == committed, "run plc/st_to_scl.py and commit plc/scl/RoutineTest.scl"


def test_scl_dialect():
    scl = (ROOT / "plc" / "scl" / "RoutineTest.scl").read_text(encoding="utf-8")
    code = scl.split("BEGIN", 2)[2]
    code = re.sub(r"\(\*.*?\*\)", "", code, flags=re.S)
    assert "DWORD#" not in code
    assert '"BIT_OF"(id := ' in code
    assert re.search(r"LIMIT\(MN := ", code)
    # a few locals that must carry the '#' prefix wherever they are used
    for name in ("stepNo", "chkPass", "uAvg", "rcUn", "qHvOn"):
        bare = re.findall(rf"(?<![#\w.]){name}\b", code)
        assert bare == [], f"{name} used without '#'"
