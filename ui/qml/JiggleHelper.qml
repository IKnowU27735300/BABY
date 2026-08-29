// ui/qml/JiggleHelper.qml
// "Jiggly physics" for Baby's frameless windows: when a window is dropped
// after dragging it wobbles like jelly and settles; when it opens it pops in
// with a wobble. Deliberately NOT used by the Dynamic Island (which stays
// crisp). The host window binds:
//
//   x: jiggle.baseX + jiggle.offsetX
//   y: jiggle.baseY + jiggle.offsetY
//
// and calls beginDrag() / dragTo(dx, dy) / release() from its drag MouseArea,
// snapTo(x, y) for programmatic moves (e.g. maximize/restore), and popIn()
// from onVisibleChanged when the window opens.
//
// Root is an invisible Item (not QtObject) so the animation child can be
// declared directly — QtObject has no default `data` property on this Qt.

import QtQuick 2.15
import QtQuick.Window 2.15

Item {
    id: jiggle
    width: 0
    height: 0
    visible: false

    property Window target: null
    property bool isEnabled: true

    // Settled position — what the window returns to when the wobble ends.
    property real baseX: 0
    property real baseY: 0

    // Live wobble offsets, driven by `phase` (0..1). At phase 1 both are 0.
    property real offsetX: 0
    property real offsetY: 0

    // Wobble shape: two X oscillations, 1.5 Y oscillations, amplitude
    // collapsing quadratically → a gelatinous settle.
    property real phase: 0
    property real ampX: 10
    property real ampY: 6
    property int wobbleDuration: 460
    property real popAmp: 16
    property int popDuration: 430

    property bool _dragging: false

    // Re-anchor the settled position on whatever the window currently shows.
    function sync() {
        if (!target) return
        baseX = target.x - offsetX
        baseY = target.y - offsetY
    }

    function beginDrag() {
        if (!isEnabled) return
        _dragging = true
        wobble.stop()
        offsetX = 0
        offsetY = 0
        sync()
    }

    function dragTo(dx, dy) {
        if (!_dragging) return
        baseX += dx
        baseY += dy
    }

    function release() {
        if (!_dragging) return
        _dragging = false
        if (!isEnabled) return
        ampX = 10
        ampY = 6
        wobble.duration = wobbleDuration
        phase = 0
        wobble.restart()
    }

    // Programmatic move (maximize/restore): no wobble, hard snap.
    function snapTo(nx, ny) {
        wobble.stop()
        _dragging = false
        offsetX = 0
        offsetY = 0
        phase = 1
        baseX = nx
        baseY = ny
    }

    // Opening wobble: keep the current position, wobble with pop amplitude.
    function popIn() {
        if (!isEnabled) return
        _dragging = false
        baseX = target.x - offsetX
        baseY = target.y - offsetY
        ampX = popAmp
        ampY = popAmp * 0.6
        wobble.duration = popDuration
        phase = 0
        wobble.restart()
    }

    // Kill any in-flight wobble and land cleanly (e.g. window hidden mid-wobble).
    function stopWobble() {
        wobble.stop()
        _dragging = false
        offsetX = 0
        offsetY = 0
        phase = 1
    }

    NumberAnimation {
        id: wobble
        target: jiggle
        property: "phase"
        from: 0
        to: 1
        duration: jiggle.wobbleDuration
        easing.type: Easing.Linear
    }

    onPhaseChanged: {
        if (_dragging) return
        var d = 1 - phase
        offsetX = Math.sin(phase * Math.PI * 4) * ampX * d * d
        offsetY = Math.cos(phase * Math.PI * 3) * ampY * d * d
    }
}














