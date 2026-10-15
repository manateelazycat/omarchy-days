// SPDX-License-Identifier: GPL-3.0-only
// Run through test_precipitation_chart.py for an isolated QML environment.
import QtQuick
import Quickshell
import "."

ShellRoot {
    PrecipitationChart {
        id: chart
        width: 460; height: 42; maximum: 0.3
        points: Array.from({length: 23}, function(_, i) { return {amount: i < 15 ? 0 : 0.1} })
    }
    Timer {
        interval: 100; running: true
        onTriggered: {
            var bars = {}
            for (var i = 0; i < chart.children.length; i++) {
                var child = chart.children[i]
                if (child.objectName.indexOf("precipitation-") === 0) bars[child.objectName] = child
            }
            if (Object.keys(bars).length !== 23 || bars["precipitation-0"].height !== 0
                || bars["precipitation-15"].x !== 300 || bars["precipitation-22"].x !== 440
                || Math.abs(bars["precipitation-15"].height - 40 / 3) > 0.01) {
                console.error("FAIL: precipitation time slots or scale")
                Qt.exit(1)
            } else {
                console.log("PASS: zero precipitation keeps its time slot; first rain at slot 15; scale preserved")
                Qt.quit()
            }
        }
    }
}
