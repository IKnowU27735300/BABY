import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

Window {
    id: socialWindow
    width: 1100
    height: 750
    minimumWidth: 700
    minimumHeight: 550
    title: "Social Network"
    visible: false
    color: "#050510"
    flags: Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint

    property var graphNodes: []
    property var graphEdges: []
    property var graphStats: ({})
    property var selectedNode: null
    property string searchQuery: ""
    property bool nodesInitialized: false
    property int maxZIndex: 100
    property var nodeMap: ({})
    property real viewW: width
    property real viewH: height
    property real graphRotation: 0
    property real graphScale: 1.0
    property point graphCenter: Qt.point(width / 2, height / 2)

    // Transform helpers
    function rotatePoint(x, y, angle) {
        var cx = graphCenter.x
        var cy = graphCenter.y
        var dx = x - cx
        var dy = y - cy
        var cos = Math.cos(angle)
        var sin = Math.sin(angle)
        return {
            x: cx + dx * cos - dy * sin,
            y: cy + dx * sin + dy * cos
        }
    }

    function buildNodeMap() {
        nodeMap = {}
        for (var i = 0; i < graphNodes.length; i++) {
            nodeMap[graphNodes[i].id] = graphNodes[i]
        }
    }

    // ── Space background ──────────────────────────────────────
    Rectangle {
        id: islandBg
        anchors.fill: parent
        clip: true

        // Mouse wheel zoom + ctrl-drag rotate on empty space
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            propagateComposedEvents: true
            onWheel: {
                if (wheel.angleDelta.y > 0)
                    graphScale = Math.min(3.0, graphScale * 1.1)
                else
                    graphScale = Math.max(0.2, graphScale / 1.1)
                edgeCanvas.requestPaint()
            }
            onPositionChanged: {
                if (pressed && (mouse.modifiers & Qt.ControlModifier)) {
                    graphRotation += (mouse.x - mouse.lastX) * 0.01
                    edgeCanvas.requestPaint()
                }
            }
        }

        // ── Edge canvas (draws all connections) ──────────────
        Canvas {
            id: edgeCanvas
            z: 1
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)

                // Apply rotation transform
                ctx.translate(width / 2, height / 2)
                ctx.rotate(graphRotation)
                ctx.scale(graphScale, graphScale)
                ctx.translate(-width / 2, -height / 2)

                for (var i = 0; i < graphEdges.length; i++) {
                    var edge = graphEdges[i]
                    var sn = nodeMap[edge.source_id]
                    var tn = nodeMap[edge.target_id]
                    if (!sn || !tn) continue

                    var x1 = sn.x, y1 = sn.y
                    var x2 = tn.x, y2 = tn.y

                    if ((x1 < -50 && x2 < -50) || (x1 > width + 50 && x2 > width + 50)) continue
                    if ((y1 < -50 && y2 < -50) || (y1 > height + 50 && y2 > height + 50)) continue

                    var isHl = selectedNode && (edge.source_id === selectedNode.id || edge.target_id === selectedNode.id)

                    var dx = x2 - x1, dy = y2 - y1
                    var dist = Math.sqrt(dx * dx + dy * dy)
                    var perpX = -dy / (dist || 1), perpY = dx / (dist || 1)
                    var midX = (x1 + x2) / 2, midY = (y1 + y2) / 2

                    // Animated curve control points
                    var wave1 = Math.sin(Date.now() * 0.001 * 0.5 + i * 1.7) * dist * 0.12
                    var wave2 = Math.cos(Date.now() * 0.001 * 0.4 + i * 2.3) * dist * 0.10
                    var cp1x = midX + perpX * wave1
                    var cp1y = midY + perpY * wave1
                    var cp2x = midX + perpX * wave2
                    var cp2y = midY + perpY * wave2

                    if (isHl) {
                        ctx.shadowColor = "#8b5cf6"
                        ctx.shadowBlur = 10
                        ctx.strokeStyle = Qt.rgba(167/255, 139/255, 250/255, 0.8)
                        ctx.lineWidth = 2.5
                    } else {
                        ctx.shadowBlur = 0
                        var wave3 = (Math.sin(Date.now() * 0.001 * 0.7 + i * 0.2) + 1) / 2
                        ctx.strokeStyle = Qt.rgba(100/255, 100/255, 160/255, 0.12 + wave3 * 0.06)
                        ctx.lineWidth = 0.8
                    }

                    ctx.beginPath()
                    ctx.moveTo(x1, y1)
                    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, x2, y2)
                    ctx.stroke()
                    ctx.shadowBlur = 0

                    // Traveling particle on highlighted edges
                    if (isHl) {
                        var t = (Math.sin(Date.now() * 0.002 + i) + 1) / 2
                        var mt = 1 - t
                        var px = mt*mt*mt*x1 + 3*mt*mt*t*cp1x + 3*mt*t*t*cp2x + t*t*t*x2
                        var py = mt*mt*mt*y1 + 3*mt*mt*t*cp1y + 3*mt*t*t*cp2y + t*t*t*y2
                        ctx.beginPath()
                        ctx.arc(px, py, 2.5, 0, Math.PI * 2)
                        ctx.fillStyle = "#c4b5fd"
                        ctx.fill()
                    }
                }
            }
        }

        // ── Node container (QML Items with GPU transform) ────
        Item {
            id: nodeContainer
            z: 2
            anchors.fill: parent

            transform: [
                Translate { x: width / 2; y: height / 2 },
                Rotation { angle: graphRotation * 180 / Math.PI },
                Scale { xScale: graphScale; yScale: graphScale },
                Translate { x: -width / 2; y: -height / 2 }
            ]

            Repeater {
                id: nodeRepeater
                model: graphNodes.length

                Item {
                    id: nodeItem
                    property int nodeIdx: index
                    property real nodeX: graphNodes[index].x
                    property real nodeY: graphNodes[index].y
                    property bool isDragging: false
                    property bool isDimmed: searchQuery.length > 0 && graphNodes[index].name.toLowerCase().indexOf(searchQuery) < 0
                    property bool isSelected: selectedNode && selectedNode.id === graphNodes[index].id
                    property real driftPhase: Math.random() * Math.PI * 2
                    property real driftSpeedX: (Math.random() - 0.5) * 0.3
                    property real driftSpeedY: (Math.random() - 0.5) * 0.3

                    x: nodeX
                    y: nodeY
                    width: 40
                    height: 50
                    z: isDragging ? 999 : (isSelected ? 500 : nodeIdx + 100)

                    Behavior on x { NumberAnimation { duration: isDragging ? 0 : 800; easing.type: Easing.OutQuad } }
                    Behavior on y { NumberAnimation { duration: isDragging ? 0 : 800; easing.type: Easing.OutQuad } }

                    // Idle drift animation
                    Timer {
                        interval: 50
                        running: nodesInitialized && !nodeItem.isDragging
                        repeat: true
                        onTriggered: {
                            nodeItem.driftPhase += 0.02
                            var dx = Math.sin(nodeItem.driftPhase * nodeItem.driftSpeedX + nodeItem.driftPhase) * 0.4
                            var dy = Math.cos(nodeItem.driftPhase * nodeItem.driftSpeedY + nodeItem.driftPhase * 0.7) * 0.3

                            var newX = nodeItem.nodeX + dx
                            var newY = nodeItem.nodeY + dy

                            // Boundary containment
                            newX = Math.max(20, Math.min(viewW - 20, newX))
                            newY = Math.max(20, Math.min(viewH - 20, newY))

                            nodeItem.nodeX = newX
                            nodeItem.nodeY = newY
                            graphNodes[nodeItem.nodeIdx].x = newX
                            graphNodes[nodeItem.nodeIdx].y = newY

                            edgeCanvas.requestPaint()
                        }
                    }

                    // Node visual
                    Rectangle {
                        id: nodeVisual
                        width: 10; height: 10; radius: 5
                        anchors.centerIn: parent
                        color: graphNodes[nodeItem.nodeIdx].color || "#8b5cf6"
                        opacity: nodeItem.isDimmed ? 0.15 : 1.0

                        // Glow
                        layer.enabled: true
                        layer.effect: null

                        // Shadow
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.width + 2; height: parent.height + 2; radius: (parent.width + 2) / 2
                            color: "black"
                            opacity: 0.3
                            z: -1
                            anchors.verticalCenterOffset: 2
                            anchors.horizontalCenterOffset: 1
                        }

                        // Specular highlight
                        Rectangle {
                            width: parent.width * 0.35; height: parent.height * 0.35
                            radius: width / 2
                            color: "white"
                            opacity: 0.3
                            anchors.top: parent.top
                            anchors.left: parent.left
                            anchors.topMargin: 1.5
                            anchors.leftMargin: 1.5
                        }
                    }

                    // Label pill
                    Rectangle {
                        id: labelPill
                        visible: !nodeItem.isDimmed
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.top
                        anchors.bottomMargin: 4
                        width: labelText.width + 12
                        height: 16
                        radius: 8
                        color: nodeItem.isSelected ? Qt.rgba(139/255, 92/255, 246/255, 0.3) : Qt.rgba(15/255, 15/255, 25/255, 0.85)
                        border.color: nodeItem.isSelected ? Qt.rgba(139/255, 92/255, 246/255, 0.5) : Qt.rgba(255/255, 255/255, 255/255, 0.08)
                        border.width: 0.5

                        Text {
                            id: labelText
                            anchors.centerIn: parent
                            text: {
                                var n = graphNodes[nodeItem.nodeIdx].name
                                return n.length > 14 ? n.substring(0, 14) + ".." : n
                            }
                            color: nodeItem.isSelected ? "#e0d0ff" : "#e8e8f0"
                            font.pixelSize: 9
                            font.family: "Segoe UI"
                            font.bold: nodeItem.isSelected
                        }
                    }

                    // Drag handle (entire node area)
                    MouseArea {
                        id: nodeMouseArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: nodeItem.isDragging ? Qt.ClosedHandCursor : (containsMouse ? Qt.PointingHandCursor : Qt.ArrowCursor)
                        preventStealing: true

                        property real dragStartX: 0
                        property real dragStartY: 0
                        property real nodeStartX: 0
                        property real nodeStartY: 0

                        onPressed: {
                            dragStartX = mouse.x
                            dragStartY = mouse.y
                            nodeStartX = nodeItem.nodeX
                            nodeStartY = nodeItem.nodeY
                            nodeItem.isDragging = true
                            nodeItem.z = 999

                            selectedNode = graphNodes[nodeItem.nodeIdx]
                            neuralBackend.selectNode(graphNodes[nodeItem.nodeIdx].id)
                            edgeCanvas.requestPaint()
                        }

                        onPositionChanged: {
                            if (!nodeItem.isDragging) return

                            var dx = mouse.x - dragStartX
                            var dy = mouse.y - dragStartY
                            var newX = nodeStartX + dx
                            var newY = nodeStartY + dy

                            // Boundary containment during drag
                            newX = Math.max(10, Math.min(viewW - 10, newX))
                            newY = Math.max(10, Math.min(viewH - 10, newY))

                            nodeItem.nodeX = newX
                            nodeItem.nodeY = newY
                            graphNodes[nodeItem.nodeIdx].x = newX
                            graphNodes[nodeItem.nodeIdx].y = newY

                            edgeCanvas.requestPaint()
                        }

                        onReleased: {
                            nodeItem.isDragging = false
                            edgeCanvas.requestPaint()
                        }
                    }

                    // Glow ring for selected
                    Rectangle {
                        visible: nodeItem.isSelected
                        width: 18; height: 18; radius: 9
                        anchors.centerIn: parent
                        color: "transparent"
                        border.color: Qt.rgba(167/255, 139/255, 250/255, 0.5)
                        border.width: 1.5
                        SequentialAnimation on opacity {
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.3; duration: 800 }
                            NumberAnimation { to: 0.8; duration: 800 }
                        }
                    }
                }
            }
        }

        // ── Glass panel - search ──────────────────────────────
        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.margins: 16
            width: searchRow.width + 28; height: 36; radius: 12
            z: 20

            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(30/255, 30/255, 50/255, 0.9) }
                GradientStop { position: 1.0; color: Qt.rgba(20/255, 20/255, 35/255, 0.95) }
            }
            border.color: searchField.activeFocus ? Qt.rgba(139/255, 92/255, 246/255, 0.6) : Qt.rgba(255/255, 255/255, 255/255, 0.08)
            border.width: 1

            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: parent.height * 0.4; radius: parent.radius
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(255/255, 255/255, 255/255, 0.04) }
                    GradientStop { position: 1.0; color: Qt.rgba(255/255, 255/255, 255/255, 0) }
                }
            }

            Row {
                id: searchRow
                anchors.centerIn: parent
                spacing: 8
                Text { text: "\uD83D\uDD0D"; font.pixelSize: 13; color: "#888"; anchors.verticalCenter: parent.verticalCenter }
                TextInput {
                    id: searchField
                    width: 120
                    color: "#e0e0f0"
                    font.pixelSize: 12
                    font.family: "Segoe UI"
                    clip: true
                    verticalAlignment: TextInput.AlignVCenter
                    onTextChanged: { searchQuery = text.toLowerCase() }
                    Text {
                        visible: !searchField.text && !searchField.activeFocus
                        text: "Search nodes..."
                        color: "#555"
                        font.pixelSize: 12
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }

        // ── Glass panel - node details ────────────────────────
        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.leftMargin: 16
            anchors.topMargin: 62
            visible: selectedNode !== null
            width: 230; height: selCol.height + 24; radius: 14
            z: 20

            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(25/255, 25/255, 45/255, 0.92) }
                GradientStop { position: 1.0; color: Qt.rgba(18/255, 18/255, 30/255, 0.96) }
            }
            border.color: Qt.rgba(139/255, 92/255, 246/255, 0.3)
            border.width: 1

            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: parent.height * 0.35; radius: parent.radius
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(255/255, 255/255, 255/255, 0.03) }
                    GradientStop { position: 1.0; color: Qt.rgba(255/255, 255/255, 255/255, 0) }
                }
            }

            Column {
                id: selCol
                anchors { left: parent.left; right: parent.right; margins: 12; top: parent.top; topMargin: 12 }
                spacing: 8

                Row {
                    spacing: 10
                    Rectangle {
                        width: 32; height: 32; radius: 16
                        color: selectedNode ? selectedNode.color : "#888"
                        border.color: Qt.rgba(255/255, 255/255, 255/255, 0.2)
                        border.width: 1
                        Text { anchors.centerIn: parent; text: selectedNode ? selectedNode.icon : ""; font.pixelSize: 16 }
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        Text { text: selectedNode ? selectedNode.name : ""; color: "#f0f0ff"; font.pixelSize: 13; font.bold: true }
                        Text { text: selectedNode ? selectedNode.entity_type : ""; color: "#8888aa"; font.pixelSize: 10 }
                    }
                }

                Rectangle { width: parent.width; height: 1; color: Qt.rgba(255/255, 255/255, 255/255, 0.06) }

                Text { text: "Connected to:"; color: "#a78bfa"; font.pixelSize: 10; font.bold: true }

                Repeater {
                    model: {
                        if (!selectedNode) return []
                        var connected = []
                        for (var i = 0; i < graphEdges.length; i++) {
                            var e = graphEdges[i]
                            var other = null
                            if (e.source_id === selectedNode.id) other = nodeMap[e.target_id]
                            else if (e.target_id === selectedNode.id) other = nodeMap[e.source_id]
                            if (other) connected.push({name: other.name, color: other.color, icon: other.icon, rel: e.relationship})
                        }
                        return connected.slice(0, 6)
                    }
                    Row {
                        spacing: 8
                        Rectangle {
                            width: 18; height: 18; radius: 9
                            color: modelData.color
                            border.color: Qt.rgba(255/255, 255/255, 255/255, 0.15)
                            border.width: 0.5
                            anchors.verticalCenter: parent.verticalCenter
                            Text { anchors.centerIn: parent; text: modelData.icon; font.pixelSize: 9 }
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            Text { text: modelData.name; color: "#ccccdd"; font.pixelSize: 10 }
                            Text { text: modelData.rel; color: "#666680"; font.pixelSize: 8 }
                        }
                    }
                }

                Rectangle { width: parent.width; height: 1; color: Qt.rgba(255/255, 255/255, 255/255, 0.06) }

                Repeater {
                    model: selectedNode ? Object.keys(selectedNode.attributes || {}).slice(0, 4) : []
                    Row {
                        spacing: 6
                        Text { text: modelData + ":"; color: "#7777aa"; font.pixelSize: 9 }
                        Text {
                            text: {
                                if (!selectedNode || !selectedNode.attributes) return ""
                                var v = selectedNode.attributes[modelData]
                                return typeof v === "object" ? JSON.stringify(v) : String(v)
                            }
                            color: "#aaaaBB"; font.pixelSize: 9; width: 155; elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        // ── Glass panel - close + zoom ────────────────────────
        Column {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 16
            spacing: 6
            z: 20

            Rectangle {
                width: 36; height: 36; radius: 10
                gradient: Gradient {
                    GradientStop { position: 0.0; color: closeMa.containsMouse ? Qt.rgba(180/255, 50/255, 50/255, 0.9) : Qt.rgba(40/255, 40/255, 60/255, 0.9) }
                    GradientStop { position: 1.0; color: closeMa.containsMouse ? Qt.rgba(150/255, 40/255, 40/255, 0.95) : Qt.rgba(25/255, 25/255, 40/255, 0.95) }
                }
                border.color: closeMa.containsMouse ? Qt.rgba(255/255, 80/255, 80/255, 0.5) : Qt.rgba(255/255, 255/255, 255/255, 0.08)
                border.width: 1
                Text { anchors.centerIn: parent; text: "\u2715"; color: closeMa.containsMouse ? "#ff8888" : "#ccccdd"; font.pixelSize: 14; font.bold: true }
                MouseArea {
                    id: closeMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: socialWindow.visible = false
                }
            }

            Repeater {
                model: [
                    {action: "zoomIn", icon: "+"},
                    {action: "zoomOut", icon: "\u2212"},
                    {action: "reset", icon: "\u2299"}
                ]
                Rectangle {
                    width: 36; height: 36; radius: 10
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: zoomMa.pressed ? Qt.rgba(80/255, 60/255, 160/255, 0.9) : Qt.rgba(40/255, 40/255, 60/255, 0.9) }
                        GradientStop { position: 1.0; color: zoomMa.pressed ? Qt.rgba(60/255, 45/255, 130/255, 0.95) : Qt.rgba(25/255, 25/255, 40/255, 0.95) }
                    }
                    border.color: zoomMa.containsMouse ? Qt.rgba(139/255, 92/255, 246/255, 0.4) : Qt.rgba(255/255, 255/255, 255/255, 0.08)
                    border.width: 1

                    Rectangle {
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                        height: parent.height * 0.45; radius: parent.radius
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: Qt.rgba(255/255, 255/255, 255/255, 0.06) }
                            GradientStop { position: 1.0; color: Qt.rgba(255/255, 255/255, 255/255, 0) }
                        }
                    }

                    Text { anchors.centerIn: parent; text: modelData.icon; color: "#e0e0f0"; font.pixelSize: 15; font.bold: true }
                    MouseArea {
                        id: zoomMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (modelData.action === "zoomIn") {
                                graphScale = Math.min(3.0, graphScale * 1.2)
                                edgeCanvas.requestPaint()
                            } else if (modelData.action === "zoomOut") {
                                graphScale = Math.max(0.2, graphScale / 1.2)
                                edgeCanvas.requestPaint()
                            } else if (modelData.action === "reset") {
                                // Reset all node positions to random
                                for (var i = 0; i < graphNodes.length; i++) {
                                    graphNodes[i].x = 80 + Math.random() * 900
                                    graphNodes[i].y = 80 + Math.random() * 600
                                }
                                graphScale = 1.0
                                graphRotation = 0
                                // Force node items to reposition
                                var tmp = graphNodes
                                graphNodes = []
                                graphNodes = tmp
                                edgeCanvas.requestPaint()
                            }
                        }
                    }
                }
            }
        }

        // ── Glass panel - Social label ────────────────────────
        Rectangle {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.margins: 16
            width: 170; height: 44; radius: 12
            z: 20

            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(30/255, 30/255, 50/255, 0.9) }
                GradientStop { position: 1.0; color: Qt.rgba(20/255, 20/255, 35/255, 0.95) }
            }
            border.color: Qt.rgba(139/255, 92/255, 246/255, 0.2)
            border.width: 1

            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: parent.height * 0.4; radius: parent.radius
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(255/255, 255/255, 255/255, 0.04) }
                    GradientStop { position: 1.0; color: Qt.rgba(255/255, 255/255, 255/255, 0) }
                }
            }

            Text {
                anchors.centerIn: parent
                text: "Social"
                color: "#e0e0f0"
                font.pixelSize: 17
                font.bold: true
                font.family: "Segoe UI Variable"
            }
        }

        // ── Glass panel - stats ───────────────────────────────
        Rectangle {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.leftMargin: 16
            anchors.bottomMargin: 68
            width: 190; height: 30; radius: 10
            z: 20

            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(25/255, 25/255, 40/255, 0.85) }
                GradientStop { position: 1.0; color: Qt.rgba(18/255, 18/255, 30/255, 0.9) }
            }
            border.color: Qt.rgba(255/255, 255/255, 255/255, 0.06)
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: graphNodes.length + " nodes \u00b7 " + graphEdges.length + " connections"
                color: "#666680"
                font.pixelSize: 10
            }
        }

        Connections {
            target: neuralBackend
            function onGraphDataReady(nodes, edges, stats) {
                graphNodes = nodes
                graphEdges = edges
                graphStats = stats || {}
                nodesInitialized = true
                buildNodeMap()
                edgeCanvas.requestPaint()
            }
        }

        Component.onCompleted: {
            neuralBackend.refreshGraph()
        }
    }
}














