import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Window {
    id: responseWindow
    title: "BABY - Response"
    visible: babyController ? babyController.responseWindowVisible : false
    width: 450
    height: 300
    minimumWidth: 300
    minimumHeight: 200
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"

    x: jiggle.baseX + jiggle.offsetX
    y: jiggle.baseY + jiggle.offsetY

    JiggleHelper { id: jiggle; target: responseWindow }

    onVisibleChanged: {
        if (babyController) {
            babyController.set_response_window_visible(visible)
        }
        if (visible) {
            windowBg.opacity = 0
            windowFadeIn.start()
            jiggle.popIn()
        } else {
            jiggle.stopWobble()
        }
    }

    NumberAnimation {
        id: windowFadeIn
        target: windowBg
        property: "opacity"
        to: 1
        duration: 150
        easing.type: Easing.OutCubic
    }

    // Make window draggable — jiggly physics on drop
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.SizeAllCursor
        property point clickPos: "0,0"
        onPressed: {
            clickPos = Qt.point(mouse.x, mouse.y)
            jiggle.beginDrag()
        }
        onPositionChanged: {
            jiggle.dragTo(mouse.x - clickPos.x, mouse.y - clickPos.y)
        }
        onReleased: jiggle.release()
    }

    Rectangle {
        id: windowBg
        anchors.fill: parent
        color: "#1A1A1E"
        radius: 16
        border.color: Qt.rgba(1, 1, 1, 0.1)
        border.width: 1

        // Window controls
        Row {
            id: controlsRow
            anchors { top: parent.top; right: parent.right; topMargin: 10; rightMargin: 10 }
            spacing: 8

            // Minimize button (just hide)
            Rectangle {
                width: 16; height: 16; radius: 8
                color: minBtnMouse.pressed ? "#C8C83B" : "#FFD700"
                MouseArea {
                    id: minBtnMouse
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: responseWindow.visible = false
                }
            }

            // Close button (dismisses the answer everywhere — island + window)
            Rectangle {
                width: 16; height: 16; radius: 8
                color: closeBtnMouse.pressed ? "#C83B3B" : "#FF5555"
                MouseArea {
                    id: closeBtnMouse
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: babyController ? babyController.dismissResponse() : undefined
                }
            }
        }

        Column {
            anchors { fill: parent; topMargin: 35; leftMargin: 20; rightMargin: 20; bottomMargin: 20 }
            spacing: 10

            Text {
                text: "BABY says:"
                color: "#7C7CFF"
                font.pixelSize: 14
                font.bold: true
            }

            ScrollView {
                width: parent.width
                height: parent.height - 50
                clip: true

                TextArea {
                    id: responseText
                    width: parent.width
                    height: implicitHeight
                    text: babyController ? babyController.assistantResponse : ""
                    color: "#DDD"
                    font.pixelSize: 14
                    font.family: "Segoe UI"
                    wrapMode: TextEdit.WordWrap
                    readOnly: true
                    selectByMouse: true
                    selectByKeyboard: true
                }
            }
        }
    }
}














