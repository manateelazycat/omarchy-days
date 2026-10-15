// SPDX-License-Identifier: GPL-3.0-only
import QtQuick

Item {
    id: chart
    property var points: []
    property real maximum: 1
    property color barColor: "#7aa2f7"
    readonly property real slotWidth: points.length ? width / points.length : 0
    Repeater {
        model: chart.points
        Rectangle {
            required property var modelData
            required property int index
            objectName: "precipitation-" + index
            // Explicit time slots keep zero-height bars from collapsing time.
            x: index * chart.slotWidth
            y: chart.height - height
            width: Math.max(0, chart.slotWidth - 2)
            height: Math.max(0, modelData.amount) / Math.max(0.001, chart.maximum) * (chart.height - 2)
            color: chart.barColor
            radius: 1
            opacity: 0.85
        }
    }
}
