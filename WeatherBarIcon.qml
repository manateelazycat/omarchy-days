// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import qs.Commons

Item {
    id: root

    property string icon: "unknown"
    property string temperature: ""
    property color color: "black"
    property bool vertical: false
    readonly property real iconExtent: Style.bar.iconCanvas

    implicitWidth: root.vertical
        ? Math.max(iconExtent, root.temperature !== "" ? horizontalText.implicitWidth : 0)
        : Math.max(iconExtent, row.implicitWidth)
    implicitHeight: root.vertical
        ? Math.max(iconExtent, column.implicitHeight)
        : iconExtent

    Row {
        id: row
        visible: !root.vertical
        anchors.centerIn: parent
        spacing: 4

        WeatherIcon {
            width: root.iconExtent
            height: root.iconExtent
            icon: root.icon
            ink: root.color
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            id: horizontalText
            visible: root.temperature !== ""
            text: root.temperature
            color: root.color
            font.family: Style.font.family
            font.pixelSize: Style.bar.iconFont
            renderType: Text.NativeRendering
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Column {
        id: column
        visible: root.vertical
        anchors.centerIn: parent
        spacing: 2

        WeatherIcon {
            width: root.iconExtent
            height: root.iconExtent
            icon: root.icon
            ink: root.color
        }
        Text {
            visible: root.temperature !== "" && root.vertical
            text: root.temperature
            color: root.color
            font.family: Style.font.family
            font.pixelSize: Style.bar.iconFont
            renderType: Text.NativeRendering
        }
    }
}
