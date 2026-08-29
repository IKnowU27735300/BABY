import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Window {
    id: screenSharePreviewRoot
    title: "BABY Screen Share Preview"
    visible: babyController ? babyController.screenSharePreviewVisible : false
    width: 720
    height: 520
    minimumWidth: 400
    minimumHeight: 300
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"

    property string currentScreenshot: ""
    property int updateInterval: 1000  // Update every 1 second
    property bool isMaximizedState: false
    property bool isMinimizing: false
    property int prevWidth: 720
    property int prevHeight: 520
    property int prevX: 100
    property int prevY: 100

    x: jiggle.baseX + jiggle.offsetX
    y: jiggle.baseY + jiggle.offsetY

    JiggleHelper { id: jiggle; target: screenSharePreviewRoot }

    function minimizeToIsland() {
        if (isMinimizing) return
        isMinimizing = true
        var startX = screenSharePreviewRoot.x
        var startY = screenSharePreviewRoot.y
        var startW = screenSharePreviewRoot.width
        var startH = screenSharePreviewRoot.height
        var islandCx = babyController ? babyController.islandX + 60 : Screen.width / 2
        var islandCy = babyController ? babyController.islandY + 18 : 12
        minimizeAnimX.from = startX; minimizeAnimX.to = islandCx - 40
        minimizeAnimY.from = startY; minimizeAnimY.to = islandCy - 10
        minimizeAnimW.from = startW; minimizeAnimW.to = 80
        minimizeAnimH.from = startH; minimizeAnimH.to = 36
        minimizeGroup.start()
    }

    ParallelAnimation {
        id: minimizeGroup
        NumberAnimation { id: minimizeAnimX; target: screenSharePreviewRoot; property: "x"; duration: 320; easing.type: Easing.InBack }
        NumberAnimation { id: minimizeAnimY; target: screenSharePreviewRoot; property: "y"; duration: 320; easing.type: Easing.InBack }
        NumberAnimation { id: minimizeAnimW; target: screenSharePreviewRoot; property: "width"; duration: 320; easing.type: Easing.InBack }
        NumberAnimation { id: minimizeAnimH; target: screenSharePreviewRoot; property: "height"; duration: 320; easing.type: Easing.InBack }
        NumberAnimation { target: previewBg; property: "opacity"; from: 1.0; to: 0.0; duration: 280; easing.type: Easing.InCubic }
        onFinished: {
            screenSharePreviewRoot.isMinimizing = false
            previewBg.opacity = 1
            if (babyController) babyController.setScreenSharePreviewVisible(false)
        }
    }

    Timer {
        id: screenshotUpdateTimer
        interval: screenSharePreviewRoot.updateInterval
        running: screenSharePreviewRoot.visible
        repeat: true
        onTriggered: {
            if (babyController) {
                // screenshot update ping
            }
        }
    }

    Rectangle {
        id: previewBg
        anchors.fill: parent
        color: "#1A1A1E"
        radius: 12
        border.color: Qt.rgba(1,1,1, 0.15)
        border.width: 1

        // Header Drag Area — jiggly physics on drop
        MouseArea {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 40
            cursorShape: Qt.SizeAllCursor
            property point clickPos: "0,0"
            onPressed: {
                clickPos = Qt.point(mouse.x, mouse.y)
                if (!screenSharePreviewRoot.isMaximizedState) jiggle.beginDrag()
            }
            onPositionChanged: {
                if (!screenSharePreviewRoot.isMaximizedState) {
                    jiggle.dragTo(mouse.x - clickPos.x, mouse.y - clickPos.y)
                }
            }
            onReleased: jiggle.release()
        }

        // Window Controls Container (Maximize/Restore & Close)
        Row {
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: 8
            anchors.rightMargin: 8
            spacing: 6
            z: 20

            // Maximize / Restore Toggle Button
            Rectangle {
                width: 22
                height: 22
                radius: 11
                color: maxMouse.pressed ? "#3B3B48" : (maxMouse.containsMouse ? "#4B4B58" : "#2C2C35")
                Behavior on color { ColorAnimation { duration: 150 } }

                MouseArea {
                    id: maxMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (!screenSharePreviewRoot.isMaximizedState) {
                            screenSharePreviewRoot.prevWidth = screenSharePreviewRoot.width
                            screenSharePreviewRoot.prevHeight = screenSharePreviewRoot.height
                            screenSharePreviewRoot.prevX = screenSharePreviewRoot.x
                            screenSharePreviewRoot.prevY = screenSharePreviewRoot.y
                            jiggle.snapTo(0, 0)
                            screenSharePreviewRoot.width = Screen.width
                            screenSharePreviewRoot.height = Screen.height
                            screenSharePreviewRoot.isMaximizedState = true
                        } else {
                            jiggle.snapTo(screenSharePreviewRoot.prevX, screenSharePreviewRoot.prevY)
                            screenSharePreviewRoot.width = screenSharePreviewRoot.prevWidth
                            screenSharePreviewRoot.height = screenSharePreviewRoot.prevHeight
                            screenSharePreviewRoot.isMaximizedState = false
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    text: screenSharePreviewRoot.isMaximizedState ? "◱" : "□"
                    color: "#DDDDDD"
                    font.pixelSize: 11
                }
            }

            // Minimize (shrink to island)
            Rectangle {
                width: 22; height: 22; radius: 11
                color: ssMinMouse.containsMouse ? "#C8C83B" : "#FFD700"
                Behavior on color { ColorAnimation { duration: 120 } }
                Text { anchors.centerIn: parent; text: "—"; color: "#1A1A1E"; font.pixelSize: 11; font.bold: true }
                MouseArea {
                    id: ssMinMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: screenSharePreviewRoot.minimizeToIsland()
                }
            }

            // Close button
            Rectangle {
                id: closeBtn
                width: 22
                height: 22
                radius: 11
                color: closeMouse.pressed ? "#C83B3B" : (closeMouse.containsMouse ? "#FF5555" : "#FF3B30")
                Behavior on color { ColorAnimation { duration: 150 } }

                MouseArea {
                    id: closeMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (babyController) {
                            babyController.setScreenSharePreviewVisible(false)
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    text: "✕"
                    color: "white"
                    font.pixelSize: 11
                    font.bold: true
                }
            }
        }

        // Fluid Content Area
        Column {
            id: contentCol
            anchors.fill: parent
            anchors.topMargin: 12
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            anchors.bottomMargin: 12
            spacing: 8

            Text {
                text: "📺 Screen Share Preview"
                color: "#7C7CFF"
                font.pixelSize: 14
                font.bold: true
                font.letterSpacing: 0.5
            }

            Text {
                text: babyController ? babyController.screenShareSummary : "No screens selected"
                color: "#AAA"
                font.pixelSize: 11
            }

            Rectangle {
                width: contentCol.width
                height: contentCol.height - 45
                color: "#0D0D0F"
                radius: 8
                border.color: Qt.rgba(1, 1, 1, 0.05)
                clip: true

                Image {
                    id: screenImage
                    anchors.fill: parent
                    anchors.margins: 4
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    cache: false
                    source: babyController ? babyController.screenShareFrame : ""

                    onStatusChanged: {
                        if (status === Image.Ready && source !== "") {
                            noScreenText.visible = false
                        } else if (source === "") {
                            noScreenText.visible = true
                        }
                    }
                }

                Text {
                    id: noScreenText
                    anchors.centerIn: parent
                    text: babyController && babyController.screenShareGranted
                          ? "Rendering live screen preview..."
                          : "Screen content will appear here\nwhen screen share is active"
                    color: "#666"
                    font.pixelSize: 12
                    textFormat: Text.PlainText
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }

        // Right Edge Resize Handle
        MouseArea {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: 20
            anchors.bottomMargin: 20
            width: 8
            cursorShape: Qt.SizeHorCursor
            property point clickPos: "0,0"
            onPressed: clickPos = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                var deltaX = mouse.x - clickPos.x
                var newW = screenSharePreviewRoot.width + deltaX
                if (newW >= screenSharePreviewRoot.minimumWidth) {
                    screenSharePreviewRoot.width = newW
                }
            }
        }

        // Bottom Edge Resize Handle
        MouseArea {
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            height: 8
            cursorShape: Qt.SizeVerCursor
            property point clickPos: "0,0"
            onPressed: clickPos = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                var deltaY = mouse.y - clickPos.y
                var newH = screenSharePreviewRoot.height + deltaY
                if (newH >= screenSharePreviewRoot.minimumHeight) {
                    screenSharePreviewRoot.height = newH
                }
            }
        }

        // Bottom-Right Corner Resize Grip (2D Reshaping)
        MouseArea {
            id: cornerGrip
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            width: 18
            height: 18
            cursorShape: Qt.SizeFDiagCursor
            z: 30
            property point clickPos: "0,0"
            onPressed: clickPos = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                var deltaX = mouse.x - clickPos.x
                var deltaY = mouse.y - clickPos.y
                var newW = screenSharePreviewRoot.width + deltaX
                var newH = screenSharePreviewRoot.height + deltaY
                if (newW >= screenSharePreviewRoot.minimumWidth) screenSharePreviewRoot.width = newW
                if (newH >= screenSharePreviewRoot.minimumHeight) screenSharePreviewRoot.height = newH
            }

            Text {
                anchors.centerIn: parent
                text: "⇲"
                color: "#7C7CFF"
                font.pixelSize: 12
            }
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
            previewBg.opacity = 0
            windowFadeIn.start()
            jiggle.popIn()
            screenshotUpdateTimer.start()
        } else {
            jiggle.stopWobble()
            screenshotUpdateTimer.stop()
            // Sync Python state when closed externally (Alt+F4, taskbar, etc.)
            if (babyController && babyController.screenSharePreviewVisible) {
                babyController.setScreenSharePreviewVisible(false)
            }
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














