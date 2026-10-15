// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart
import QtQuick
import Quickshell.Io
import qs.Commons as Commons

Column {
    id: root
    property string title: ""
    property string value: ""
    signal edited(string value)
    spacing: 5
    Label { width: parent.width; text: root.title; font.pixelSize: 12; opacity: 0.8 }
    Rectangle {
        width: parent.width; height: 32; radius: 6
        color: Qt.rgba(0.5, 0.5, 0.5, 0.09)
        border.width: 1
        border.color: input.activeFocus ? Commons.Color.accent : "transparent"
        SafeCityInput {
            id: input
            anchors.fill: parent; anchors.margins: 7
            text: root.value
            maximumLength: 4096
            color: Commons.Color.popups.text
            selectionColor: Commons.Color.accent
            selectedTextColor: Commons.Color.background
            font.family: Commons.Style.font.family; font.pixelSize: 12
            onTextChanged: root.edited(text)
            onPasteRequested: {
                if (paste.running) return
                paste.generation = editGeneration
                paste.running = true
            }
        }
    }
    Label { width: parent.width; visible: pasteError !== ""; text: pasteError; color: Commons.Color.urgent; wrapMode: Text.Wrap; elide: Text.ElideNone }
    property string pasteError: ""
    Process {
        id: paste
        property int generation: 0
        command: ["python3", decodeURIComponent(String(Qt.resolvedUrl("clipboard.py")).replace(/^file:\/\//, ""))]
        stdout: StdioCollector { id: output; waitForEnd: true }
        onExited: function(code) {
            if (!root.visible || !input.activeFocus || generation !== input.editGeneration) return
            var result
            try { result = JSON.parse(output.text) }
            catch (e) { result = {ok: false, error: "无法读取剪贴板"} }
            root.pasteError = result.ok ? "" : result.error
            if (code === 0 && result.ok) input.replaceSelection(result.text)
        }
    }
}
