#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Andy Stewart

set -euo pipefail
plugin_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
runtime_dir="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-days/venv"
python3 -m venv "$runtime_dir"
"$runtime_dir/bin/python" -m pip install --disable-pip-version-check -r "$plugin_dir/requirements.txt"
printf '依赖已安装：%s\n' "$runtime_dir"
