#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Andy Stewart
"""Read a user-requested Wayland clipboard outside the shell, with hard bounds."""
import json
import os
import selectors
import subprocess
import sys
import time

MAX_BYTES = 4096
TIMEOUT = 1.0


def read_clipboard():
    deadline = time.monotonic() + TIMEOUT
    with subprocess.Popen(
        ["wl-paste", "--no-newline", "--type", "text"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ) as process:
        try:
            data = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ValueError("剪贴板读取超时")
                    chunk = os.read(process.stdout.fileno(), min(4096, MAX_BYTES + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError("剪贴板文本超过 4 KiB")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("剪贴板读取超时")
            try:
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise ValueError("剪贴板读取超时") from exc
            if code != 0:
                raise ValueError("无法读取剪贴板文本")
            return data.decode("utf-8")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def main():
    try:
        result = {"ok": True, "text": read_clipboard()}
    except (OSError, ValueError) as exc:
        result = {"ok": False, "error": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
