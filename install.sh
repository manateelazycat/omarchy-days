#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Andy Stewart

set -euo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
target_dir="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/andy.days"
command -v omarchy >/dev/null
command -v omarchy-shell >/dev/null
omarchy plugin validate "$source_dir"
bash "$source_dir/bootstrap.sh"
mkdir -p "$target_dir"
if [[ "$source_dir" != "$target_dir" ]]; then
  if [[ -d "$target_dir/.git" ]]; then
    printf '目标是 Git 安装目录，请在该目录中更新插件：%s\n' "$target_dir" >&2
    exit 1
  fi
  for item in manifest.json BarWidget.qml CalendarIcon.qml DaysPanel.qml DaysModel.qml ActionButton.qml Label.qml WeatherIcon.qml backend.py requirements.txt bootstrap.sh install.sh data licenses README.md LICENSE preview.png; do
    cp -R -- "$source_dir/$item" "$target_dir/"
  done
fi
omarchy-shell shell rescanPlugins
days_ready=0
for days_attempt in {1..50}; do
  if omarchy-shell shell listPlugins 2>/dev/null | jq -e 'any(.[]; .id == "andy.days")' >/dev/null 2>&1; then
    days_ready=1
    break
  fi
  sleep 0.1
done
if [[ "$days_ready" != 1 ]]; then
  printf '插件文件已安装，但 Shell 尚未完成扫描，请稍后运行：omarchy plugin enable andy.days\n' >&2
  exit 1
fi
days_placement=(--section right)
days_shell_config="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/shell.json"
for days_tray in io.github.manateelazycat.tray-bar omarchy.tray; do
  if [[ -f "$days_shell_config" ]] && jq -e --arg id "$days_tray" 'any(.bar.layout.right[]?; .id == $id)' "$days_shell_config" >/dev/null 2>&1; then
    days_placement+=(--after "$days_tray")
    break
  fi
done
omarchy plugin enable andy.days "${days_placement[@]}"
printf '已安装并启用日历与天气。点击任务栏托盘区域的日历图标即可打开。\n'
