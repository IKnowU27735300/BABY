import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Window {
    id: screenPickerRoot
    title: "BABY — Screen Share"
    visible: babyController ? babyController.screenSharePickerVisible : false
    width: 480
    height: 580
    minimumWidth: 360
    minimumHeight: 380
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"

    property bool isMaximizedState: false
    property int prevWidth: 480
    property int prevHeight: 580
    property int prevX: 100
    property int prevY: 100

    x: jiggle.baseX + jiggle.offsetX
    y: jiggle.baseY + jiggle.offsetY

    JiggleHelper { id: jiggle; target: screenPickerRoot }

    // ── Screen model ──────────────────────────────────────────────────────────
    ListModel { id: screenShareModel }

    function refreshScreenShareModel() {
        screenShareModel.clear()
        if (!babyController) return
        var screens  = babyController.getAvailableScreens()
        var selected = babyController.screenShareSelection || []
        for (var i = 0; i < screens.length; i++) {
            var s = screens[i]
            var sel = (selected.length === 0 && s.primary)
                      ? true
                      : (selected.indexOf(s.index) !== -1)
            screenShareModel.append({
                "index":   s.index,
                "name":    s.name,
                "label":   s.label,
                "primary": s.primary,
                "selected": sel
            })
        }
        if (typeof applyBtn !== "undefined" && applyBtn) {
            applyBtn.forceRepaint()
        }
    }

    // Returns how many screens are currently selected
    function selectedCount() {
        var n = 0
        for (var i = 0; i < screenShareModel.count; i++)
            if (screenShareModel.get(i).selected) n++
        return n
    }

    function selectedScreenIndices() {
        var indices = []
        for (var i = 0; i < screenShareModel.count; i++) {
            var item = screenShareModel.get(i)
            if (item.selected) indices.push(item.index)
        }
        return indices
    }

    function selectAll() {
        for (var i = 0; i < screenShareModel.count; i++)
            screenShareModel.setProperty(i, "selected", true)
        applyBtn.forceRepaint()
    }

    function deselectAll() {
        for (var i = 0; i < screenShareModel.count; i++)
            screenShareModel.setProperty(i, "selected", false)
        applyBtn.forceRepaint()
    }

    Component.onCompleted: { refreshScreenShareModel() }
    onVisibleChanged: {
        if (visible) {
            refreshScreenShareModel()
            pickerBg.opacity = 0
            windowFadeIn.start()
            jiggle.popIn()
        } else {
            jiggle.stopWobble()
            if (babyController) babyController.closeScreenSharePicker()
        }
    }

    NumberAnimation {
        id: windowFadeIn
        target: pickerBg
        property: "opacity"
        to: 1
        duration: 160
        easing.type: Easing.OutCubic
    }

    // ── Background ─────────────────────────────────────────────────────────────
    Rectangle {
        id: pickerBg
        anchors.fill: parent
        radius: 16
        color: "#0F0F13"
        border.color: Qt.rgba(1, 1, 1, 0.12)
        border.width: 1

        // Top gradient shine
        Rectangle {
            anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
            height: 60; radius: 16
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1,1,1,0.05) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        // ── Drag — jiggly physics on drop ────────────────────────────────────
        MouseArea {
            anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
            height: 44; cursorShape: Qt.SizeAllCursor
            property point clickPos: "0,0"
            onPressed: {
                clickPos = Qt.point(mouse.x, mouse.y)
                if (!screenPickerRoot.isMaximizedState) jiggle.beginDrag()
            }
            onPositionChanged: {
                if (!screenPickerRoot.isMaximizedState) {
                    jiggle.dragTo(mouse.x - clickPos.x, mouse.y - clickPos.y)
                }
            }
            onReleased: jiggle.release()
        }

        // ── Window controls ────────────────────────────────────────────────────
        Row {
            anchors.top: parent.top; anchors.right: parent.right
            anchors.topMargin: 10; anchors.rightMargin: 10
            spacing: 6; z: 30

            Rectangle {
                width: 22; height: 22; radius: 11
                color: maxM.containsMouse ? "#44444F" : "#2A2A35"
                Behavior on color { ColorAnimation { duration: 120 } }
                Text { anchors.centerIn: parent; text: screenPickerRoot.isMaximizedState ? "◱" : "□"; color: "#CCC"; font.pixelSize: 11 }
                MouseArea {
                    id: maxM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (!screenPickerRoot.isMaximizedState) {
                            screenPickerRoot.prevWidth  = screenPickerRoot.width
                            screenPickerRoot.prevHeight = screenPickerRoot.height
                            screenPickerRoot.prevX = screenPickerRoot.x
                            screenPickerRoot.prevY = screenPickerRoot.y
                            jiggle.snapTo(0, 0)
                            screenPickerRoot.width  = Screen.width
                            screenPickerRoot.height = Screen.height
                            screenPickerRoot.isMaximizedState = true
                        } else {
                            jiggle.snapTo(screenPickerRoot.prevX, screenPickerRoot.prevY)
                            screenPickerRoot.width  = screenPickerRoot.prevWidth
                            screenPickerRoot.height = screenPickerRoot.prevHeight
                            screenPickerRoot.isMaximizedState = false
                        }
                    }
                }
            }

            Rectangle {
                width: 22; height: 22; radius: 11
                color: pickerMinM.containsMouse ? "#C8C83B" : "#FFD700"
                Behavior on color { ColorAnimation { duration: 120 } }
                Text { anchors.centerIn: parent; text: "—"; color: "#1A1A1E"; font.pixelSize: 11; font.bold: true }
                MouseArea {
                    id: pickerMinM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: babyController.closeScreenSharePicker()
                }
            }

            Rectangle {
                width: 22; height: 22; radius: 11
                color: closeM.containsMouse ? "#FF5555" : "#FF3B30"
                Behavior on color { ColorAnimation { duration: 120 } }
                Text { anchors.centerIn: parent; text: "✕"; color: "white"; font.pixelSize: 11; font.bold: true }
                MouseArea {
                    id: closeM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: babyController.closeScreenSharePicker()
                }
            }
        }

        // ── Main content ───────────────────────────────────────────────────────
        Column {
            anchors.fill: parent
            anchors.margins: 16
            anchors.topMargin: 48
            spacing: 12

            // Title
            Row {
                spacing: 8
                Text {
                    text: "🖥"
                    font.pixelSize: 20
                    anchors.verticalCenter: parent.verticalCenter
                }
                Column {
                    spacing: 2
                    Text {
                        text: babyController && babyController.screenShareGranted
                              ? "Modify Screen Selection"
                              : "Select Displays to Share"
                        color: "#B8B8FF"
                        font { bold: true; pixelSize: 15 }
                    }
                    Text {
                        text: babyController && babyController.screenShareGranted
                              ? "Currently sharing — add, remove, or stop"
                              : "BABY will capture these for AI screen context"
                        color: "#666"
                        font.pixelSize: 11
                    }
                }
            }

            // Select All / Deselect All row
            Row {
                spacing: 8

                Rectangle {
                    width: 100; height: 26; radius: 6
                    color: selAllM.containsMouse ? "#2C2C38" : "#1E1E28"
                    border.color: Qt.rgba(1,1,1,0.08); border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text {
                        anchors.centerIn: parent; text: "Select All"
                        color: "#AAA"; font.pixelSize: 11
                    }
                    MouseArea {
                        id: selAllM; anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: selectAll()
                    }
                }

                Rectangle {
                    width: 110; height: 26; radius: 6
                    color: deselAllM.containsMouse ? "#2C2C38" : "#1E1E28"
                    border.color: Qt.rgba(1,1,1,0.08); border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text {
                        anchors.centerIn: parent; text: "Deselect All"
                        color: "#AAA"; font.pixelSize: 11
                    }
                    MouseArea {
                        id: deselAllM; anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: deselectAll()
                    }
                }
            }

            // Screen list
            Rectangle {
                width: parent.width
                height: parent.height - 190
                color: "#080810"
                radius: 10
                border.color: Qt.rgba(1, 1, 1, 0.06)
                clip: true

                ListView {
                    id: screenListView
                    anchors.fill: parent
                    anchors.margins: 8
                    model: screenShareModel
                    spacing: 6
                    clip: true

                    delegate: Rectangle {
                        id: delegateRoot
                        width: screenListView.width
                        height: 58
                        radius: 8

                        color: model.selected
                               ? Qt.rgba(0.42, 0.37, 0.85, 0.22)
                               : (itemMouse.containsMouse ? "#1C1C26" : "#131318")
                        border.color: model.selected ? "#8B5CF6" : Qt.rgba(1,1,1,0.05)
                        border.width: model.selected ? 2 : 1

                        Behavior on color { ColorAnimation { duration: 100 } }
                        Behavior on border.color { ColorAnimation { duration: 100 } }

                        // Left accent bar when selected
                        Rectangle {
                            visible: model.selected
                            anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
                            anchors.topMargin: 4; anchors.bottomMargin: 4
                            width: 3; radius: 2
                            color: "#8B5CF6"
                        }

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            anchors.rightMargin: 10
                            spacing: 12

                            // Custom checkbox indicator
                            Rectangle {
                                width: 18; height: 18; radius: 4
                                anchors.verticalCenter: parent.verticalCenter
                                color: model.selected ? "#8B5CF6" : "transparent"
                                border.color: model.selected ? "#8B5CF6" : "#555"
                                border.width: 2
                                Behavior on color { ColorAnimation { duration: 100 } }

                                Text {
                                    anchors.centerIn: parent
                                    text: "✓"
                                    color: "white"
                                    font.pixelSize: 11
                                    font.bold: true
                                    visible: model.selected
                                }
                            }

                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 3

                                Row {
                                    spacing: 6
                                    Text {
                                        text: model.label
                                        color: model.selected ? "#E0E0FF" : "#CCC"
                                        font { bold: true; pixelSize: 13 }
                                        Behavior on color { ColorAnimation { duration: 100 } }
                                    }
                                    Rectangle {
                                        visible: model.primary
                                        width: 55; height: 16; radius: 8
                                        anchors.verticalCenter: parent.verticalCenter
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0.0; color: "#8B5CF6" }
                                            GradientStop { position: 1.0; color: "#6366F1" }
                                        }
                                        Text {
                                            anchors.centerIn: parent; text: "PRIMARY"
                                            color: "white"; font { bold: true; pixelSize: 8 }
                                        }
                                    }
                                }

                                Text {
                                    text: "Display " + model.index + " · " + model.name
                                    color: "#666"
                                    font.pixelSize: 11
                                }
                            }
                        }

                        // Click handler: toggle selection directly on model
                        MouseArea {
                            id: itemMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                var newVal = !model.selected
                                screenShareModel.setProperty(index, "selected", newVal)
                                applyBtn.forceRepaint()
                            }
                        }
                    }
                }
            }

            // Bottom buttons
            Row {
                width: parent.width
                spacing: 10

                // Stop Sharing button - only visible when already sharing
                Rectangle {
                    width: (parent.width - 10) / 2
                    height: 44; radius: 8
                    visible: babyController ? babyController.screenShareGranted : false
                    color: stopM.containsMouse ? "#5C2020" : "#3A1515"
                    border.color: Qt.rgba(1,0,0,0.2); border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text { anchors.centerIn: parent; text: "Stop Sharing"; color: "#FF6B6B"; font { bold: true; pixelSize: 14 } }
                    MouseArea {
                        id: stopM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            babyController.clearScreenShareSelection()
                            babyController.closeScreenSharePicker()
                        }
                    }
                }

                Rectangle {
                    width: (babyController && babyController.screenShareGranted) ? (parent.width - 10) / 2 : (parent.width - 10) / 2
                    height: 44; radius: 8
                    color: cancelM.containsMouse ? "#2A2A35" : "#1A1A22"
                    border.color: Qt.rgba(1,1,1,0.07); border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text { anchors.centerIn: parent; text: "Cancel"; color: "#AAA"; font { bold: true; pixelSize: 14 } }
                    MouseArea {
                        id: cancelM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: babyController.closeScreenSharePicker()
                    }
                }

                Rectangle {
                    id: applyBtn
                    width: (parent.width - 10) / 2
                    height: 44; radius: 8

                    property int count: 0

                    function update() {
                        count = selectedCount()
                    }

                    // Also re-check count whenever model changes
                    function forceRepaint() { count = selectedCount() }

                    Component.onCompleted: count = selectedCount()

                    enabled: count > 0
                    opacity: enabled ? 1.0 : 0.4
                    Behavior on opacity { NumberAnimation { duration: 150 } }

                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: applyM.containsMouse ? "#9B6FFF" : "#8B5CF6" }
                        GradientStop { position: 1.0; color: applyM.containsMouse ? "#7B76FF" : "#6366F1" }
                    }

                    Text {
                        anchors.centerIn: parent
                        text: applyBtn.count > 0
                              ? "Apply & Share (" + applyBtn.count + ")"
                              : "Apply & Share"
                        color: "white"
                        font { bold: true; pixelSize: 13 }
                    }

                    MouseArea {
                        id: applyM
                        anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        enabled: applyBtn.enabled
                        onClicked: {
                            var sel = selectedScreenIndices()
                            if (sel.length > 0) {
                                babyController.applyScreenShareSelection(JSON.stringify(sel))
                                babyController.closeScreenSharePicker()
                            }
                        }
                    }
                }
            }
        }

        // ── Resize handles ─────────────────────────────────────────────────────
        MouseArea {
            anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
            anchors.topMargin: 20; anchors.bottomMargin: 20; width: 8; cursorShape: Qt.SizeHorCursor
            property point clickPos: "0,0"
            onPressed: clickPos = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                var nw = screenPickerRoot.width + (mouse.x - clickPos.x)
                if (nw >= screenPickerRoot.minimumWidth) screenPickerRoot.width = nw
            }
        }
        MouseArea {
            anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin: 20; anchors.rightMargin: 20; height: 8; cursorShape: Qt.SizeVerCursor
            property point clickPos: "0,0"
            onPressed: clickPos = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                var nh = screenPickerRoot.height + (mouse.y - clickPos.y)
                if (nh >= screenPickerRoot.minimumHeight) screenPickerRoot.height = nh
            }
        }
        MouseArea {
            anchors.right: parent.right; anchors.bottom: parent.bottom; width: 18; height: 18
            cursorShape: Qt.SizeFDiagCursor; z: 30
            property point clickPos: "0,0"
            onPressed: clickPos = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                var nw = screenPickerRoot.width  + (mouse.x - clickPos.x)
                var nh = screenPickerRoot.height + (mouse.y - clickPos.y)
                if (nw >= screenPickerRoot.minimumWidth)  screenPickerRoot.width  = nw
                if (nh >= screenPickerRoot.minimumHeight) screenPickerRoot.height = nh
            }
            Text { anchors.centerIn: parent; text: "⇲"; color: "#8B5CF6"; font.pixelSize: 12 }
        }
    }
}














