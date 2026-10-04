// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: root
    visible: false

    property bool active: false
    property var todayData: null
    property string error: ""
    property string dayKey: ""
    readonly property string helper: decodeURIComponent(String(Qt.resolvedUrl("backend.py")).replace(/^file:\/\//, ""))

    function refresh() {
        if (!root.active || process.running) return
        process.command = ["python3", helper, "today"]
        process.running = true
    }

    onActiveChanged: if (active) refresh()

    SystemClock {
        precision: SystemClock.Minutes
        onDateChanged: {
            var key = Qt.formatDate(date, "yyyy-MM-dd")
            if (key !== root.dayKey) {
                root.dayKey = key
                if (root.active) Qt.callLater(root.refresh)
            }
        }
    }

    Process {
        id: process
        stdout: StdioCollector { id: todayOut; waitForEnd: true }
        stderr: StdioCollector { id: todayErr; waitForEnd: true }
        onExited: function(code) {
            try { var result = JSON.parse(String(todayOut.text || "{}")) }
            catch (e) { result = {ok: false, error: String(todayErr.text || "").trim() || "无法读取今日数据"} }
            if (code === 0 && result.ok) {
                root.todayData = result
                root.error = ""
            } else {
                root.error = result.error || "今日数据加载失败"
            }
        }
    }
}
