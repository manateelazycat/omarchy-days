// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart
import QtQuick

Item {
    id: root
    visible: false
    required property var process
    property int timeout: 120000
    property int killDelay: 1000
    property bool timedOut: false

    Connections {
        target: root.process
        function onStarted() {
            root.timedOut = false
            killTimer.stop()
            deadlineTimer.restart()
        }
        function onExited() {
            deadlineTimer.stop()
            killTimer.stop()
        }
    }
    Timer {
        id: deadlineTimer
        interval: root.timeout
        onTriggered: {
            if (!root.process.running) return
            root.timedOut = true
            root.process.signal(15)
            killTimer.restart()
        }
    }
    Timer {
        id: killTimer
        interval: root.killDelay
        onTriggered: if (root.process.running) root.process.signal(9)
    }
}
