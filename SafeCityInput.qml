// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart
pragma ComponentBehavior: Bound
import QtQuick

// Use native editing for IME composition while focused. Inactive fields stay
// read-only to avoid clipboard probes from every hidden monitor instance.
TextInput {
    id: root
    readOnly: !activeFocus
    selectByMouse: true
    clip: true
    maximumLength: 120
    property int editGeneration: 0
    signal pasteRequested()
    signal searchKeyPressed(var event)
    onTextChanged: editGeneration++
    onActiveFocusChanged: editGeneration++
    onCursorPositionChanged: editGeneration++
    onSelectionStartChanged: editGeneration++
    onSelectionEndChanged: editGeneration++

    cursorDelegate: Rectangle {
        width: 1
        color: root.color
        visible: root.activeFocus
    }

    function replaceSelection(value) {
        var start = selectionStart
        var end = selectionEnd
        var remaining = maximumLength - (text.length - (end - start))
        var addition = String(value).replace(/[\r\n\t]+/g, " ").slice(0, Math.max(0, remaining))
        text = text.slice(0, start) + addition + text.slice(end)
        cursorPosition = start + addition.length
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.MiddleButton
        onPressed: function(mouse) { mouse.accepted = true }
    }

    Keys.onPressed: function(event) {
        if (root.inputMethodComposing) { event.accepted = false; return }
        root.searchKeyPressed(event)
        if (event.accepted) return
        var ctrl = !!(event.modifiers & Qt.ControlModifier)
        if ((ctrl && event.key === Qt.Key_V) || ((event.modifiers & Qt.ShiftModifier) && event.key === Qt.Key_Insert)) {
            root.pasteRequested()
            event.accepted = true
        }
    }
}
