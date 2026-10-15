// SPDX-License-Identifier: GPL-3.0-only
import QtQuick
import QtTest
import ".." as Days

TestCase {
    name: "SafeCityInput"
    width: 400
    height: 60
    when: windowShown
    Days.SafeCityInput { id: input; width: 400; height: 44 }
    SignalSpy { id: pasteSpy; target: input; signalName: "pasteRequested" }
    function init() { input.text = ""; input.forceActiveFocus(); pasteSpy.clear() }
    function test_typing_editing() {
        keyClick(Qt.Key_S); keyClick(Qt.Key_H); keyClick(Qt.Key_A)
        compare(input.text, "sha")
        keyClick(Qt.Key_Left); keyClick(Qt.Key_Backspace)
        compare(input.text, "sa")
        keyClick(Qt.Key_Delete); compare(input.text, "s")
        keyClick(Qt.Key_A, Qt.ControlModifier); keyClick(Qt.Key_B)
        compare(input.text, "b")
        verify(!input.readOnly)
    }
    function test_paste_is_explicit() {
        keyClick(Qt.Key_V, Qt.ControlModifier); compare(pasteSpy.count, 1)
        keyClick(Qt.Key_Insert, Qt.ShiftModifier); compare(pasteSpy.count, 2)
        compare(input.text, "")
        mouseClick(input, 10, 10, Qt.MiddleButton); compare(pasteSpy.count, 2)
        verify(!input.readOnly)
    }
    function test_selection_and_limit() {
        input.text = "shanghai"; input.select(0, 5); input.replaceSelection("上海")
        compare(input.text, "上海hai")
        input.selectAll(); input.replaceSelection("x".repeat(200))
        compare(input.text.length, 120)
        input.replaceSelection("y"); compare(input.text.length, 120)
        input.selectAll(); input.replaceSelection("bei\njing")
        compare(input.text, "bei jing")
    }
    function test_generation_invalidates_pending_paste() {
        var generation = input.editGeneration
        keyClick(Qt.Key_A); verify(input.editGeneration > generation)
        generation = input.editGeneration
        keyClick(Qt.Key_Left); verify(input.editGeneration > generation)
        generation = input.editGeneration
        input.focus = false; verify(input.editGeneration > generation)
    }
}
