// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart
//
// Status bar content module. Add a mode by extending `modes` below and giving
// it a branch in `textFor()` or a renderer item; BarWidget handles sizing,
// persistence, and right-click cycling automatically.

import QtQuick
import Quickshell
import qs.Commons

Item {
    id: root

    property string mode: "calendar"
    property var weather: null
    property var todayData: null
    property color color: "black"
    property bool vertical: false
    readonly property real iconExtent: Style.bar.iconCanvas

    readonly property var modes: [
        { id: "calendar", label: "日历" },
        { id: "weather", label: "天气" },
        { id: "weekday-time", label: "星期与时间" },
        { id: "date-time", label: "年月日与时间" },
        { id: "lunar", label: "农历" },
        { id: "holiday", label: "假日倒数" }
    ]

    function modeLabel(id) {
        for (var i = 0; i < root.modes.length; i++) if (root.modes[i].id === id) return root.modes[i].label
        return ""
    }

    readonly property var current: weather && weather.current ? weather.current : null
    readonly property string temperatureText: {
        var value = current ? current.temperature : null
        return typeof value === "number" && isFinite(value) ? Math.round(value) + "°" : ""
    }
    readonly property bool isTextMode: ["weekday-time", "date-time", "lunar", "holiday"].indexOf(mode) >= 0
    // Unknown mode values (e.g. leftover settings) fall back to the calendar glyph.
    readonly property bool isCalendar: mode !== "weather" && !isTextMode
    readonly property string timeText: Qt.formatTime(clock.date, "hh:mm")

    function textFor(id) {
        if (id === "weekday-time") return "周" + "日一二三四五六"[clock.date.getDay()] + " " + timeText
        if (id === "date-time") return clock.date.getFullYear() + "年" + (clock.date.getMonth() + 1) + "月" + clock.date.getDate() + "日 " + timeText
        if (id === "lunar") return todayData ? todayData.lunar : "—"
        if (id === "holiday") {
            var holiday = todayData ? todayData.holiday : null
            if (!holiday) return "假日待公布"
            return holiday.state === "during" ? holiday.name + " 剩" + holiday.days + "天" : "距" + holiday.name + " " + holiday.days + "天"
        }
        return ""
    }

    // Extent along the bar axis, used by the host button to widen its slot.
    readonly property real contentExtent: {
        if (mode === "weather") return vertical ? weatherIcon.implicitHeight : weatherIcon.implicitWidth
        if (isTextMode) return modeText.implicitWidth
        return iconExtent
    }
    implicitWidth: root.vertical ? Math.max(iconExtent, mode === "weather" ? weatherIcon.implicitWidth : 0) : Math.max(iconExtent, contentExtent)
    implicitHeight: root.vertical ? Math.max(iconExtent, contentExtent) : iconExtent

    SystemClock {
        id: clock
        precision: SystemClock.Minutes
    }

    CalendarIcon {
        visible: root.isCalendar
        anchors.centerIn: parent
        width: root.iconExtent
        height: root.iconExtent
        color: root.color
    }

    WeatherBarIcon {
        id: weatherIcon
        visible: root.mode === "weather"
        anchors.centerIn: parent
        vertical: root.vertical
        icon: root.current ? root.current.icon : "unknown"
        temperature: root.temperatureText
        color: root.color
    }

    Text {
        id: modeText
        visible: root.isTextMode
        anchors.centerIn: parent
        rotation: root.vertical ? 270 : 0
        text: root.textFor(root.mode)
        color: root.color
        font.family: Style.font.family
        font.pixelSize: Style.bar.iconFont
        renderType: Text.NativeRendering
    }
}
