"""Render page 1 of a report PDF to PNG for the README (needs pdftoppm)."""

import subprocess
import sys
from pathlib import Path

pdf = Path(sys.argv[1])
out = Path(sys.argv[2])
subprocess.run(["pdftoppm", "-png", "-r", "80", "-singlefile", str(pdf), str(out.with_suffix(""))], check=True)
print(out)
