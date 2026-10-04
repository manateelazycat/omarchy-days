// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import Quickshell
import Quickshell.Io
import "Days" as Days
import qs.Commons

ShellRoot {
    function panelItem() {
        for (var i = 0; i < widget.children.length; i++)
            if ("locationMode" in widget.children[i] && "selectedDate" in widget.children[i]) return widget.children[i]
        return null
    }
    function dataItem() {
        var panel = panelItem()
        for (var i = 0; panel && i < panel.children.length; i++)
            if ("calendarData" in panel.children[i]) return panel.children[i]
        return null
    }
    QtObject {
        id: fakeBar
        property string position: "top"
        property bool vertical: false
        property int barSize: 36
        property color foreground: Color.foreground
        property color barForeground: Color.foreground
        property color background: Color.background
        property color urgent: Color.urgent
        property string fontFamily: Style.font.family
        property bool transparent: false
        property bool foregroundAnimationEnabled: true
        property bool centerSectionRevealHeld: false
        property bool centerHoverRevealSuppressed: false
        property var activePopout: null
        property var clickTargets: []
        property var previewSettings: ({locationMode: "manual", city: {name: "上海", englishName: "Shanghai", admin1: "上海市", country: "中国", country_code: "CN", latitude: 31.22222, longitude: 121.45806, timezone: "Asia/Shanghai"}})
        property QtObject shell: QtObject {
            function updateEntryInline(id, entry) { fakeBar.previewSettings = entry; return true }
        }
        function showTooltip(target, text) {}
        function hideTooltip(target) {}
        function registerClickTarget(target) { clickTargets = clickTargets.concat([target]) }
        function unregisterClickTarget(target) { clickTargets = clickTargets.filter(function(t) { return t !== target }) }
        function requestPopout(owner) { activePopout = owner }
        function releasePopout(owner) { if (activePopout === owner) activePopout = null }
        function switchPanelFrom(owner, direction) { return false }
        function targetBelongsToWindow(target, window) { return true }
        function moduleWidgets(id) { return [widget] }
        function run(command) {}
    }
    PanelWindow {
        screen: Quickshell.screens.find(function(s) { return s.name === "HDMI-A-1" }) || Quickshell.screens[0]
        anchors { top: true; left: true; right: true }
        implicitHeight: 36
        color: Color.background
        Days.BarWidget {
            id: widget
            anchors.horizontalCenter: parent.horizontalCenter
            width: 36; height: 36
            bar: fakeBar
            settings: fakeBar.previewSettings
        }
    }
    IpcHandler {
        target: "preview"
        function quit(): void { Qt.quit() }
        function open(): void { widget.open() }
        function close(): void { widget.close() }
        function position(value: string): void { fakeBar.position = value; fakeBar.vertical = value === "left" || value === "right" }
        function snapshot(): string {
            var panel = panelItem(), data = dataItem()
            return JSON.stringify({opened: widget.opened, city: fakeBar.previewSettings.city, mode: fakeBar.previewSettings.locationMode,
                calendarDays: data ? data.calendarData.days.length : 0, weatherDays: data && data.weatherData ? data.weatherData.days.length : 0,
                results: data ? data.results.length : 0, query: data ? data.searchQuery : "", selectedDate: panel ? panel.selectedDate : ""})
        }
        function month(delta: int): void { panelItem().moveMonth(delta) }
        function automatic(): void { panelItem().automaticRequested() }
    }
    Timer { interval: 500; running: true; onTriggered: widget.open() }
}
