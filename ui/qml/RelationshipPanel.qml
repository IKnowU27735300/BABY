import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: relationshipPanel

    property var relationships: []
    property bool collapsed: false
    property string typeColor_sequential: "#22c55e"
    property string typeColor_causal: "#f59e0b"
    property string typeColor_conditional: "#3b82f6"
    property string typeColor_parallel: "#8b5cf6"
    property string typeColor_contextual: "#06b6d4"
    property string typeColor_contradictory: "#ef4444"
    property string typeColor_independent: "#6b7280"

    function getTypeColor(type) {
        switch(type) {
            case "SEQUENTIAL": return typeColor_sequential;
            case "CAUSAL": return typeColor_causal;
            case "CONDITIONAL": return typeColor_conditional;
            case "PARALLEL": return typeColor_parallel;
            case "CONTEXTUAL": return typeColor_contextual;
            case "CONTRADICTORY": return typeColor_contradictory;
            case "INDEPENDENT": return typeColor_independent;
            default: return "#6b7280";
        }
    }

    width: parent ? parent.width : 300
    height: collapsed ? 40 : Math.min(contentColumn.implicitHeight + 20, 300)
    color: "#1a1a2e"
    radius: 12
    border.color: "#333355"
    border.width: 1
    clip: true

    Behavior on height {
        NumberAnimation { duration: 200; easing.type: Easing.InOutQuad }
    }

    ColumnLayout {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: 10
        spacing: 6

        RowLayout {
            Layout.fillWidth: true

            Rectangle {
                width: 8
                height: 8
                radius: 4
                color: relationships.length > 0 ? "#22c55e" : "#6b7280"
            }

            Text {
                text: "Relationships"
                color: "#ffffff"
                font.pixelSize: 13
                font.bold: true
                Layout.fillWidth: true
            }

            Text {
                text: relationships.length.toString()
                color: "#aaaaaa"
                font.pixelSize: 11
            }

            Rectangle {
                width: 20
                height: 20
                radius: 10
                color: "#333355"

                Text {
                    anchors.centerIn: parent
                    text: collapsed ? "+" : "-"
                    color: "#ffffff"
                    font.pixelSize: 14
                    font.bold: true
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: collapsed = !collapsed
                }
            }
        }

        Repeater {
            model: collapsed ? 0 : relationships

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: itemColumn.implicitHeight + 12
                color: "#0d1117"
                radius: 8
                border.color: getTypeColor(modelData.type || "INDEPENDENT")
                border.width: 1

                ColumnLayout {
                    id: itemColumn
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true

                        Rectangle {
                            Layout.preferredWidth: badgeText.implicitWidth + 12
                            Layout.preferredHeight: 20
                            radius: 4
                            color: getTypeColor(modelData.type || "INDEPENDENT")

                            Text {
                                id: badgeText
                                anchors.centerIn: parent
                                text: modelData.type || "?"
                                color: "#ffffff"
                                font.pixelSize: 9
                                font.bold: true
                            }
                        }

                        Text {
                            text: Math.round((modelData.confidence || 0) * 100) + "%"
                            color: "#aaaaaa"
                            font.pixelSize: 10
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    Text {
                        text: (modelData.action_a || "") + " → " + (modelData.action_b || "")
                        color: "#cccccc"
                        font.pixelSize: 10
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }

                    Text {
                        text: modelData.explanation || ""
                        color: "#888888"
                        font.pixelSize: 9
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                }
            }
        }

        Text {
            text: "No relationships detected"
            color: "#555555"
            font.pixelSize: 10
            visible: relationships.length === 0 && !collapsed
            Layout.alignment: Qt.AlignHCenter
        }
    }

    Connections {
        target: typeof islandController !== "undefined" ? islandController : null

        function onRelationshipsReady(results) {
            relationships = results
        }
    }
}














