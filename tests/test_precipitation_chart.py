# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PrecipitationChartTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('quickshell'), 'Requires Quickshell')
    def test_zero_bars_preserve_timeline_in_actual_qml(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            shutil.copy2(root / 'PrecipitationChart.qml', directory)
            shutil.copy2(root / 'tests/precipitation_chart.qml', Path(directory) / 'shell.qml')
            result = subprocess.run(['quickshell', '-p', directory],
                env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS:', result.stdout + result.stderr)
