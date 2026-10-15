// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart
import QtQuick
import Quickshell.Io
import qs.Commons as Commons

Item {
    id: root
    property bool editing: false
    property string effectiveProvider: ""
    property var currentLocation: null
    property bool loaded: false
    property var savedSettings: ({provider: "open-meteo", qweather: {}})
    property bool notifications: true
    property var customLocation: ({enabled: false, name: "", longitude: "", latitude: ""})
    property string provider: "open-meteo"
    property var draft: ({})
    property string testedDraft: ""
    property string message: ""
    property bool failed: false
    readonly property bool busy: process.running
    readonly property string connectionJson: JSON.stringify({provider: provider, qweather: draft})
    readonly property bool connectionUnchanged: connectionJson === JSON.stringify({provider: savedSettings.provider, qweather: savedSettings.qweather || {}})
    readonly property string draftJson: JSON.stringify({provider: provider, qweather: draft, notifications: notifications, customLocation: customLocation})
    signal configurationChanged()
    property real editorHeight: 650
    implicitHeight: 30 + (loadError.visible ? loadError.implicitHeight + 6 : 0)

    function load() { run("load") }
    function run(action) {
        if (busy) return
        message = ""
        process.action = action
        process.payload = draftJson
        process.command = ["python3", decodeURIComponent(String(Qt.resolvedUrl("backend.py")).replace(/^file:\/\//, "")), "weather-settings", action]
        process.running = true
    }
    function begin() {
        var savedLocation = savedSettings.customLocation || {}
        var hasSavedLocation = String(savedLocation.name || "").trim() !== ""
                && savedLocation.longitude !== undefined && String(savedLocation.longitude).trim() !== ""
                && savedLocation.latitude !== undefined && String(savedLocation.latitude).trim() !== ""
        var initialLocation = hasSavedLocation ? savedLocation : currentLocation || {}
        customLocation = {
            enabled: savedLocation.enabled === true,
            name: initialLocation.name || "",
            longitude: initialLocation.longitude === undefined ? "" : initialLocation.longitude,
            latitude: initialLocation.latitude === undefined ? "" : initialLocation.latitude
        }
        notifications = savedSettings.notifications !== false
        provider = savedSettings.provider
        draft = Object.assign({}, savedSettings.qweather || {})
        message = ""; testedDraft = ""; editing = true
    }
    Component.onCompleted: load()
    Row {
        id: footer
        visible: !root.editing
        width: parent.width; spacing: 8
        Label {
            text: (root.effectiveProvider || root.savedSettings.provider) === "qweather" ? '天气数据：<a href="https://developer.qweather.com/attribution.html">和风天气</a>' : "来源：Open-Meteo"
            textFormat: Text.RichText; linkColor: Commons.Color.accent
            onLinkActivated: function(link) { Qt.openUrlExternally(link) }
            font.pixelSize: 12; opacity: 0.7; anchors.verticalCenter: parent.verticalCenter
        }
        ActionButton { text: "天气配置"; fontPixelSize: 12; implicitHeight: 28; enabled: root.loaded && !root.busy; onClicked: root.begin() }
        ActionButton { visible: !root.loaded && !root.busy; text: "重试"; fontPixelSize: 12; implicitHeight: 28; onClicked: root.load() }
    }
    Label {
        id: loadError
        y: 34; width: parent.width
        visible: !root.editing && root.failed && root.message !== ""
        text: root.message; color: Commons.Color.urgent; font.pixelSize: 12
        wrapMode: Text.Wrap; elide: Text.ElideNone
    }
    Rectangle {
        // Overlay the weather column without contributing to the panel layout.
        y: -root.y
        width: root.width; height: root.editorHeight
        visible: root.editing
        color: Commons.Color.popups.background
        z: 10
        MouseArea { anchors.fill: parent } // Do not click through to weather/search.
        Row {
            id: header
            width: parent.width; spacing: 10
            Label { text: "天气配置"; font.pixelSize: 15; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
            ActionButton { text: "返回天气"; fontPixelSize: 12; implicitHeight: 28; enabled: !root.busy; onClicked: { root.editing = false; root.message = "" } }
        }
        Flickable {
            anchors.top: header.bottom; anchors.topMargin: 14
            anchors.bottom: feedback.top; anchors.bottomMargin: 8
            width: parent.width
            contentWidth: width; contentHeight: form.implicitHeight
            clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: form
                width: parent.width; spacing: 12
                Row {
                    spacing: 8
                    ActionButton { text: "Open-Meteo（原有）"; fontPixelSize: 12; implicitHeight: 30; emphasized: root.provider === "open-meteo"; enabled: !root.busy; onClicked: { root.provider = "open-meteo"; root.message = "" } }
                    ActionButton { text: "和风天气"; fontPixelSize: 12; implicitHeight: 30; emphasized: root.provider === "qweather"; enabled: !root.busy; onClicked: { root.provider = "qweather"; root.message = "" } }
                }
                Row {
                    spacing: 12
                    Label { text: "天气通知"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                    Rectangle {
                        width: 36; height: 20; radius: 10
                        color: root.notifications ? Commons.Color.accent : Qt.rgba(0.5, 0.5, 0.5, 0.25)
                        enabled: !root.busy
                        activeFocusOnTab: true
                        border.width: activeFocus ? 1 : 0
                        border.color: Commons.Color.popups.text
                        Accessible.role: Accessible.CheckBox
                        Accessible.name: "天气通知"
                        Accessible.checkable: true
                        Accessible.checked: root.notifications
                        function toggle() { root.notifications = !root.notifications; root.message = "" }
                        Keys.onSpacePressed: toggle()
                        Keys.onReturnPressed: toggle()
                        Rectangle { x: root.notifications ? 18 : 2; y: 2; width: 16; height: 16; radius: 8; color: Commons.Color.popups.text }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: parent.toggle() }
                    }
                    Label { text: root.notifications ? "开启" : "关闭"; font.pixelSize: 12; opacity: 0.65; anchors.verticalCenter: parent.verticalCenter }
                }
                Label { width: parent.width; visible: root.provider === "open-meteo"; text: "无需凭据，保留原有天气服务。"; font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone; opacity: 0.75 }
                Column {
                    width: parent.width; spacing: 8; visible: root.provider === "qweather"; enabled: !root.busy
                    Row {
                        spacing: 12
                        Label { text: "自定义位置"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                        Rectangle {
                            width: 36; height: 20; radius: 10
                            color: root.customLocation.enabled ? Commons.Color.accent : Qt.rgba(0.5, 0.5, 0.5, 0.25)
                            activeFocusOnTab: true
                            border.width: activeFocus ? 1 : 0; border.color: Commons.Color.popups.text
                            Accessible.role: Accessible.CheckBox; Accessible.name: "自定义位置"
                            Accessible.checkable: true; Accessible.checked: !!root.customLocation.enabled
                            function toggle() { root.customLocation = Object.assign({}, root.customLocation, {enabled: !root.customLocation.enabled}); root.message = "" }
                            Keys.onSpacePressed: toggle()
                            Keys.onReturnPressed: toggle()
                            Rectangle { x: root.customLocation.enabled ? 18 : 2; y: 2; width: 16; height: 16; radius: 8; color: Commons.Color.popups.text }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: parent.toggle() }
                        }
                    }
                    Column {
                        width: parent.width; spacing: 8; visible: !!root.customLocation.enabled
                        Repeater {
                            model: [{key: "name", title: "位置名称"}, {key: "longitude", title: "经度（-180 至 180，东经为正）"}, {key: "latitude", title: "纬度（-90 至 90，北纬为正）"}]
                            WeatherConfigField {
                                required property var modelData
                                width: parent.width; title: modelData.title
                                value: String(root.customLocation[modelData.key] === undefined ? "" : root.customLocation[modelData.key])
                                onEdited: function(value) {
                                    if (String(root.customLocation[modelData.key]) === value) return
                                    var next = Object.assign({}, root.customLocation)
                                    next[modelData.key] = value; root.customLocation = next; root.message = ""
                                }
                            }
                        }
                        Label { width: parent.width; text: "保存后，和风天气与预警始终使用此坐标，时间按本机时区显示。关闭后恢复搜索或 IP 定位。"; font.pixelSize: 12; opacity: 0.65; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    }
                }
                Column {
                    width: parent.width; spacing: 10; visible: root.provider === "qweather"; enabled: !root.busy
                    Label {
                        width: parent.width
                        text: '<a href="https://dev.qweather.com/docs/start/">注册与开通</a>  ·  <a href="https://dev.qweather.com/docs/configuration/project-and-key/">创建项目与凭据</a>  ·  <a href="https://dev.qweather.com/docs/configuration/authentication/">生成密钥</a>  ·  <a href="https://dev.qweather.com/docs/configuration/api-host/">获取 API Host</a>'
                        textFormat: Text.RichText; linkColor: Commons.Color.accent
                        onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                        font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone
                    }
                    Label {
                        width: parent.width
                        text: "注册和风帐号并完成开发者开通 → 创建项目 → 在本机生成 Ed25519 密钥，上传公钥创建 JWT 凭据。将控制台中的 ID、API Host 和本机私钥路径填入下方，测试后保存。"
                        font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone; opacity: 0.75
                    }
                    Label {
                        width: parent.width
                        text: '请求频率会随天气自动调整：无雨雪时每 10 分钟更新，雨雪时每 5 分钟更新，预警每 15 分钟查询。锁屏、待机和休眠时暂停，恢复后立即更新；多屏共享缓存，通知不额外请求接口。<br><br>单机日常使用通常够用：天气与基础服务每月前 5 万次请求免费。即使全天按雨雪频率运行，31 天约 3.87 万次定时请求；日常有无雨雪和暂停时段，用量通常更低。搜索、唤醒及其他应用会额外占用额度，超额按量计费。<a href="https://dev.qweather.com/docs/finance/pricing/">查看额度与价格</a>'
                        textFormat: Text.RichText; linkColor: Commons.Color.accent
                        onLinkActivated: function(link) { Qt.openUrlExternally(link) }
                        font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone; opacity: 0.75
                    }
                    Repeater {
                        model: [
                            {key: "api_host", title: "API Host"},
                            {key: "developer_id", title: "开发者 ID（iss）"},
                            {key: "project_id", title: "项目 ID（sub）"},
                            {key: "credential_id", title: "凭据 ID（kid）"},
                            {key: "private_key_path", title: "Ed25519 私钥文件绝对路径"}
                        ]
                        WeatherConfigField {
                            required property var modelData
                            width: parent.width
                            title: modelData.title
                            value: root.draft[modelData.key] || ""
                            onEdited: function(value) {
                                if ((root.draft[modelData.key] || "") === value) return
                                var next = Object.assign({}, root.draft)
                                next[modelData.key] = value
                                root.draft = next
                                root.testedDraft = ""; root.message = ""
                            }
                        }
                    }
                    Label { width: parent.width; text: "私钥只保存在本机，不要上传或分享。测试将查询北京天气。"; wrapMode: Text.Wrap; elide: Text.ElideNone; font.pixelSize: 12; opacity: 0.65 }
                }
            }
        }
        Label {
            id: feedback
            anchors.bottom: actions.top; anchors.bottomMargin: 10
            width: parent.width; height: Math.max(32, implicitHeight)
            text: root.message || (root.provider === "qweather" ? (root.connectionUnchanged ? "保存后生效。" : "测试通过后即可保存。") : "保存后切换至 Open-Meteo。")
            color: root.failed ? Commons.Color.urgent : Commons.Color.popups.text
            wrapMode: Text.Wrap; elide: Text.ElideNone; font.pixelSize: 12
        }
        Row {
            id: actions
            anchors.bottom: parent.bottom
            spacing: 8
            ActionButton { text: root.busy ? "正在连接…" : "测试连接"; fontPixelSize: 12; implicitHeight: 30; visible: root.provider === "qweather"; enabled: !root.busy; onClicked: root.run("test") }
            ActionButton { text: "保存并使用"; fontPixelSize: 12; implicitHeight: 30; emphasized: true; enabled: !root.busy && (root.provider === "open-meteo" || root.connectionUnchanged || root.testedDraft === root.connectionJson); onClicked: root.run("save") }
            ActionButton { text: "取消"; fontPixelSize: 12; implicitHeight: 30; enabled: !root.busy; onClicked: { root.editing = false; root.message = "" } }
        }
    }
    Process {
        id: process
        property string action: ""
        property string payload: ""
        stdinEnabled: true
        onStarted: { if (action !== "load") write(payload + "\n") }
        stdout: StdioCollector { id: output; waitForEnd: true }
        onExited: function(code) {
            var result
            try { result = JSON.parse(output.text) }
            catch (e) { result = {ok: false, error: "无法读取天气配置，请重试"} }
            root.failed = code !== 0 || !result.ok
            root.message = root.failed ? result.error || "操作失败，请重试" : result.message || ""
            if (root.failed) { root.testedDraft = ""; return }
            if (action === "test") { var tested = JSON.parse(payload); root.testedDraft = JSON.stringify({provider: tested.provider, qweather: tested.qweather}) }
            else {
                var changed = JSON.stringify(root.savedSettings) !== JSON.stringify(result.settings)
                root.savedSettings = result.settings
                root.loaded = true
                if (action === "save") root.editing = false
                if (changed) root.configurationChanged()
            }
        }
    }
}
