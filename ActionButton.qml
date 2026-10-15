// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import qs.Commons as Commons
Rectangle {
    id: root
    property string text: ""
    property bool emphasized: false
    property int fontPixelSize: 16
    signal clicked()
    implicitWidth: label.implicitWidth + 24
    implicitHeight: 36
    radius: 6
    color: emphasized ? Commons.Color.accent : mouse.containsMouse || activeFocus ? Qt.rgba(0.5, 0.5, 0.5, 0.18) : Qt.rgba(0.5, 0.5, 0.5, 0.08)
    opacity: enabled ? 1 : 0.35
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    Label { id: label; anchors.centerIn: parent; text: root.text; font.pixelSize: root.fontPixelSize; color: root.emphasized ? Commons.Color.background : Commons.Color.popups.text }
    MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.clicked() }
}
