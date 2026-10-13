# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clipboard


class ClipboardTests(unittest.TestCase):
    def run_owner(self, body):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / 'wl-paste'
            program.write_text('#!' + sys.executable + '\n' + body)
            program.chmod(0o755)
            with patch.dict(os.environ, {'PATH': directory}), patch.object(clipboard, 'TIMEOUT', 0.2):
                return clipboard.read_clipboard()

    def test_utf8(self):
        self.assertEqual(self.run_owner("import sys; sys.stdout.buffer.write('上海'.encode())"), '上海')

    def test_exact_limit(self):
        self.assertEqual(len(self.run_owner("import sys; sys.stdout.write('x' * 4096)")), 4096)

    def test_rejects_large_and_endless_data(self):
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, '4 KiB'):
            self.run_owner("import os\nwhile True: os.write(1, b'x' * 4096)")
        self.assertLess(time.monotonic() - started, 1)

    def test_stalled_owner(self):
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, '超时'):
            self.run_owner("import time; time.sleep(60)")
        self.assertLess(time.monotonic() - started, 1)

    def test_slow_trickle_uses_total_deadline(self):
        with self.assertRaisesRegex(ValueError, '超时'):
            self.run_owner("import os, time\nwhile True:\n os.write(1, b'x'); time.sleep(0.02)")

    def test_closed_output_without_exit(self):
        with self.assertRaisesRegex(ValueError, '超时'):
            self.run_owner("import os, time; os.close(1); time.sleep(60)")

    def test_failure(self):
        with self.assertRaisesRegex(ValueError, '无法读取'):
            self.run_owner("raise SystemExit(1)")

    def test_invalid_utf8(self):
        with self.assertRaises(UnicodeDecodeError):
            self.run_owner("import os; os.write(1, b'\\xff')")
