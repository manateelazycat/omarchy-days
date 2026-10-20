# SPDX-License-Identifier: GPL-3.0-only
"""Run the real Quickshell process lifecycle without touching the desktop."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
QUICKSHELL = shutil.which("qs") or shutil.which("quickshell")


@unittest.skipUnless(QUICKSHELL, "Quickshell is needed for process lifecycle tests")
class ProcessWatchdogTests(unittest.TestCase):
    def run_qml(self, path, expected):
        result = subprocess.run([QUICKSHELL, "--path", str(path), "--no-color"],
                                env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                                capture_output=True, text=True, timeout=8)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("FAIL:", output)
        self.assertIn(expected, output)

    def test_termination_force_kill_and_restart(self):
        with tempfile.TemporaryDirectory(prefix="days-watchdog-test-") as directory:
            directory = Path(directory)
            shutil.copyfile(ROOT / "ProcessWatchdog.qml", directory / "ProcessWatchdog.qml")
            shutil.copyfile(ROOT / "tests/process_watchdog.qml", directory / "shell.qml")
            self.run_qml(directory / "shell.qml", "PASS: process watchdog")

    def test_weather_refresh_queued_behind_hung_process_recovers(self):
        with tempfile.TemporaryDirectory(prefix="days-watchdog-test-") as directory:
            directory = Path(directory)
            for name in ("DaysModel.qml", "ProcessWatchdog.qml"):
                shutil.copyfile(ROOT / name, directory / name)
            (directory / "session_watch.py").write_text(
                "import time\nprint('{\"available\":true}', flush=True)\ntime.sleep(10)\n")
            (directory / "weather_notifications.py").write_text("import sys\nsys.stdin.readline()\n")
            (directory / "backend.py").write_text('''import json, signal, sys, time
from pathlib import Path
if sys.argv[1] == "weather":
    marker = Path(__file__).with_name("first-weather")
    if not marker.exists():
        marker.touch()
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(10)
    print(json.dumps({"ok": True, "forced": "--force" in sys.argv, "refreshAfter": 900}), flush=True)
else:
    print('{"ok":true,"enabled":false}', flush=True)
''')
            (directory / "shell.qml").write_text('''import QtQuick
import Quickshell
ShellRoot {
    id: root
    property bool queued: false
    function fail(message) { console.error("FAIL: " + message); Qt.quit() }
    DaysModel { id: model }
    Component.onCompleted: {
        for (var child of model.children) {
            if (child.timeout !== undefined && child.killDelay !== undefined) {
                child.timeout = 1000
                child.killDelay = 100
            }
        }
    }
    Timer {
        interval: 20; running: true; repeat: true
        onTriggered: {
            if (!root.queued && model.weatherBusy) {
                root.queued = true
                model.refreshWeather(true)
                if (!model.weatherPending) root.fail("refresh was not queued")
            }
            if (root.queued && model.weatherData) {
                if (!model.weatherData.forced || model.weatherBusy || model.weatherPending) {
                    root.fail("queued refresh did not finish or lost its force flag")
                    return
                }
                console.log("PASS: queued weather refresh recovered after timeout")
                Qt.quit()
            }
        }
    }
    Timer { interval: 5000; running: true; onTriggered: root.fail("weather remained stuck") }
}
''')
            self.run_qml(directory / "shell.qml", "PASS: queued weather refresh recovered")


if __name__ == "__main__":
    unittest.main()
