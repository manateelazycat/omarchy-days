import "CompatUi" as ThemeUi
// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import Quickshell.Io
import qs.Ui

BarWidget {
    id: root
    moduleName: "andy.days"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    readonly property bool opened: panel.opened
    readonly property bool popoutSwitchClosing: panel.popoutSwitchClosing
    readonly property bool preservePopupContentAppearance: true

    function open() { panel.open() }
    function close() { panel.close() }
    function toggle() { root.opened ? root.close() : root.open() }
    function closeForPopoutSwitch() { panel.closeForPopoutSwitch() }
    function persist(values) {
        var entry = {id: root.moduleName}
        for (var key in root.settings) if (key !== "id") entry[key] = root.settings[key]
        for (var field in values) entry[field] = values[field]
        var changed = false
        for (var name in values) {
            if (JSON.stringify(root.settings[name]) !== JSON.stringify(values[name])) changed = true
        }
        // updateEntryInline returns false for a no-op, not just an error.
        if (!changed) { panel.settingsError = ""; return }
        if (!root.bar || !root.bar.shell || typeof root.bar.shell.updateEntryInline !== "function") {
            panel.settingsError = "城市设置保存接口不可用，请重新加载插件"
            return
        }
        if (!root.bar.shell.updateEntryInline(root.moduleName, entry)) {
            panel.settingsError = "城市设置保存失败，请重新打开插件后重试"
            return
        }
        // Let the host update settings on every monitor through its config
        // change handler; avoid a separate local-only settings assignment.
        panel.settingsError = ""
    }

    ThemeUi.BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        iconComponent: Component {
            CalendarIcon {
                color: button.active && button.useActiveColor ? button.activeColor : button.foreground
            }
        }
        active: root.opened
        tooltipText: "日历与天气"
        onPressed: function(b) {
            if (b === Qt.MiddleButton) panel.refresh()
            else if (b === Qt.LeftButton) root.toggle()
        }
    }
    DaysPanel {
        id: panel
        bar: root.bar
        anchorItem: button
        hostWidget: root
        city: root.setting("city", null)
        locationMode: root.setting("locationMode", "auto")
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
    }
}
