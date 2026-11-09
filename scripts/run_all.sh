#!/usr/bin/env bash
# Full pipeline: compile the PLC code, run the tests, run the batches, and
# regenerate every result file and README image.
#   QUICK=1  smaller batches (used in CI)
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"

bash scripts/build_plc.sh
"$PYTHON" plc/st_to_scl.py plc/st/routine_test.st plc/scl/RoutineTest.scl
"$PYTHON" -m pytest -q

if [ "${QUICK:-0}" = "1" ]; then
  "$PYTHON" -m station batch --n 80 --seed 1
  "$PYTHON" -m station sweep --reps 2
  "$PYTHON" -m station analyse
  exit 0
fi

"$PYTHON" -m station batch --n 400 --seed 1
"$PYTHON" -m station sweep --reps 10
"$PYTHON" -m station analyse
"$PYTHON" -m station gif
"$PYTHON" -m station test --frame medium --serial EX-0001-PASS --seed 2 --out docs/examples
"$PYTHON" -m station test --frame medium --fault DIODE_OPEN --serial EX-0002-FAIL --seed 5 --out docs/examples
if command -v pdftoppm >/dev/null; then
  "$PYTHON" tools/pdf_to_png.py docs/examples/EX-0001-PASS.pdf docs/img/report_pass.png
  "$PYTHON" tools/pdf_to_png.py docs/examples/EX-0002-FAIL.pdf docs/img/report_fail.png
fi
