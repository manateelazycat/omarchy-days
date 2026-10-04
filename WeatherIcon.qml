// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import qs.Commons

Canvas {
    id: root
    property string icon: "unknown"
    property color ink: Color.accent
    implicitWidth: 36
    implicitHeight: 36
    onIconChanged: requestPaint()
    onInkChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var c = getContext("2d")
        c.reset()
        c.scale(width / 48, height / 48)
        c.strokeStyle = ink
        c.fillStyle = ink
        c.lineWidth = 2
        c.lineCap = "round"
        c.lineJoin = "round"
        function line(x, y, a, b) { c.beginPath(); c.moveTo(x, y); c.lineTo(a, b); c.stroke() }
        if (icon === "sun" || icon === "partly") {
            var sx = icon === "partly" ? 16 : 24
            var sy = icon === "partly" ? 17 : 24
            c.beginPath(); c.arc(sx, sy, 7, 0, Math.PI * 2); c.stroke()
            for (var i = 0; i < 8; i++) {
                var a = i * Math.PI / 4
                line(sx + Math.cos(a) * 11, sy + Math.sin(a) * 11, sx + Math.cos(a) * 14, sy + Math.sin(a) * 14)
            }
        }
        if (["partly", "cloud", "rain", "snow", "storm", "fog"].indexOf(icon) >= 0) {
            c.beginPath(); c.moveTo(12, 32); c.bezierCurveTo(2, 32, 2, 19, 13, 20)
            c.bezierCurveTo(14, 7, 32, 8, 33, 21); c.bezierCurveTo(45, 19, 46, 32, 36, 32)
            c.closePath(); c.stroke()
        }
        if (icon === "rain") { line(15, 36, 12, 42); line(25, 36, 22, 42); line(35, 36, 32, 42) }
        if (icon === "fog") { line(9, 37, 38, 37); line(14, 42, 33, 42) }
        if (icon === "snow") {
            for (var j = 0; j < 3; j++) { var x = 14 + 10 * j; line(x - 2, 39, x + 2, 39); line(x, 37, x, 41) }
        }
        if (icon === "storm") { c.beginPath(); c.moveTo(26, 33); c.lineTo(19, 39); c.lineTo(26, 39); c.lineTo(22, 46); c.stroke() }
        if (icon === "unknown") { c.font = "24px sans-serif"; c.textAlign = "center"; c.fillText("?", 24, 33) }
    }
}
