# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the real HTTP stack against bounded local malicious responses."""
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def chunk(self, content):
        self.wfile.write(f"{len(content):x}\r\n".encode() + content + b"\r\n")
        self.wfile.flush()

    def do_GET(self):
        try:
            self.respond()
        except (OSError, ssl.SSLError):
            pass  # The client deliberately cuts off malicious responses.

    def respond(self):
        path = self.path
        if path in ("/redirect", "/slow-redirect"):
            self.send_response(302)
            self.send_header("Location", "/json" if path == "/redirect" else "/slow-headers")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/slow-headers":
            self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Slow: ")
            self.wfile.flush()
        else:
            status = 400 if path in ("/slow-error", "/no-location", "/bad-error") else 200
            self.send_response(status)
            if path in ("/slow-gzip", "/slow-error", "/empty-gzip"):
                self.send_header("Content-Encoding", "gzip")
            if path.startswith("/slow-") or path == "/empty-gzip":
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
            else:
                body = b'{"ok":true}'
                if path == "/gzip":
                    body = gzip.compress(body)
                elif path == "/multi-gzip":
                    body = gzip.compress(b'{"ok":') + gzip.compress(b'true}')
                elif path == "/large-output":
                    body = gzip.compress(json.dumps({"x": "a" * 2_000_000}).encode())
                elif path == "/large-json":
                    body = json.dumps({"x": "a" * 2_000_000}).encode()
                elif path in ("/boundary-json", "/boundary-gzip"):
                    body = b'{"x":"' + b"a" * (2_000_000 - 8) + b'"}'
                    if path == "/boundary-gzip":
                        body = gzip.compress(body)
                elif path == "/bad-gzip":
                    body = b"not gzip"
                elif path == "/truncated-gzip":
                    body = gzip.compress(body)[:-2]
                elif path == "/no-location":
                    body = gzip.compress(json.dumps({"error": {"type": "https://example.test/#no-such-location"}}).encode())
                elif path == "/bad-error":
                    body = b'{"error":"invalid"}'
                elif path == "/text":
                    body = "当前 IP：127.0.0.1  来自于：中国 江苏 苏州 联通".encode()
                elif path == "/large-text":
                    body = b"x" * 200_001
                elif path == "/weather":
                    today = backend.datetime.now(backend.ZoneInfo("Asia/Shanghai")).date().isoformat()
                    body = json.dumps({"daily": {"time": [today], "weather_code": [0],
                                                "temperature_2m_min": [10], "temperature_2m_max": [20]}}).encode()
                if path in ("/gzip", "/multi-gzip", "/large-output", "/bad-gzip", "/truncated-gzip", "/no-location", "/boundary-gzip"):
                    self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        # Stop after two seconds even if the client's deadline implementation
        # regresses, so a failing test cannot leave an infinite server thread.
        end = time.monotonic() + 2
        while time.monotonic() < end:
            if path == "/slow-headers":
                self.wfile.write(b"x")
            elif path == "/slow-chunk-header":
                self.wfile.write(b"0")
            elif path in ("/slow-gzip", "/slow-error", "/empty-gzip"):
                self.chunk(gzip.compress(b"") * (1024 if path == "/empty-gzip" else 1))
            else:
                self.chunk(b" ")
            self.wfile.flush()
            time.sleep(0.01)
        self.close_connection = True


class NetworkLimitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        # Keep user proxy configuration out of loopback tests.
        self.proxies = patch.dict(os.environ, {"no_proxy": "127.0.0.1"})
        self.proxies.start()
        self.addCleanup(self.proxies.stop)

    def url(self, path):
        return f"http://127.0.0.1:{self.server.server_port}{path}"

    def test_normal_json_gzip_and_multiple_members(self):
        for path in ("/json", "/gzip", "/multi-gzip", "/redirect"):
            with self.subTest(path=path):
                self.assertEqual(backend.fetch_json(self.url(path)), {"ok": True})

    def test_authenticated_requests_still_reject_redirects(self):
        with self.assertRaisesRegex(backend.DataError, "重定向"):
            backend.fetch_json(self.url("/redirect"), headers={"Authorization": "Bearer test"})

    def test_input_limit_counts_empty_members(self):
        with patch.object(backend, "GZIP_MAX_BYTES", 4_000):
            with self.assertRaisesRegex(backend.DataError, "数据过大"):
                backend.fetch_json(self.url("/empty-gzip"))

    def test_output_limit_for_compressed_and_uncompressed_json(self):
        for path in ("/large-output", "/large-json"):
            with self.subTest(path=path), self.assertRaisesRegex(backend.DataError, "数据过大"):
                backend.fetch_json(self.url(path))

    def test_existing_output_limit_is_inclusive(self):
        for path in ("/boundary-json", "/boundary-gzip"):
            with self.subTest(path=path):
                self.assertEqual(len(backend.fetch_json(self.url(path))["x"]), 2_000_000 - 8)

    def test_malformed_and_truncated_gzip_are_data_errors(self):
        for path in ("/bad-gzip", "/truncated-gzip"):
            with self.subTest(path=path), self.assertRaisesRegex(backend.DataError, "格式错误"):
                backend.fetch_json(self.url(path))

    def test_total_deadline_interrupts_streams_headers_and_chunk_framing(self):
        for path in ("/slow-gzip", "/slow-body", "/slow-error", "/slow-headers", "/slow-chunk-header", "/slow-redirect"):
            with self.subTest(path=path), patch.object(backend, "NETWORK_TOTAL_TIMEOUT", 0.25):
                start = time.monotonic()
                with self.assertRaisesRegex(backend.DataError, "超时"):
                    backend.fetch_json(self.url(path))
                self.assertLess(time.monotonic() - start, 1.5)
            # A timed-out request must not poison the next request's deadline.
            self.assertEqual(backend.fetch_json(self.url("/gzip")), {"ok": True})

    def test_error_response_preserves_no_location_handling(self):
        with self.assertRaises(backend.LocationNotFound):
            backend.fetch_json(self.url("/no-location"))
        with self.assertRaisesRegex(backend.DataError, "HTTP 400"):
            backend.fetch_json(self.url("/bad-error"))

    def test_text_requests_have_size_and_total_time_limits(self):
        self.assertIn("苏州", backend.fetch_text(self.url("/text")))
        with self.assertRaisesRegex(backend.DataError, "数据过大"):
            backend.fetch_text(self.url("/large-text"))
        with patch.object(backend, "NETWORK_TOTAL_TIMEOUT", 0.25):
            with self.assertRaisesRegex(backend.DataError, "超时"):
                backend.fetch_text(self.url("/slow-body"))

    def test_weather_uses_cached_data_on_timeout_and_refreshes_again(self):
        city = {"name": "北京", "latitude": 39.92, "longitude": 116.41, "timezone": "Asia/Shanghai"}
        fetch_json = backend.fetch_json
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(backend, "CACHE", Path(directory)), \
             patch.object(backend, "weather_settings", return_value={"provider": "open-meteo"}):
            with patch.object(backend, "fetch_json", side_effect=lambda *args: fetch_json(self.url("/weather"))):
                self.assertTrue(backend.get_weather(city)["ok"])
            with patch.object(backend, "NETWORK_TOTAL_TIMEOUT", 0.25), \
                 patch.object(backend, "fetch_json", side_effect=lambda *args: fetch_json(self.url("/slow-gzip"))):
                result = backend.get_weather(city, force=True)
                self.assertTrue(result["ok"])
                self.assertTrue(result["stale"])
                self.assertIn("缓存", result["warning"])
            with patch.object(backend, "fetch_json", side_effect=lambda *args: fetch_json(self.url("/weather"))):
                result = backend.get_weather(city, force=True)
                self.assertTrue(result["ok"])
                self.assertFalse(result["stale"])

    @unittest.skipUnless(shutil.which("openssl"), "openssl is needed for the local TLS fixture")
    def test_https_verification_and_deadline(self):
        with tempfile.TemporaryDirectory(prefix="days-network-tls-") as directory:
            cert, key = (str(Path(directory) / name) for name in ("cert.pem", "key.pem"))
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                            "-keyout", key, "-out", cert], check=True, capture_output=True)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.daemon_threads = True
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"https://127.0.0.1:{server.server_port}"
            try:
                with self.assertRaises(backend.DataError):
                    backend.fetch_json(url + "/gzip")
                trusted = ssl.create_default_context(cafile=cert)
                with patch("ssl._create_default_https_context", return_value=trusted):
                    self.assertEqual(backend.fetch_json(url + "/gzip"), {"ok": True})
                    with patch.object(backend, "NETWORK_TOTAL_TIMEOUT", 0.25):
                        with self.assertRaisesRegex(backend.DataError, "超时"):
                            backend.fetch_json(url + "/slow-gzip")
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
