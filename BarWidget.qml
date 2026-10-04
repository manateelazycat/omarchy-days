// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import Quickshell.Io
import qs.Ui
import qs.Commons

BarWidget {
    id: root
    moduleName: "andy.days"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    readonly property bool opened: panel.opened
    readonly property bool popoutSwitchClosing: panel.popoutSwitchClosing
    readonly property bool preservePopupContentAppearance: true
    property string iconMode: root.setting("iconMode", "calendar")
    readonly property string iconModeLabel: barSizer.modeLabel(iconMode)

    function open() { panel.open() }
    function close() { panel.close() }
    function toggle() { root.opened ? root.close() : root.open() }
    function closeForPopoutSwitch() { panel.closeForPopoutSwitch() }
    function cycleIconMode() {
        var modes = barSizer.modes
        var index = modes.length - 1
        for (var i = 0; i < modes.length; i++) if (modes[i].id === root.iconMode) { index = i; break }
        root.persist({iconMode: modes[(index + 1) % modes.length].id})
    }
    function persist(values) {
        var entry = {id: root.moduleName}
        for (var key in root.settings) if (key !== "id") entry[key] = root.settings[key]
        for (var field in values) entry[field] = values[field]
        if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function") {
            if (!root.bar.shell.updateEntryInline(root.moduleName, entry)) {
                panel.settingsError = "城市设置保存失败，请重新打开插件后重试"
                return
            }
        }
        root.settings = entry
        panel.settingsError = ""
    }

    BarContent {
        id: barSizer
        visible: false
        mode: root.iconMode
        vertical: root.vertical
        weather: panel.weatherModel.weatherData
        todayData: todayModel.todayData
    }

    TodayModel {
        id: todayModel
        active: root.iconMode === "lunar" || root.iconMode === "holiday"
    }

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        slotSize: root.iconMode === "calendar"
            ? Style.bar.iconSlot
            : Math.ceil(root.vertical ? barSizer.implicitHeight : barSizer.implicitWidth) + Style.bar.iconSlot - Style.bar.iconCanvas
        iconComponent: barComponent
        active: root.opened
        tooltipText: "日历与天气 · 右键切换显示（当前：" + (root.iconModeLabel || "日历") + "）"
        onPressed: function(b) {
            if (b === Qt.MiddleButton) panel.refresh()
            else if (b === Qt.RightButton) root.cycleIconMode()
            else if (b === Qt.LeftButton) root.toggle()
        }
    }

    Component {
        id: barComponent
        BarContent {
            mode: root.iconMode
            vertical: root.vertical
            weather: panel.weatherModel.weatherData
            todayData: todayModel.todayData
            color: button.active && button.useActiveColor ? button.activeColor : button.foreground
        }
    }

    DaysPanel {
        id: panel
        bar: root.bar
        anchorItem: button
        hostWidget: root
        city: root.setting("city", null)
        locationMode: root.setting("locationMode", "auto")
        barIconMode: root.iconMode
        onCitySelected: function(city) { root.persist({locationMode: "manual", city: city}) }
        onAutomaticRequested: root.persist({locationMode: "auto", city: null})
    }
    IpcHandler {
        target: "andy.days"
        function open(): void { root.open() }
        function show(): void { root.open() }
        function close(): void { root.close() }
        function hide(): void { root.close() }
        function toggle(): void { root.toggle() }
        function refresh(): void { panel.refresh() }
        function cycleIconMode(): void { root.cycleIconMode() }
        function setIconMode(mode: string): void {
            for (var i = 0; i < barSizer.modes.length; i++) if (barSizer.modes[i].id === mode) { root.persist({iconMode: mode}); return }
        }
    }
}
