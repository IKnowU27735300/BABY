import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Window {
    id: cameraPreviewRoot
    title: "BABY — Camera Preview"
    visible: babyController ? babyController.cameraPreviewVisible : false
    width: 460
    height: 360
    minimumWidth: 280
    minimumHeight: 220
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"

    property bool frameReceived: false
    property bool isMaximizedState: false
    property bool isMinimizing: false
    property int prevWidth: 460
    property int prevHeight: 360
    property int prevX: 100
    property int prevY: 100

    x: jiggle.baseX + jiggle.offsetX
    y: jiggle.baseY + jiggle.offsetY

    JiggleHelper { id: jiggle; target: cameraPreviewRoot }

    function minimizeToIsland() {
        if (isMinimizing) return
        isMinimizing = true

        // Capture current position and size
        var startX = cameraPreviewRoot.x
        var startY = cameraPreviewRoot.y
        var startW = cameraPreviewRoot.width
        var startH = cameraPreviewRoot.height

        // Target: island position (center of island)
        var islandCx = babyController ? babyController.islandX + 60 : Screen.width / 2
        var islandCy = babyController ? babyController.islandY + 18 : 12

        // Animate position toward island
        minimizeAnimX.from = startX
        minimizeAnimX.to = islandCx - 40
        minimizeAnimY.from = startY
        minimizeAnimY.to = islandCy - 10
        minimizeAnimW.from = startW
        minimizeAnimW.to = 80
        minimizeAnimH.from = startH
        minimizeAnimH.to = 36

        minimizeGroup.start()
    }

    ParallelAnimation {
        id: minimizeGroup
        NumberAnimation { id: minimizeAnimX; target: cameraPreviewRoot; property: "x"; duration: 320; easing.type: Easing.InBack }
        NumberAnimation { id: minimizeAnimY; target: cameraPreviewRoot; property: "y"; duration: 320; easing.type: Easing.InBack }
        NumberAnimation { id: minimizeAnimW; target: cameraPreviewRoot; property: "width"; duration: 320; easing.type: Easing.InBack }
        NumberAnimation { id: minimizeAnimH; target: cameraPreviewRoot; property: "height"; duration: 320; easing.type: Easing.InBack }
        NumberAnimation { target: previewBg; property: "opacity"; from: 1.0; to: 0.0; duration: 280; easing.type: Easing.InCubic }
        onFinished: {
            cameraPreviewRoot.isMinimizing = false
            previewBg.opacity = 1
            if (babyController) babyController.minimizeCameraPreview()
        }
    }

    // ── Outer container with glassmorphism look ────────────────────────────────
    Rectangle {
        id: previewBg
        anchors.fill: parent
        radius: 16
        color: "#0F0F13"
        border.color: Qt.rgba(1, 1, 1, 0.12)
        border.width: 1

        // Subtle top-gradient shine
        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 60
            radius: 16
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1,1,1,0.06) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        // ── Drag handle (full header area) — jiggly physics on drop ────────────
        MouseArea {
            id: dragArea
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 44
            cursorShape: Qt.SizeAllCursor
            property point clickPos: "0,0"
            onPressed: {
                clickPos = Qt.point(mouse.x, mouse.y)
                if (!cameraPreviewRoot.isMaximizedState) jiggle.beginDrag()
            }
            onPositionChanged: {
                if (!cameraPreviewRoot.isMaximizedState) {
                    jiggle.dragTo(mouse.x - clickPos.x, mouse.y - clickPos.y)
                }
            }
            onReleased: jiggle.release()
        }

        // ── Window controls (top-right) ────────────────────────────────────────
        Row {
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: 10
            anchors.rightMargin: 10
            spacing: 6
            z: 30

            // Maximise / restore
            Rectangle {
                width: 22; height: 22; radius: 11
                color: maxMouse.containsMouse ? "#44444F" : "#2A2A35"
                Behavior on color { ColorAnimation { duration: 120 } }
                Text { anchors.centerIn: parent; text: cameraPreviewRoot.isMaximizedState ? "◱" : "□"; color: "#CCC"; font.pixelSize: 11 }
                MouseArea {
                    id: maxMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (!cameraPreviewRoot.isMaximizedState) {
                            cameraPreviewRoot.prevWidth  = cameraPreviewRoot.width
                            cameraPreviewRoot.prevHeight = cameraPreviewRoot.height
                            cameraPreviewRoot.prevX = cameraPreviewRoot.x
                            cameraPreviewRoot.prevY = cameraPreviewRoot.y
                            jiggle.snapTo(0, 0)
                            cameraPreviewRoot.width  = Screen.width
                            cameraPreviewRoot.height = Screen.height
                            cameraPreviewRoot.isMaximizedState = true
                        } else {
                            jiggle.snapTo(cameraPreviewRoot.prevX, cameraPreviewRoot.prevY)
                            cameraPreviewRoot.width  = cameraPreviewRoot.prevWidth
                            cameraPreviewRoot.height = cameraPreviewRoot.prevHeight
                            cameraPreviewRoot.isMaximizedState = false
                        }
                    }
                }
            }

            // Minimize (shrink to island)
            Rectangle {
                width: 22; height: 22; radius: 11
                color: minMouse.containsMouse ? "#C8C83B" : "#FFD700"
                Behavior on color { ColorAnimation { duration: 120 } }
                Text { anchors.centerIn: parent; text: "—"; color: "#1A1A1E"; font.pixelSize: 11; font.bold: true }
                MouseArea {
                    id: minMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: cameraPreviewRoot.minimizeToIsland()
                }
            }

            // Close
            Rectangle {
                width: 22; height: 22; radius: 11
                color: closeMouse.containsMouse ? "#FF5555" : "#FF3B30"
                Behavior on color { ColorAnimation { duration: 120 } }
                Text { anchors.centerIn: parent; text: "✕"; color: "white"; font.pixelSize: 11; font.bold: true }
                MouseArea {
                    id: closeMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { if (babyController) babyController.setCameraPreviewVisible(false) }
                }
            }
        }

        // ── Title ──────────────────────────────────────────────────────────────
        Row {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.topMargin: 12
            anchors.leftMargin: 14
            spacing: 6
            z: 10

            Rectangle {
                width: 8; height: 8; radius: 4
                color: cameraPreviewRoot.frameReceived ? "#30D158" : "#FF9F0A"
                Behavior on color { ColorAnimation { duration: 400 } }
                anchors.verticalCenter: parent.verticalCenter
                SequentialAnimation on opacity {
                    running: !cameraPreviewRoot.frameReceived
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.3; duration: 600 }
                    NumberAnimation { to: 1.0; duration: 600 }
                }
            }
            Text {
                text: "📷  Camera Preview"
                color: "#B8B8FF"
                font.pixelSize: 13
                font.bold: true
                font.letterSpacing: 0.3
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        // ── Camera feed area ───────────────────────────────────────────────────
        Rectangle {
            id: previewArea
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.topMargin: 44
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            anchors.bottomMargin: 10
            color: "#070709"
            radius: 10
            clip: true
            border.color: Qt.rgba(1, 1, 1, 0.06)

            // Live camera image — rendered from data URL
            Image {
                id: cameraImage
                anchors.fill: parent
                anchors.margins: 1
                fillMode: Image.PreserveAspectFit
                smooth: true
                cache: false
                asynchronous: true
                opacity: cameraPreviewRoot.frameReceived ? 1.0 : 0.0
                Behavior on opacity { NumberAnimation { duration: 300 } }
            }

            // ── Loading / error overlay ────────────────────────────────────────
            Item {
                id: loadingOverlay
                anchors.fill: parent
                visible: !cameraPreviewRoot.frameReceived

                // Spinner ring
                Item {
                    id: spinRing
                    anchors.centerIn: parent
                    width: 48; height: 48
                    anchors.verticalCenterOffset: -20

                    Rectangle {
                        anchors.fill: parent
                        radius: width / 2
                        color: "transparent"
                        border.width: 3
                        border.color: Qt.rgba(0.55, 0.55, 1, 0.25)
                    }

                    Rectangle {
                        id: spinArc
                        anchors.fill: parent
                        radius: width / 2
                        color: "transparent"
                        border.width: 3
                        border.color: "#8B5CF6"
                        // Fake arc effect via clipping half
                        Rectangle {
                            anchors.right: parent.right
                            anchors.top: parent.top
                            width: parent.width / 2
                            height: parent.height
                            color: "#070709"
                        }
                        RotationAnimator on rotation {
                            loops: Animation.Infinite
                            from: 0; to: 360; duration: 900
                        }
                    }
                }

                Text {
                    id: statusText
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: spinRing.bottom
                    anchors.topMargin: 14
                    text: "Initializing camera…"
                    color: "#888"
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    width: parent.width - 30
                }
            }
        }

        // ── Camera switch button (bottom center) ─────────────────────────────
        Rectangle {
            id: switchBtn
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 18
            anchors.horizontalCenter: parent.horizontalCenter
            width: 40; height: 40; radius: 20
            color: switchMouse.containsMouse ? "#50506A" : "#3A3A50"
            border.color: Qt.rgba(1, 1, 1, 0.15)
            border.width: 1
            z: 30
            opacity: cameraPreviewRoot.frameReceived ? 1.0 : 0.0
            Behavior on opacity { NumberAnimation { duration: 200 } }

            Text {
                anchors.centerIn: parent
                text: "⟳"
                color: "#B8B8FF"
                font.pixelSize: 20
                font.bold: true
            }

            MouseArea {
                id: switchMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (babyController) {
                        cameraPreviewRoot.frameReceived = false
                        statusText.text = "Switching camera…"
                        babyController.switchCamera()
                    }
                }
            }

            // Tooltip
            ToolTip {
                visible: switchMouse.containsMouse
                text: "Switch Camera"
                delay: 600
            }
        }

        // ── Resize handles ─────────────────────────────────────────────────────
        MouseArea {
            anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
            anchors.topMargin: 20; anchors.bottomMargin: 20; width: 8
            cursorShape: Qt.SizeHorCursor
            property point clickPos: "0,0"
            onPressed: clickPos = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                var nw = cameraPreviewRoot.width + (mouse.x - clickPos.x)
                if (nw >= cameraPreviewRoot.minimumWidth) cameraPreviewRoot.width = nw
            }
        }
        MouseArea {
            anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin: 20; anchors.rightMargin: 20; height: 8
            cursorShape: Qt.SizeVerCursor
            property point clickPos: "0,0"
            onPressed: clickPos = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                var nh = cameraPreviewRoot.height + (mouse.y - clickPos.y)
                if (nh >= cameraPreviewRoot.minimumHeight) cameraPreviewRoot.height = nh
            }
        }
        MouseArea {
            id: cornerGrip
            anchors.right: parent.right; anchors.bottom: parent.bottom
            width: 18; height: 18; cursorShape: Qt.SizeFDiagCursor; z: 30
            property point clickPos: "0,0"
            onPressed: clickPos = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                var nw = cameraPreviewRoot.width  + (mouse.x - clickPos.x)
                var nh = cameraPreviewRoot.height + (mouse.y - clickPos.y)
                if (nw >= cameraPreviewRoot.minimumWidth)  cameraPreviewRoot.width  = nw
                if (nh >= cameraPreviewRoot.minimumHeight) cameraPreviewRoot.height = nh
            }
            Text { anchors.centerIn: parent; text: "⇲"; color: "#7C7CFF"; font.pixelSize: 12 }
        }
    }

    // ── Timeout timer ──────────────────────────────────────────────────────────
    Timer {
        id: cameraTimeoutTimer
        interval: 10000
        running: cameraPreviewRoot.visible && !cameraPreviewRoot.frameReceived
        repeat: false
        onTriggered: {
            if (!cameraPreviewRoot.frameReceived) {
                statusText.text = "❌ Camera did not start in time.\nCheck if another app is using it."
            }
        }
    }

    // ── React to incoming frames ───────────────────────────────────────────────
    Connections {
        target: babyController
        enabled: babyController !== null
        function onCameraFrameChanged(dataUrl) {
            if (dataUrl && dataUrl.length > 10) {
                cameraImage.source = dataUrl
                if (!cameraPreviewRoot.frameReceived) {
                    cameraPreviewRoot.frameReceived = true
                    cameraTimeoutTimer.stop()
                }
            }
        }
        function onCameraPreviewError(message) {
            statusText.text = "❌ " + message
            cameraPreviewRoot.frameReceived = false
            cameraTimeoutTimer.stop()
        }
    }

    onVisibleChanged: {
        if (visible) {
            // Reset size/position if coming back from minimize
            if (width < minimumWidth || height < minimumHeight) {
                width = prevWidth
                height = prevHeight
                x = prevX
                y = prevY
                isMaximizedState = false
            }
            // Only reset frame state if camera worker was fully stopped (close case)
            // If minimized, worker is still running and frames keep coming
            if (!babyController || !babyController.cameraMinimized) {
                frameReceived = false
                statusText.text = "Initializing camera…"
                cameraImage.source = ""
                cameraTimeoutTimer.restart()
            }
            previewBg.opacity = 0
            windowFadeIn.start()
            jiggle.popIn()
        } else {
            jiggle.stopWobble()
        }
    }

    NumberAnimation {
        id: windowFadeIn
        target: previewBg
        property: "opacity"
        to: 1
        duration: 160
        easing.type: Easing.OutCubic
    }
}














