// ui/qml/ConsentWindow.qml
// Dedicated permission window — permission requests live here, not in the
// Dynamic Island. Frameless, dark, draggable (same pattern as ResponseWindow).

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Window {
    id: consentWindow
    title: "BABY - Permission"
    visible: babyController ? babyController.consentWindowVisible : false
    width: 460
    height: 320
    minimumWidth: 320
    minimumHeight: 240
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"

    x: jiggle.baseX + jiggle.offsetX
    y: jiggle.baseY + jiggle.offsetY

    JiggleHelper { id: jiggle; target: consentWindow }

    onVisibleChanged: {
        if (babyController) {
            babyController.set_consent_window_visible(visible)
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
        color: "#141417"
        radius: 16
        border.color: Qt.rgba(1, 1, 1, 0.12)
        border.width: 1

        // Deny on close
        Rectangle {
            width: 16; height: 16; radius: 8
            color: closeMouse.pressed ? "#C83B3B" : "#FF5555"
            anchors { top: parent.top; right: parent.right; topMargin: 10; rightMargin: 10 }
            MouseArea {
                id: closeMouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: babyController ? babyController.deny_action() : undefined
            }
        }

        // Minimize button
        Rectangle {
            width: 16; height: 16; radius: 8
            color: consentMinMouse.pressed ? "#C8C83B" : "#FFD700"
            anchors { top: parent.top; right: parent.right; topMargin: 10; rightMargin: 32 }
            MouseArea {
                id: consentMinMouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: consentWindow.visible = false
            }
        }

        Column {
            anchors { fill: parent; topMargin: 22; leftMargin: 20; rightMargin: 20; bottomMargin: 18 }
            spacing: 12

            // Title + risk badge
            Row {
                spacing: 10
                anchors.horizontalCenter: parent.horizontalCenter
                Rectangle {
                    width: 12; height: 12; radius: 6
                    color: riskColor()
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: "BABY needs permission"
                    color: "white"
                    font { pixelSize: 15; bold: true; family: "Segoe UI" }
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            // Risk label
            Text {
                text: riskLabel()
                color: riskColor()
                font { pixelSize: 11; bold: true; family: "Segoe UI" }
                anchors.horizontalCenter: parent.horizontalCenter
            }

            // Plan description (scrollable so long plans always fit)
            Rectangle {
                width: parent.width
                height: 150
                color: "#0E0E12"
                radius: 10
                border.color: Qt.rgba(1, 1, 1, 0.06)
                border.width: 1

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 10
                    clip: true

                    Text {
                        id: planBody
                        width: consentWindow.width - 60
                        text: babyController ? babyController.planText : ""
                        color: "#DDD"
                        font { pixelSize: 13; family: "Segoe UI" }
                        wrapMode: Text.WordWrap
                        textFormat: Text.MarkdownText
                    }
                }
            }

            Item { height: 2; width: 1 }

            // Approve / Deny
            Row {
                spacing: 14
                anchors.horizontalCenter: parent.horizontalCenter

                Rectangle {
                    width: 130; height: 40; radius: 9
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: approveMouse.containsMouse ? "#22a844" : "#1a8c37" }
                        GradientStop { position: 1.0; color: approveMouse.containsMouse ? "#1e9e3e" : "#168030" }
                    }
                    Text { anchors.centerIn: parent; text: "✓  Approve"; color: "white"; font { pixelSize: 13; bold: true } }
                    MouseArea {
                        id: approveMouse; anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: babyController ? babyController.approve_action() : undefined
                    }
                }
                Rectangle {
                    width: 120; height: 40; radius: 9
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: denyMouse.containsMouse ? "#e63547" : "#c82d3d" }
                        GradientStop { position: 1.0; color: denyMouse.containsMouse ? "#cc2f40" : "#b02535" }
                    }
                    Text { anchors.centerIn: parent; text: "✕  Deny"; color: "white"; font { pixelSize: 13; bold: true } }
                    MouseArea {
                        id: denyMouse; anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: babyController ? babyController.deny_action() : undefined
                    }
                }
            }
        }
    }

    function riskColor() {
        switch(babyController ? babyController.riskLevel : "low") {
            case "high":   return "#FF453A"
            case "medium": return "#FFB347"
            default:       return "#30D158"
        }
    }

    function riskLabel() {
        switch(babyController ? babyController.riskLevel : "low") {
            case "high":   return "HIGH RISK ACTION — review carefully"
            case "medium": return "ACTION REQUIRED"
            default:       return "QUICK ACTION"
        }
    }
}














