// ui/qml/DynamicIsland.qml
// Baby's Dynamic Island — frameless, transparent, always-on-top.
// Premium dark aesthetic with violet-purple gradient accents.

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Effects
import QtQuick.Window 2.15

Window {
    id: root
    title: "BABY"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    visible: true
    minimumWidth: 80
    minimumHeight: 36

    x: (babyController ? babyController.islandX : 600) + dragOffsetX
    y: (babyController ? babyController.islandY : 12) + dragOffsetY

    // Drag offsets are added to the controller position instead of mutating
    // x/y imperatively — assigning to x/y in JS would destroy the binding
    // above and break "Reset Island Position" after the first drag.
    property real dragOffsetX: 0
    property real dragOffsetY: 0

    width:  islandBg.implicitWidth  + 32
    height: islandBg.implicitHeight + 20

    Behavior on width  { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
    Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

    // ═══════════════════════════════════════════════════════════════
    // ISLAND BACKGROUND
    // ═══════════════════════════════════════════════════════════════
    Rectangle {
        id: islandBg
        anchors.centerIn: parent

        property string stateStr: babyController ? babyController.state : "idle"
        property bool exitMenuOpen: false
        property bool hasAnswer: !exitMenuOpen
                                 && (babyController ? babyController.assistantResponse !== "" : false)
                                 && stateStr !== "consent"

        color: "#0A0A0E"
        radius: (exitMenuOpen || hasAnswer)
            ? 20
            : ((stateStr === "idle" || stateStr === "listening") ? height / 2 : 22)
        Behavior on radius { NumberAnimation { duration: 200; easing.type: Easing.InOutCubic } }

        // ── State-change squish ─────────────────────────────────────────────
        // The island "squishes" briefly whenever the state swaps, then springs
        // back with an overshoot — instant feedback that hides resize lag.
        property real squish: 1.0
        onStateStrChanged: {
            squish = 0.94
            squishBack.restart()
        }
        NumberAnimation {
            id: squishBack
            target: islandBg
            property: "squish"
            to: 1.0
            duration: 340
            easing.type: Easing.OutBack
        }
        scale: squish * (dragArea.pressed ? 0.97 : 1.0)

        // ── Glow effect ─────────────────────────────────────────────────
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowBlur: 0.6
            shadowColor: islandBg.exitMenuOpen ? "#66FF453A" : stateGlowColor()
            shadowVerticalOffset: 8
            shadowHorizontalOffset: 0
        }

        implicitWidth: {
            var minW = mainLayoutRow.implicitWidth + (stateStr === "consent" ? 44 : 28)
            if (exitMenuOpen) {
                return Math.min(Math.max(minW, 300), Screen.width - 40)
            } else if (hasAnswer) {
                return Math.min(Math.max(minW, 480), Screen.width - 40)
            }
            return Math.min(minW, Screen.width - 40)
        }

        implicitHeight: Math.min(islandContentCol.implicitHeight + (exitMenuOpen ? 22 : (hasAnswer ? 22 : (stateStr === "consent" ? 26 : 16))), Screen.height - 60)

        Behavior on implicitWidth  { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }
        Behavior on implicitHeight { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }

        // ── Subtle top-gradient shine ──────────────────────────────────────
        Rectangle {
            anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
            height: Math.min(parent.height * 0.55, 32)
            radius: parent.radius
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1,1,1,0.07) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        // ── Thin border ───────────────────────────────────────────────────
        Rectangle {
            anchors.fill: parent
            color: "transparent"
            radius: parent.radius
            border.color: islandBg.exitMenuOpen
                ? Qt.rgba(1, 0.27, 0.23, 0.35)
                : islandBg.stateStr === "listening"
                    ? Qt.rgba(0.55, 0.55, 1, 0.30)
                    : Qt.rgba(1, 1, 1, 0.08)
            border.width: 1
            Behavior on border.color { ColorAnimation { duration: 400 } }
        }

        // ── Drag ──────────────────────────────────────────────────────────
        MouseArea {
            id: dragArea
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.SizeAllCursor
            property point clickPos: "0,0"
            onPressed:  {
                if (mouse.button === Qt.RightButton) {
                    islandBg.exitMenuOpen = !islandBg.exitMenuOpen
                    return
                }
                clickPos = Qt.point(mouse.x, mouse.y)
                root.dragOffsetX = 0
                root.dragOffsetY = 0
            }
            onPositionChanged: {
                if (mouse.buttons & Qt.LeftButton) {
                    root.dragOffsetX += mouse.x - clickPos.x
                    root.dragOffsetY += mouse.y - clickPos.y
                }
            }
            onReleased: {
                if (mouse.button === Qt.LeftButton) {
                    var finalX = root.x
                    var finalY = root.y
                    root.dragOffsetX = 0
                    root.dragOffsetY = 0
                    babyController.savePosition(finalX, finalY)
                }
            }
        }

        // ── Main layout ───────────────────────────────────────────────────
        Column {
            id: islandContentCol
            anchors.centerIn: parent
            width: islandBg.width - 28
            spacing: (islandBg.exitMenuOpen || islandBg.hasAnswer) ? 10 : 0

            // Top control row
            Row {
                id: mainLayoutRow
                height: 28
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 8

                Loader {
                    id: contentItem
                    anchors.verticalCenter: parent.verticalCenter
                    transformOrigin: Item.Center
                    property string s: babyController ? babyController.state : "idle"
                    sourceComponent: {
                        switch(s) {
                            case "loading":         return cLoading
                            case "activating":      return cActivating
                            case "listening":       return cListening
                            case "thinking":        return cThinking
                            case "speaking":        return cSpeaking
                            case "consent":         return cConsent
                            case "error":           return cError
                            case "network_active":  return cNetwork
                            default:                return cIdle
                        }
                    }
                    onSourceComponentChanged: { opacity = 0; scale = 0.92; contentPopIn.start() }
                    ParallelAnimation {
                        id: contentPopIn
                        NumberAnimation { target: contentItem; property: "opacity"; to: 1; duration: 160; easing.type: Easing.OutCubic }
                        NumberAnimation { target: contentItem; property: "scale";   to: 1; duration: 260; easing.type: Easing.OutBack }
                    }
                }

                // Thin divider
                Rectangle {
                    width: 1; height: 14
                    color: Qt.rgba(1, 1, 1, 0.12)
                    anchors.verticalCenter: parent.verticalCenter
                }

                // ── Control buttons ────────────────────────────────────────
                // Mute Speaker
                ControlButton {
                    icon: (babyController && babyController.speakerMuted) ? "🔇" : "🔊"
                    active: babyController ? !babyController.speakerMuted : false
                    onTapped: babyController.toggleSpeakerMute()
                }
                // Mute Mic
                ControlButton {
                    icon: (babyController && babyController.micMuted) ? "✕" : "🎙"
                    active: babyController ? !babyController.micMuted : false
                    accentColor: (babyController && babyController.micMuted) ? "#FF3B30" : "#8B5CF6"
                    onTapped: babyController.toggleMicMute()
                }
                // Screen Share
                ControlButton {
                    icon: (babyController && babyController.screenShareGranted) ? "🖥✓" : "🖥"
                    active: babyController ? babyController.screenShareGranted : false
                    accentColor: (babyController && babyController.screenShareGranted) ? "#30D158" : "#8B5CF6"
                    showIndicator: babyController ? babyController.screenShareGranted : false
                    onTapped: { if (babyController) babyController.toggleScreenShare() }
                }
                // Camera — blocked (dimmed, non-clickable) when no camera exists
                ControlButton {
                    icon: (babyController && babyController.cameraAccessGranted) ? "📷✓" : "📷"
                    active: babyController ? babyController.cameraAccessGranted : false
                    buttonEnabled: babyController ? babyController.cameraAvailable : false
                    accentColor: "#FF9F0A"
                    onTapped: { if (babyController) babyController.toggleCameraAccess() }
                }

                // Exit / Power button
                Rectangle {
                    width: 24; height: 24; radius: 12
                    anchors.verticalCenter: parent.verticalCenter
                    color: islandBg.exitMenuOpen
                           ? "#E03838"
                           : (exitMouse.containsMouse ? "#C83B3B" : "#992828")
                    border.color: Qt.rgba(1,1,1,0.1); border.width: 1
                    Behavior on color { ColorAnimation { duration: 150 } }

                    Text {
                        anchors.centerIn: parent; text: "⏻"
                        color: "white"; font.pixelSize: 12
                    }
                    scale: exitMouse.pressed ? 0.88 : 1.0
                    Behavior on scale { NumberAnimation { duration: 100 } }

                    MouseArea {
                        id: exitMouse; anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: islandBg.exitMenuOpen = !islandBg.exitMenuOpen
                    }
                }
            }

            // ── Expanded exit panel ────────────────────────────────────────
            Column {
                id: exitMenuPanel
                visible: islandBg.exitMenuOpen
                width: parent.width
                spacing: 6
                anchors.horizontalCenter: parent.horizontalCenter

                Rectangle { width: parent.width; height: 1; color: Qt.rgba(1,1,1,0.10) }

                ExitMenuEntry {
                    label: "Settings"; sublabel: "Configure LLM, Voice, Mic & UI"
                    icon: "⚙"; iconColor: "#7C7CFF"; bgHover: "#1A1A2E"
                    onActivated: { islandBg.exitMenuOpen = false; if (babyController) babyController.openSettings() }
                }
                ExitMenuEntry {
                    label: "Shut Down BABY"; sublabel: "Close assistant session & exit"
                    icon: "⏻"; iconColor: "#FF453A"; bgHover: "#2C1214"
                    onActivated: { islandBg.exitMenuOpen = false; if (babyController) babyController.requestExit() }
                }
                ExitMenuEntry {
                    label: "Restart Assistant"; sublabel: "Reboot BABY background process"
                    icon: "⟳"; iconColor: "#FFFFFF"; bgHover: "#202024"
                    onActivated: { islandBg.exitMenuOpen = false; if (babyController) babyController.requestRestart() }
                }
                ExitMenuEntry {
                    label: "Toggle Test Mode"; sublabel: "Switch LLM test mode"
                    icon: "⚡"; iconColor: "#FFB347"; bgHover: "#2A1E10"
                    onActivated: { islandBg.exitMenuOpen = false; if (babyController) babyController.toggleTestMode() }
                }
            }

            // ── Generated-answer panel ─────────────────────────────────────
            // Answers live IN the island; the panel wraps and scrolls so any
            // response length fits, capped to the screen size.
            Column {
                id: answerPanel
                visible: islandBg.hasAnswer
                width: parent.width
                spacing: 8
                anchors.horizontalCenter: parent.horizontalCenter

                Rectangle { width: parent.width; height: 1; color: Qt.rgba(1,1,1,0.10) }

                Item {
                    width: parent.width
                    height: 22

                    Text {
                        text: "✦ BABY"
                        color: "#7C7CFF"
                        font { pixelSize: 11; bold: true }
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Row {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6

                        // Expand into the full response window
                        Rectangle {
                            id: expandBtn
                            width: 20; height: 20; radius: 10
                            color: expandMouse.containsMouse ? "#28283A" : "#18181E"
                            border.color: Qt.rgba(1,1,1,0.08); border.width: 1
                            Text { anchors.centerIn: parent; text: "⛶"; color: "#AAA"; font.pixelSize: 10 }
                            MouseArea {
                                id: expandMouse; anchors.fill: parent; hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: babyController ? babyController.set_response_window_visible(true) : undefined
                            }
                        }
                        // Dismiss
                        Rectangle {
                            id: dismissBtn
                            width: 20; height: 20; radius: 10
                            color: dismissMouse.containsMouse ? "#28283A" : "#18181E"
                            border.color: Qt.rgba(1,1,1,0.08); border.width: 1
                            Text { anchors.centerIn: parent; text: "✕"; color: "#AAA"; font.pixelSize: 10 }
                            MouseArea {
                                id: dismissMouse; anchors.fill: parent; hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: babyController ? babyController.dismissResponse() : undefined
                            }
                        }
                    }
                }

                ScrollView {
                    id: answerScroll
                    width: parent.width
                    height: Math.min(answerText.implicitHeight + 4, Math.min(240, Screen.height - 180))
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    Text {
                        id: answerText
                        width: answerScroll.width
                        text: babyController ? babyController.assistantResponse : ""
                        color: "#E2E8F0"
                        font { pixelSize: 12; family: "Segoe UI, sans-serif" }
                        wrapMode: Text.WordWrap
                        textFormat: Text.MarkdownText
                    }
                }
            }
        }
    }

    // ── Relationship Section ──────────────────────────────────────────────────
    Rectangle {
        id: relationshipSection
        anchors { top: responseArea.bottom; topMargin: 4; horizontalCenter: parent.horizontalCenter }
        width: parent.width - 16
        height: relationshipContent.implicitHeight + 16
        visible: relationshipRepeater.count > 0
        color: "#0A0A0E"
        radius: 10
        border.color: "#222244"
        border.width: 1

        property var relationships: []

        ColumnLayout {
            id: relationshipContent
            anchors.fill: parent
            anchors.margins: 8
            spacing: 4

            RowLayout {
                Layout.fillWidth: true
                Rectangle { width: 6; height: 6; radius: 3; color: "#22c55e" }
                Text { text: "Relationships"; color: "#aaa"; font.pixelSize: 10; font.bold: true; Layout.fillWidth: true }
                Text { text: relationshipRepeater.count.toString(); color: "#666"; font.pixelSize: 9 }
            }

            Repeater {
                id: relationshipRepeater
                model: relationshipSection.relationships

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    color: "#111122"
                    radius: 6

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 4
                        spacing: 6

                        Rectangle {
                            Layout.preferredWidth: relTypeText.implicitWidth + 8
                            Layout.preferredHeight: 16
                            radius: 3
                            color: {
                                switch(modelData.type) {
                                    case "SEQUENTIAL": return "#22c55e";
                                    case "CAUSAL": return "#f59e0b";
                                    case "CONDITIONAL": return "#3b82f6";
                                    case "PARALLEL": return "#8b5cf6";
                                    case "CONTEXTUAL": return "#06b6d4";
                                    case "CONTRADICTORY": return "#ef4444";
                                    default: return "#6b7280";
                                }
                            }
                            Text {
                                id: relTypeText
                                anchors.centerIn: parent
                                text: modelData.type || "?"
                                color: "#fff"
                                font.pixelSize: 8
                                font.bold: true
                            }
                        }

                        Text {
                            text: Math.round((modelData.confidence || 0) * 100) + "%"
                            color: "#888"
                            font.pixelSize: 9
                        }

                        Text {
                            text: modelData.explanation || ""
                            color: "#aaa"
                            font.pixelSize: 9
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            maximumLineCount: 1
                        }
                    }
                }
            }
        }

        Connections {
            target: babyController

            function onRelationshipsReady(results) {
                relationshipSection.relationships = results
            }
        }
    }

    // ── Privacy indicators ────────────────────────────────────────────────────
    Row {
        anchors { right: islandBg.right; rightMargin: 8; top: islandBg.top; topMargin: 8 }
        spacing: 4
        Rectangle {
            visible: babyController ? babyController.micActive : false
            width: 16; height: 16; radius: 8; color: "#FF453A"
            Text { anchors.centerIn: parent; text: "🎙"; font.pixelSize: 8 }
        }
        Rectangle {
            visible: babyController ? babyController.camActive : false
            width: 16; height: 16; radius: 8; color: "#FF9F0A"
            Text { anchors.centerIn: parent; text: "📷"; font.pixelSize: 8 }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // REUSABLE CONTROL BUTTON COMPONENT
    // ═══════════════════════════════════════════════════════════════
    component ControlButton: Rectangle {
        property string icon: ""
        property bool active: false
        property bool buttonEnabled: true
        property string accentColor: "#8B5CF6"
        property bool showIndicator: false
        signal tapped()

        width: 24; height: 24; radius: 12
        anchors.verticalCenter: parent !== null ? parent.verticalCenter : undefined
        opacity: buttonEnabled ? 1.0 : 0.35
        Behavior on opacity { NumberAnimation { duration: 150 } }
        color: active
               ? Qt.rgba(0.54, 0.36, 0.96, 0.25)
               : (btnMouse.containsMouse ? "#28283A" : "#18181E")
        border.color: active ? accentColor : Qt.rgba(1,1,1,0.08)
        border.width: active ? 2 : 1
        Behavior on color { ColorAnimation { duration: 150 } }

        Text {
            anchors.centerIn: parent; text: parent.icon
            font.pixelSize: 10
        }

        // Green status dot when active
        Rectangle {
            visible: showIndicator
            width: 6; height: 6; radius: 3
            anchors.top: parent.top; anchors.right: parent.right
            anchors.topMargin: -1; anchors.rightMargin: -1
            color: accentColor
            border.color: "#0F0F13"; border.width: 1
        }

        scale: btnMouse.pressed ? 0.85 : (btnMouse.containsMouse ? 1.12 : 1.0)
        Behavior on scale { SpringAnimation { spring: 4; damping: 0.4 } }

        MouseArea {
            id: btnMouse; anchors.fill: parent; hoverEnabled: buttonEnabled
            cursorShape: buttonEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            enabled: parent.buttonEnabled
            onClicked: if (parent.buttonEnabled) parent.tapped()
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // EXIT MENU ENTRY COMPONENT
    // ═══════════════════════════════════════════════════════════════
    component ExitMenuEntry: Rectangle {
        property string label: ""
        property string sublabel: ""
        property string icon: ""
        property string iconColor: "#FFFFFF"
        property string bgHover: "#202024"
        signal activated()

        width: parent !== null ? parent.width : 250
        height: 40; radius: 10
        color: entryMouse.containsMouse ? bgHover : "#111115"
        border.color: entryMouse.containsMouse ? Qt.rgba(1,1,1,0.12) : Qt.rgba(1,1,1,0.05)
        border.width: 1
        Behavior on color { ColorAnimation { duration: 100 } }

        scale: entryMouse.pressed ? 0.97 : 1.0
        Behavior on scale { NumberAnimation { duration: 80 } }

        Row {
            anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
            Text {
                anchors.verticalCenter: parent.verticalCenter; text: parent.parent.icon
                color: parent.parent.iconColor; font.pixelSize: 14; font.bold: true
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter; spacing: 1
                Text { text: parent.parent.parent.label; color: parent.parent.parent.iconColor; font { pixelSize: 12; bold: true } }
                Text { text: parent.parent.parent.sublabel; color: "#8E8E93"; font.pixelSize: 9 }
            }
        }
        MouseArea {
            id: entryMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onClicked: parent.activated()
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // STATE: IDLE
    // ═══════════════════════════════════════════════════════════════
    // STATE: LOADING (warmup)
    // ═══════════════════════════════════════════════════════════════
    Component {
        id: cLoading
        Row {
            spacing: 10

            // Pulsing warmup ring
            Item {
                width: 20; height: 20; anchors.verticalCenter: parent.verticalCenter
                Rectangle {
                    anchors.fill: parent; radius: width / 2
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "#8B5CF6" }
                        GradientStop { position: 1.0; color: "#EC4899" }
                    }
                    RotationAnimator on rotation { loops: Animation.Infinite; from: 0; to: 360; duration: 1200 }
                    SequentialAnimation on opacity {
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.4; duration: 800; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 1.0; duration: 800; easing.type: Easing.InOutSine }
                    }
                }
                Rectangle {
                    anchors.centerIn: parent; width: parent.width - 5; height: parent.height - 5
                    radius: width / 2; color: "#0A0A0E"
                }
            }

            Column {
                spacing: 2; anchors.verticalCenter: parent.verticalCenter
                Text { text: "Warming up…"; color: "white"; font { pixelSize: 13; family: "Segoe UI" } }
                Text { text: "Loading models"; color: "#6B6B8A"; font.pixelSize: 10 }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // STATE: ACTIVATING (play button pressed, starting up)
    // ═══════════════════════════════════════════════════════════════
    Component {
        id: cActivating
        Row {
            spacing: 10

            // Spinning activation ring
            Item {
                width: 20; height: 20; anchors.verticalCenter: parent.verticalCenter
                Rectangle {
                    anchors.fill: parent; radius: width / 2
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "#30D158" }
                        GradientStop { position: 1.0; color: "#8B5CF6" }
                    }
                    RotationAnimator on rotation { loops: Animation.Infinite; from: 0; to: 360; duration: 800 }
                }
                Rectangle {
                    anchors.centerIn: parent; width: parent.width - 5; height: parent.height - 5
                    radius: width / 2; color: "#0A0A0E"
                }
            }

            Column {
                spacing: 2; anchors.verticalCenter: parent.verticalCenter
                Text { text: "Starting…"; color: "white"; font { pixelSize: 13; family: "Segoe UI" } }
                Text { text: "Activating assistant"; color: "#6B6B8A"; font.pixelSize: 10 }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    Component {
        id: cIdle
        Row {
            spacing: 8

            // Activate button — gradient fill
            Rectangle {
                id: activateButton
                width: 24; height: 24; radius: 12
                anchors.verticalCenter: parent.verticalCenter
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: activateMA.containsMouse ? "#9B6FFF" : "#8B5CF6" }
                    GradientStop { position: 1.0; color: activateMA.containsMouse ? "#7B76FF" : "#6366F1" }
                }
                Behavior on gradient { } // allow gradient animation
                scale: activateMA.pressed ? 0.85 : (activateMA.containsMouse ? 1.12 : 1.0)
                Behavior on scale { SpringAnimation { spring: 4; damping: 0.4 } }

                Text {
                    anchors.centerIn: parent; text: "▶"
                    color: "white"; font.pixelSize: 10; font.bold: true
                    x: 1
                }
                MouseArea {
                    id: activateMA; anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: babyController.triggerToggle()
                }
            }

            Text {
                text: "BABY"
                color: "#6B6B8A"
                font { pixelSize: 13; family: "Segoe UI, sans-serif"; weight: Font.Medium }
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // STATE: LISTENING
    // ═══════════════════════════════════════════════════════════════
    Component {
        id: cListening
        Row {
            spacing: 10

            // Stop button
            Rectangle {
                width: 24; height: 24; radius: 12
                color: stopMA.containsMouse ? "#FF5555" : "#FF3B30"
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: 120 } }
                scale: stopMA.pressed ? 0.85 : 1.0
                Behavior on scale { NumberAnimation { duration: 80 } }
                Text { anchors.centerIn: parent; text: "■"; color: "white"; font.pixelSize: 10; font.bold: true }
                MouseArea {
                    id: stopMA; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: babyController.triggerToggle()
                }
            }

            // Animated waveform bars
            Item {
                width: 27; height: 20
                anchors.verticalCenter: parent.verticalCenter
                Row {
                    anchors.centerIn: parent
                    spacing: 3
                    Repeater {
                        model: 5
                        Rectangle {
                            id: waveBar
                            width: 3; radius: 1.5
                            property real baseH: 6 + (index % 3) * 3
                            height: baseH
                            anchors.verticalCenter: parent.verticalCenter
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: "#B8B8FF" }
                                GradientStop { position: 1.0; color: "#8B5CF6" }
                            }
                            SequentialAnimation on height {
                                loops: Animation.Infinite
                                NumberAnimation { to: 14; duration: 200 + index * 45; easing.type: Easing.InOutSine }
                                NumberAnimation { to: waveBar.baseH; duration: 200 + index * 45; easing.type: Easing.InOutSine }
                            }
                        }
                    }
                }
            }

            Text {
                text: "Listening…"
                color: "#E0E0FF"
                font { pixelSize: 13; family: "Segoe UI, sans-serif"; weight: Font.Medium }
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // STATE: THINKING
    // ═══════════════════════════════════════════════════════════════
    Component {
        id: cThinking
        Row {
            spacing: 10

            // Stop
            Rectangle {
                width: 24; height: 24; radius: 12
                color: stopTMA.containsMouse ? "#FF5555" : "#FF3B30"
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: 120 } }
                scale: stopTMA.pressed ? 0.85 : 1.0
                Behavior on scale { NumberAnimation { duration: 80 } }
                Text { anchors.centerIn: parent; text: "■"; color: "white"; font.pixelSize: 10; font.bold: true }
                MouseArea {
                    id: stopTMA; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: babyController.triggerToggle()
                }
            }

            // Gradient spinner
            Item {
                width: 20; height: 20; anchors.verticalCenter: parent.verticalCenter
                Rectangle {
                    anchors.fill: parent; radius: width / 2
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "#8B5CF6" }
                        GradientStop { position: 1.0; color: "#EC4899" }
                    }
                    RotationAnimator on rotation { loops: Animation.Infinite; from: 0; to: 360; duration: 700 }
                }
                Rectangle {
                    anchors.centerIn: parent; width: parent.width - 5; height: parent.height - 5
                    radius: width / 2; color: "#0A0A0E"
                }
            }

            Column {
                spacing: 2; anchors.verticalCenter: parent.verticalCenter
                Text { text: "Thinking…"; color: "white"; font { pixelSize: 13; family: "Segoe UI" } }
                Row {
                    spacing: 4
                    visible: babyController && babyController.speaker !== ""
                    Text {
                        text: babyController ? babyController.speaker : ""
                        visible: text !== ""; color: "#8B5CF6"; font.pixelSize: 10
                    }
                    Rectangle {
                        width: 14; height: 14; radius: 3
                        visible: babyController && babyController.speaker !== ""
                        color: Qt.rgba("#FFD700".r, "#FFD700".g, "#FFD700".b, 0.2)
                        Text { anchors.centerIn: parent; text: "👑"; font.pixelSize: 8 }
                        // Show crown only for admin (would need to check admin status)
                    }
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // STATE: SPEAKING
    // ═══════════════════════════════════════════════════════════════
    Component {
        id: cSpeaking
        Row {
            spacing: 8

            // Stop
            Rectangle {
                width: 20; height: 20; radius: 10
                color: stopSMA.containsMouse ? "#FF5555" : "#FF3B30"
                anchors.verticalCenter: parent.verticalCenter
                Behavior on color { ColorAnimation { duration: 120 } }
                Text { anchors.centerIn: parent; text: "■"; color: "white"; font.pixelSize: 9; font.bold: true }
                MouseArea {
                    id: stopSMA; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: babyController.triggerToggle()
                }
            }

            // Pulsing green ring
            Item {
                width: 16; height: 16; anchors.verticalCenter: parent.verticalCenter
                Rectangle {
                    anchors.fill: parent; radius: width / 2; color: "transparent"
                    border.color: "#30D158"; border.width: 2
                    SequentialAnimation on opacity {
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.3; duration: 500 }
                        NumberAnimation { to: 1.0; duration: 500 }
                    }
                }
                Rectangle {
                    anchors.centerIn: parent; width: 8; height: 8; radius: 4; color: "#30D158"
                }
            }

            Text {
                text: "BABY"
                color: "#30D158"
                font.pixelSize: 13
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // STATE: NETWORK ACTIVE
    // ═══════════════════════════════════════════════════════════════
    Component {
        id: cNetwork
        Row {
            spacing: 8
            Item {
                width: 18; height: 18; anchors.verticalCenter: parent.verticalCenter
                Rectangle {
                    anchors.fill: parent; radius: width / 2; color: "transparent"
                    border.color: "#0A84FF"; border.width: 2
                    RotationAnimator on rotation { loops: Animation.Infinite; from: 0; to: 360; duration: 900 }
                }
            }
            Text {
                text: "Searching…"
                color: "#0A84FF"
                font.pixelSize: 13
                font.family: "Segoe UI"
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // STATE: CONSENT — compact indicator; the full permission dialog
    // lives in the separate ConsentWindow.
    // ═══════════════════════════════════════════════════════════════
    Component {
        id: cConsent
        Row {
            spacing: 8
            Rectangle {
                width: 22; height: 22; radius: 11
                color: "#2A1E10"
                border.color: "#FFB347"
                border.width: 1
                anchors.verticalCenter: parent.verticalCenter
                Text { anchors.centerIn: parent; text: "🔒"; font.pixelSize: 11 }
            }
            Text {
                text: "Permission requested"
                color: "#FFB347"
                font { pixelSize: 13; family: "Segoe UI"; weight: Font.Medium }
                anchors.verticalCenter: parent.verticalCenter
            }
            Rectangle {
                width: 58; height: 24; radius: 12
                color: openPermMouse.containsMouse ? "#FFB347" : "#3A2A12"
                border.color: "#FFB347"
                border.width: 1
                anchors.verticalCenter: parent.verticalCenter
                Text {
                    anchors.centerIn: parent; text: "Open"
                    color: "#FFE9B8"; font { pixelSize: 10; bold: true }
                }
                MouseArea {
                    id: openPermMouse; anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: babyController ? babyController.openConsentWindow() : undefined
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // STATE: ERROR
    // ═══════════════════════════════════════════════════════════════
    Component {
        id: cError
        Row {
            spacing: 8
            Rectangle {
                width: 20; height: 20; radius: 10
                color: stopEMA.containsMouse ? "#FF5555" : "#FF3B30"
                anchors.verticalCenter: parent.verticalCenter
                Text { anchors.centerIn: parent; text: "■"; color: "white"; font.pixelSize: 9; font.bold: true }
                MouseArea {
                    id: stopEMA; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: babyController.triggerToggle()
                }
            }
            Text { text: "⚠"; font.pixelSize: 15; color: "#FF453A"; anchors.verticalCenter: parent.verticalCenter }
            Text {
                text: "Error"
                color: "#FF453A"
                font.pixelSize: 13
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // HELPERS
    // ═══════════════════════════════════════════════════════════════
    function stateGlowColor() {
        switch(babyController ? babyController.state : "idle") {
            case "listening":       return "#668B5CF6"
            case "speaking":        return "#5530D158"
            case "consent":         return "#55FFB347"
            case "error":           return "#55FF453A"
            case "network_active":  return "#550A84FF"
            default:                return "#22000000"
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
            case "high":   return "HIGH RISK ACTION"
            case "medium": return "Action Required"
            default:       return "Quick Action"
        }
    }
}














