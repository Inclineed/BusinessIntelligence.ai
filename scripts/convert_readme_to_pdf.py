"""
scripts/convert_readme_to_pdf.py — Python wrapper that converts README.md to PDF with server-side KaTeX math rendering.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
JS_SCRIPT = SCRIPT_DIR / "convert_readme_to_pdf.js"


def main() -> None:
    res = subprocess.run(["node", str(JS_SCRIPT)], check=False)
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
