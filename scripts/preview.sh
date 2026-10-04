#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Andy Stewart

set -euo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
preview_dir=$(mktemp -d /tmp/omarchy-days-preview.XXXXXX)
trap 'rm -rf -- "$preview_dir"' EXIT
ln -s /usr/share/omarchy/shell/Commons "$preview_dir/Commons"
ln -s /usr/share/omarchy/shell/Ui "$preview_dir/Ui"
ln -s "$source_dir" "$preview_dir/Days"
cp "$source_dir/tests/Preview.qml" "$preview_dir/shell.qml"
printf 'Preview configuration: %s\n' "$preview_dir"
quickshell -p "$preview_dir" --no-color
