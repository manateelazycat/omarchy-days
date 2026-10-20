// SPDX-License-Identifier: GPL-3.0-only
// Run through Quickshell: its Io plugin is linked into the executable.
import QtQuick
import Quickshell
import Quickshell.Io
import "." as Days

ShellRoot {
    id: root
    property int stage: 0

    function check(condition, message) {
        if (condition) return true
        console.error("FAIL: " + message)
        Qt.quit()
        return false
    }
    Process {
        id: worker
        stdout: StdioCollector { id: output; waitForEnd: false }
        onExited: function(code) {
            if (root.stage === 0) {
                if (!root.check(watchdog.timedOut && code === 9 && output.text.indexOf("ready") !== -1,
                                "hung process must receive SIGKILL after ignoring SIGTERM")) return
                root.stage = 1
                Qt.callLater(function() {
                    worker.command = ["python3", "-c", "print('{\"ok\":true}')"]
                    worker.running = true
                })
            } else if (root.stage === 1) {
                if (!root.check(!watchdog.timedOut && JSON.parse(output.text).ok,
                                "the next request must succeed with a fresh deadline")) return
                root.stage = 2
                finishTimer.start()
            } else root.check(false, "an old timer affected the next request")
        }
    }
    Days.ProcessWatchdog {
        id: watchdog
        process: worker
        timeout: 1000
        killDelay: 100
    }
    Component.onCompleted: {
        worker.command = ["python3", "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(10)"]
        worker.running = true
    }
    Timer {
        id: finishTimer
        interval: 1200
        onTriggered: {
            if (!root.check(root.stage === 2 && !worker.running && !watchdog.timedOut,
                            "completed requests must cancel their watchdog timers")) return
            console.log("PASS: process watchdog termination, forced kill, restart and timer cleanup")
            Qt.quit()
        }
    }
    Timer { interval: 5000; running: true; onTriggered: root.check(false, "test timed out") }
}
