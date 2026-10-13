// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Andy Stewart
pragma ComponentBehavior: Bound
import QtQuick

// Keep Qt's clipboard probe and native paste paths disabled at all times.
// Direct key text is sufficient for English/pinyin city searches. Chinese
// names can be pasted through the bounded, asynchronous helper instead.
TextInput {
    id: root
    readOnly: true
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

    function deleteText(backward, word) {
        if (selectionStart !== selectionEnd) { replaceSelection(""); return }
        var start = cursorPosition
        var end = cursorPosition
        if (backward) {
            start = word ? text.slice(0, start).replace(/\s*\S+\s*$/, "").length : Math.max(0, start - 1)
            if (!word && start > 0 && /[\uDC00-\uDFFF]/.test(text.charAt(start))) start--
        } else {
            end = word ? end + (text.slice(end).match(/^\s*\S+\s*/) || [""])[0].length : Math.min(text.length, end + 1)
            if (!word && end < text.length && /[\uD800-\uDBFF]/.test(text.charAt(end - 1))) end++
        }
        select(start, end)
        replaceSelection("")
    }

    Keys.onPressed: function(event) {
        root.searchKeyPressed(event)
        if (event.accepted) return
        var ctrl = !!(event.modifiers & Qt.ControlModifier)
        if ((ctrl && event.key === Qt.Key_V) || ((event.modifiers & Qt.ShiftModifier) && event.key === Qt.Key_Insert)) {
            root.pasteRequested()
            event.accepted = true
        } else if (ctrl && event.key === Qt.Key_X) {
            root.copy()
            root.replaceSelection("")
            event.accepted = true
        } else if (event.key === Qt.Key_Backspace || event.key === Qt.Key_Delete) {
            root.deleteText(event.key === Qt.Key_Backspace, ctrl)
            event.accepted = true
        } else if (!ctrl && !(event.modifiers & (Qt.AltModifier | Qt.MetaModifier)) && event.text && !/[\x00-\x1f\x7f]/.test(event.text)) {
            root.replaceSelection(event.text)
            event.accepted = true
        }
    }
}
