// SPDX-License-Identifier: GPL-3.0-only
import QtQuick
import qs.Commons as Commons

Column {
    id: root
    property var alertData: null
    property string error: ""
    property bool expanded: false
    readonly property color signalColor: alerts.length ? (({blue: "#7aa2f7", yellow: "#e0c36c", amber: "#e0b16c", orange: "#e89c61", red: "#ef717a", purple: "#bc93dd"})[alerts[0].color] || Commons.Color.accent) : Commons.Color.popups.text
    property double clock: Date.now()
    readonly property var alerts: alertData && alertData.alerts ? alertData.alerts.filter(function(a) {
        return Date.parse(a.effectiveTime) <= root.clock && Date.parse(a.expireTime) > root.clock
    }) : []
    readonly property bool hasContent: alerts.length > 0 || error !== ""
    spacing: 6
    onAlertDataChanged: clock = Date.now()
    Timer { interval: 1000; running: !!root.alertData; repeat: true; onTriggered: root.clock = Date.now() }
    Label {
        width: parent.width
        visible: root.error !== ""
        text: root.alerts.length ? "预警更新失败，显示上次信息" : "预警暂不可用"
        font.pixelSize: 12; color: Commons.Color.urgent
    }
    Repeater {
        model: root.alerts
        Rectangle {
            id: card
            required property var modelData
            readonly property color signalColor: ({blue: "#7aa2f7", yellow: "#e0c36c", amber: "#e0b16c", orange: "#e89c61", red: "#ef717a", purple: "#bc93dd"})[modelData.color] || Commons.Color.accent
            width: root.width; height: content.implicitHeight + 16; radius: 6
            color: Qt.rgba(signalColor.r, signalColor.g, signalColor.b, 0.12)
            Rectangle { x: 0; y: 7; width: 3; height: parent.height - 14; radius: 1; color: card.signalColor }
            Column {
                id: content
                x: 10; y: 8; width: parent.width - 20; spacing: 7
                Label {
                    width: parent.width; text: card.modelData.headline
                    textFormat: Text.PlainText; font.pixelSize: 14; font.bold: true
                    wrapMode: Text.Wrap; elide: Text.ElideNone
                }
                Column {
                    width: parent.width; spacing: 7
                    Label { width: parent.width; text: card.modelData.senderName + " · " + card.modelData.issuedTime.slice(5, 16).replace("T", " "); textFormat: Text.PlainText; font.pixelSize: 12; opacity: 0.7; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    Label { width: parent.width; text: card.modelData.description; textFormat: Text.PlainText; font.pixelSize: 13; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    Label { width: parent.width; visible: text !== ""; text: card.modelData.instruction; textFormat: Text.PlainText; font.pixelSize: 13; wrapMode: Text.Wrap; elide: Text.ElideNone }
                }
            }
        }
    }
    Label {
        width: parent.width
        visible: root.alerts.length > 0
        text: root.alertData ? (root.alertData.attributions || []).join(" · ") : ""
        textFormat: Text.PlainText; font.pixelSize: 11; opacity: 0.6
        wrapMode: Text.Wrap; elide: Text.ElideNone
    }
}
