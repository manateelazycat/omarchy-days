// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart

import QtQuick
import qs.Commons

Rectangle {
    id: root
    property string text: ""
    property bool emphasized: false
    signal clicked()
    implicitWidth: label.implicitWidth + 24
    implicitHeight: 36
    radius: 6
    color: emphasized ? Color.accent : mouse.containsMouse || activeFocus ? Qt.rgba(0.5, 0.5, 0.5, 0.18) : Qt.rgba(0.5, 0.5, 0.5, 0.08)
    opacity: enabled ? 1 : 0.35
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    Label { id: label; anchors.centerIn: parent; text: root.text; color: root.emphasized ? Color.background : Color.popups.text }
    MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.clicked() }
}
