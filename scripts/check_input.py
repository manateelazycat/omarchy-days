#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run input editing tests and a Qt clipboard probe regression check."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
runner = shutil.which("qmltestrunner") or "/usr/lib/qt6/bin/qmltestrunner"
subprocess.run([runner, "-input", str(root / "tests/tst_cityinput.qml")], env=environment, check=True)
with tempfile.TemporaryDirectory(prefix="days-input-check-") as directory:
    binary = str(Path(directory) / "clipboard-probe")
    flags = shlex.split(subprocess.check_output(
        ["pkg-config", "--cflags", "--libs", "Qt6Quick", "Qt6Gui", "Qt6Qml"], text=True))
    subprocess.run(["g++", "-std=c++17", str(root / "tests/clipboard_probe.cpp"), "-o", binary, *flags], check=True)
    subprocess.run([binary, str(root / "SafeCityInput.qml")], env=environment, check=True)
