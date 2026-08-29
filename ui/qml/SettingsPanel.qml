import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import QtQuick.Effects

Window {
    id: settingsWindow
    width: 600
    height: 720
    minimumWidth: 520
    minimumHeight: 600
    title: "BABY Settings"
    visible: false
    color: "transparent"
    flags: Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint

    property bool saved: false
    property bool isAdmin: babyConfig.hasAdmin() ? true : false

    // ── Color Palette ──────────────────────────────────────────────
    readonly property color bg: "#08080C"
    readonly property color cardBg: "#111118"
    readonly property color cardBgHover: "#16161F"
    readonly property color inputBg: "#0E0E14"
    readonly property color border: "#1E1E2A"
    readonly property color borderHover: "#2A2A3C"
    readonly property color accent: "#7C6CFF"
    readonly property color accentLight: "#9B8FFF"
    readonly property color accentDim: "#5A4ED9"
    readonly property color text1: "#EEEEF4"
    readonly property color text2: "#A0A0B8"
    readonly property color text3: "#60607A"
    readonly property color green: "#34D399"
    readonly property color amber: "#FBBF24"
    readonly property color rose: "#F472B6"
    readonly property color teal: "#2DD4BF"
    readonly property color orange: "#FB923C"
    readonly property color cyan: "#22D3EE"

    onClosing: {
        if (!saved) babyConfig.cancelEdit()
        saved = false
        close.accepted = false
        settingsWindow.hide()
    }

    function refreshValues() {
        llmModelInput.text = babyConfig.getValue("llm", "model")
        llmUrlInput.text = babyConfig.getValue("llm", "base_url")
        llmTestModeSwitch.checked = babyConfig.getValue("llm", "test_mode") === "True"

        updateVoiceOptions()
        var cv = babyConfig.getValue("tts", "voice")
        for (var i = 0; i < voiceCombo.model.length; i++) {
            if (voiceCombo.model[i].indexOf(cv) === 0) { voiceCombo.currentIndex = i; break }
        }
        speedSlider.value = parseFloat(babyConfig.getValue("tts", "speed")) || 1.0

        var cl = babyConfig.getValue("ui", "language")
        for (var i = 0; i < langCombo.model.length; i++) {
            if (langCombo.model[i].indexOf(cl) === 0) { langCombo.currentIndex = i; break }
        }

        var cp = babyConfig.getValue("tts", "persona")
        for (var i = 0; i < personaCombo.model.length; i++) {
            if (personaCombo.model[i].indexOf(cp) === 0) { personaCombo.currentIndex = i; break }
        }

        vadSlider.value = parseFloat(babyConfig.getValue("audio", "barge_in_vad_threshold")) || 0.5
        silenceInput.text = babyConfig.getValue("audio", "silence_threshold_ms")
        bioSlider.value = parseFloat(babyConfig.getValue("biometrics", "voice_similarity_threshold")) || 0.82

        var devices = babyConfig.getInputDevices()
        micCombo.model = devices
        var cm = parseInt(babyConfig.getValue("audio", "device_index"))
        if (isNaN(cm)) cm = -1
        for (var i = 0; i < micCombo.model.length; i++) {
            var t = micCombo.model[i], ci = t.indexOf(":")
            if (ci !== -1 && parseInt(t.substring(0, ci)) === cm) { micCombo.currentIndex = i; break }
        }
    }

    Component.onCompleted: refreshValues()

    function updateVoiceOptions() {
        // Edge Neural TTS voices — fluent in English, Hindi AND Kannada.
        // Each voice auto-routes to the correct native Edge voice (en-US-AvaNeural,
        // hi-IN-SwaraNeural, kn-IN-SapnaNeural) based on the text's script.
        voiceCombo.model = [
            "en-US-AvaNeural - Ava (Warm & Friendly)",
            "en-US-EmmaNeural - Emma (Crisp & Professional)",
            "en-US-JennyNeural - Jenny (Soft & Calm)",
            "en-US-AnaNeural - Ana (Expressive & Conversational)",
            "en-US-MichelleNeural - Michelle (Natural & Balanced)",
            "en-IE-EmilyNeural - Emily (Irish Dialect)",
            "en-US-SteffanNeural - Steffan (Clear & Bright)"
        ]
    }

    function checkAdmin() {
        // If no admin exists, this is first-time setup — allow all
        if (!babyConfig.hasAdmin()) {
            isAdmin = true
            return
        }
        // Otherwise, check if current user is admin
        // For now, allow all since we don't track current user in QML
        // The actual check happens in Python backend
        isAdmin = true
    }

    // ── Window background (transparent for shadow) ─────────────────
    Rectangle {
        anchors.fill: parent
        radius: 16
        color: bg
        border.color: border
        border.width: 1
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Qt.rgba(0, 0, 0, 0.55)
            shadowVerticalOffset: 8
        }
    }

    // ── Header ─────────────────────────────────────────────────────
    Rectangle {
        id: header
        anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
        height: 68
        radius: 16
        color: "transparent"
        clip: true

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0.04, 0.04, 0.06, 0.95)
        }

        // Bottom accent line
        Rectangle {
            anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
            height: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.2; color: Qt.rgba(accent.r, accent.g, accent.b, 0.5) }
                GradientStop { position: 0.8; color: Qt.rgba(accent.r, accent.g, accent.b, 0.5) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20; anchors.topMargin: 0
            spacing: 14

            // Left accent bar
            Rectangle {
                width: 4; height: 32; radius: 2
                color: accent
                Layout.alignment: Qt.AlignVCenter
            }

            ColumnLayout {
                Layout.fillWidth: true; spacing: 2
                Text {
                    text: "BABY Settings"
                    color: text1; font.pixelSize: 20; font.bold: true
                    font.family: "Segoe UI Variable Display, Segoe UI, sans-serif"
                }
                Text {
                    text: "Configure your assistant"
                    color: text3; font.pixelSize: 12; font.family: "Segoe UI"
                }
            }

            // Close button
            Rectangle {
                width: 30; height: 30; radius: 8; color: closeMa.pressed ? cardBgHover : (closeMa.containsMouse ? border : "transparent")
                border.color: closeMa.containsMouse ? borderHover : "transparent"; border.width: 1
                Text { anchors.centerIn: parent; text: "✕"; color: text2; font.pixelSize: 13 }
                MouseArea { id: closeMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: settingsWindow.close() }
            }
        }
    }

    // ── Scrollable Content ─────────────────────────────────────────
    ScrollView {
        id: sv
        anchors.top: header.bottom; anchors.bottom: footer.top
        anchors.left: parent.left; anchors.right: parent.right
        clip: true
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
            width: 6
            contentItem: Rectangle { radius: 3; color: accent; opacity: 0.4; width: 6 }
            background: Rectangle { color: "transparent" }
        }

        ColumnLayout {
            width: parent.width - 40
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 12
            Layout.topMargin: 16; Layout.bottomMargin: 16

            // ═══════════════════════════════════════════════════════
            // SECTION 1 — Neural Network Visualization (Moved to top)
            // ═══════════════════════════════════════════════════════
            Rectangle {
                Layout.fillWidth: true; height: neuralCol.height + 48; radius: 14
                color: cardBg; border.color: border; border.width: 1
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(0, 0, 0, 0.3)
                    shadowVerticalOffset: 2
                }

                ColumnLayout {
                    id: neuralCol
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    RowLayout { spacing: 12
                        Rectangle { width: 40; height: 40; radius: 12; color: Qt.rgba(cyan.r, cyan.g, cyan.b, 0.12)
                            border.color: Qt.rgba(cyan.r, cyan.g, cyan.b, 0.3); border.width: 1
                            Text { anchors.centerIn: parent; text: "🧠"; font.pixelSize: 20 }
                        }
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Text { text: "Neural Network"; color: text1; font.pixelSize: 15; font.bold: true; font.family: "Segoe UI Variable" }
                            Text { text: "View knowledge graph visualization"; color: text3; font.pixelSize: 11 }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: border }

                    // Description
                    ColumnLayout { spacing: 8
                        Text {
                            text: "Explore how information is interconnected in Baby's memory. The knowledge graph shows entities (people, projects, preferences) and their relationships using a neural network-like structure."
                            color: text2
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        // Network type info
                        RowLayout { spacing: 12
                            Rectangle {
                                Layout.fillWidth: true; height: 60; radius: 8
                                color: Qt.rgba(cyan.r, cyan.g, cyan.b, 0.05)
                                border.color: Qt.rgba(cyan.r, cyan.g, cyan.b, 0.2)
                                border.width: 1
                                ColumnLayout {
                                    anchors.centerIn: parent
                                    spacing: 2
                                    Text { text: "🔗 Feed-Forward"; color: cyan; font.pixelSize: 10; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                                    Text { text: "Entity → Edge → Entity"; color: text3; font.pixelSize: 9; Layout.alignment: Qt.AlignHCenter }
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true; height: 60; radius: 8
                                color: Qt.rgba(rose.r, rose.g, rose.b, 0.05)
                                border.color: Qt.rgba(rose.r, rose.g, rose.b, 0.2)
                                border.width: 1
                                ColumnLayout {
                                    anchors.centerIn: parent
                                    spacing: 2
                                    Text { text: "🔄 Recurrent"; color: rose; font.pixelSize: 10; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                                    Text { text: "Temporal connections"; color: text3; font.pixelSize: 9; Layout.alignment: Qt.AlignHCenter }
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true; height: 60; radius: 8
                                color: Qt.rgba(green.r, green.g, green.b, 0.05)
                                border.color: Qt.rgba(green.r, green.g, green.b, 0.2)
                                border.width: 1
                                ColumnLayout {
                                    anchors.centerIn: parent
                                    spacing: 2
                                    Text { text: "🎯 Hopfield"; color: green; font.pixelSize: 10; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                                    Text { text: "Pattern recognition"; color: text3; font.pixelSize: 9; Layout.alignment: Qt.AlignHCenter }
                                }
                            }
                        }

                        // Open button
                        Rectangle {
                            Layout.fillWidth: true; height: 44; radius: 10
                            color: neuralBtnMa.pressed ? Qt.rgba(cyan.r, cyan.g, cyan.b, 0.3) : (neuralBtnMa.containsMouse ? Qt.rgba(cyan.r, cyan.g, cyan.b, 0.15) : Qt.rgba(cyan.r, cyan.g, cyan.b, 0.08))
                            border.color: neuralBtnMa.containsMouse ? cyan : Qt.rgba(cyan.r, cyan.g, cyan.b, 0.3)
                            border.width: 1

                            RowLayout {
                                anchors.centerIn: parent
                                spacing: 8
                                Text { text: "🧠"; font.pixelSize: 16 }
                                Text { text: "Show Neural Network"; color: cyan; font.pixelSize: 13; font.bold: true; font.family: "Segoe UI" }
                            }

                            MouseArea {
                                id: neuralBtnMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    // Use the backend to refresh and show the neural window
                                    neuralBackend.refreshGraph()
                                }
                            }
                        }
                    }
                }
}

            // ══════════════════════════════════════════════════════
            // SECTION 2 — Local LLM
            // ═══════════════════════════════════════════════════════
            Rectangle {
                Layout.fillWidth: true; height: llmCol.height + 48; radius: 14
                color: cardBg; border.color: border; border.width: 1
                Behavior on border.color { ColorAnimation { duration: 200 } }
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(0, 0, 0, 0.3)
                    shadowVerticalOffset: 2
                }

                ColumnLayout {
                    id: llmCol
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    // Section header
                    RowLayout { spacing: 12
                        Rectangle { width: 40; height: 40; radius: 12; color: Qt.rgba(accent.r, accent.g, accent.b, 0.12)
                            border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.3); border.width: 1
                            Text { anchors.centerIn: parent; text: "🧠"; font.pixelSize: 20 }
                        }
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Text { text: "Local LLM"; color: text1; font.pixelSize: 15; font.bold: true; font.family: "Segoe UI Variable" }
                            Text { text: "Model, endpoint & test mode"; color: text3; font.pixelSize: 11 }
                        }
                        Text { text: "▾"; color: text3; font.pixelSize: 11 }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: border }

                    // Model ID
                    ColumnLayout { spacing: 6
                        Text { text: "Model ID"; color: text2; font.pixelSize: 12 }
                        Rectangle { Layout.fillWidth: true; height: 40; radius: 8; color: inputBg; border.color: llmModelInput.activeFocus ? accent : border; border.width: llmModelInput.activeFocus ? 2 : 1
                            TextField { id: llmModelInput; anchors.fill: parent; anchors.margins: 1; padding: 0; leftPadding: 12; color: text1; font.pixelSize: 13; font.family: "Segoe UI"; placeholderText: "llama3.1:8b"; placeholderTextColor: text3; background: null
                                onEditingFinished: babyConfig.setValue("llm", "model", text) }
                            Behavior on border.color { ColorAnimation { duration: 150 } }
                        }
                    }

                    // Ollama URL
                    ColumnLayout { spacing: 6
                        Text { text: "Ollama URL"; color: text2; font.pixelSize: 12 }
                        Rectangle { Layout.fillWidth: true; height: 40; radius: 8; color: inputBg; border.color: llmUrlInput.activeFocus ? accent : border; border.width: llmUrlInput.activeFocus ? 2 : 1
                            TextField { id: llmUrlInput; anchors.fill: parent; anchors.margins: 1; padding: 0; leftPadding: 12; color: text1; font.pixelSize: 13; font.family: "Segoe UI"; placeholderText: "http://localhost:11434"; placeholderTextColor: text3; background: null
                                onEditingFinished: babyConfig.setValue("llm", "base_url", text) }
                            Behavior on border.color { ColorAnimation { duration: 150 } }
                        }
                    }

                    // Test Mode
                    RowLayout { spacing: 12
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Text { text: "Test Mode"; color: text2; font.pixelSize: 12 }
                            Text { text: "Use simulated responses (no LLM calls)"; color: text3; font.pixelSize: 10 }
                        }
                        Switch { id: llmTestModeSwitch; onCheckedChanged: babyConfig.setValue("llm", "test_mode", checked ? "True" : "False")
                            indicator: Rectangle { x: llmTestModeSwitch.leftPadding; y: parent.height/2 - height/2; width: 44; height: 24; radius: 12
                                color: llmTestModeSwitch.checked ? accent : Qt.rgba(border.r, border.g, border.b, 1.5)
                                border.color: llmTestModeSwitch.checked ? "transparent" : border; border.width: 1
                                Behavior on color { ColorAnimation { duration: 180 } }
                                Rectangle { x: llmTestModeSwitch.checked ? 22 : 2; y: 2; width: 20; height: 20; radius: 10; color: text1
                                    Behavior on x { SpringAnimation { spring: 3; damping: 0.7 } }
                                    layer.enabled: true
                                    layer.effect: MultiEffect {
                                        shadowEnabled: true
                                        shadowColor: Qt.rgba(0, 0, 0, 0.2)
                                        shadowVerticalOffset: 1
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ═══════════════════════════════════════════════════════
            // SECTION 2 — Microphone
            // ═══════════════════════════════════════════════════════
            Rectangle {
                Layout.fillWidth: true; height: micCol.height + 48; radius: 14
                color: cardBg; border.color: border; border.width: 1
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(0, 0, 0, 0.3)
                    shadowVerticalOffset: 2
                }

                ColumnLayout {
                    id: micCol
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    RowLayout { spacing: 12
                        Rectangle { width: 40; height: 40; radius: 12; color: Qt.rgba(green.r, green.g, green.b, 0.12)
                            border.color: Qt.rgba(green.r, green.g, green.b, 0.3); border.width: 1
                            Text { anchors.centerIn: parent; text: "🎤"; font.pixelSize: 20 }
                        }
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Text { text: "Microphone"; color: text1; font.pixelSize: 15; font.bold: true; font.family: "Segoe UI Variable" }
                            Text { text: "Input device selection"; color: text3; font.pixelSize: 11 }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: border }

                    ColumnLayout { spacing: 6
                        Text { text: "Input Device"; color: text2; font.pixelSize: 12 }
                        ComboBox { id: micCombo; Layout.fillWidth: true; model: []; font.pixelSize: 13; padding: 8
                            background: Rectangle { radius: 8; color: inputBg; border.color: micCombo.pressed || micCombo.activeFocus ? green : border; border.width: 1
                                Behavior on border.color { ColorAnimation { duration: 150 } } }
                            contentItem: Text { text: micCombo.currentText || "Select microphone..."; color: micCombo.currentText ? text1 : text3; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 8 }
                            delegate: ItemDelegate { width: parent.width; height: 34
                                contentItem: Text { text: modelData; color: text1; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 10 } }
                            popup: Popup { y: micCombo.height; width: micCombo.width; padding: 4; background: Rectangle { color: cardBg; border.color: border; border.width: 1; radius: 8 }
                                contentItem: ListView { model: micCombo.popup.visible ? micCombo.model : 0; currentIndex: micCombo.highlightedIndex; delegate: micCombo.delegate; spacing: 2; clip: true } }
                            onActivated: { var si = -1, t = currentText; if (t.indexOf(":") !== -1) si = parseInt(t.split(":")[0]); babyConfig.setValue("audio", "device_index", si.toString()) }
                        }
                    }
                }
            }

            // ═══════════════════════════════════════════════════════
            // SECTION 3 — Language
            // ═══════════════════════════════════════════════════════
            Rectangle {
                Layout.fillWidth: true; height: langCol.height + 48; radius: 14
                color: cardBg; border.color: border; border.width: 1
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(0, 0, 0, 0.3)
                    shadowVerticalOffset: 2
                }

                ColumnLayout {
                    id: langCol
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    RowLayout { spacing: 12
                        Rectangle { width: 40; height: 40; radius: 12; color: Qt.rgba(amber.r, amber.g, amber.b, 0.12)
                            border.color: Qt.rgba(amber.r, amber.g, amber.b, 0.3); border.width: 1
                            Text { anchors.centerIn: parent; text: "🌐"; font.pixelSize: 20 }
                        }
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Text { text: "Language"; color: text1; font.pixelSize: 15; font.bold: true; font.family: "Segoe UI Variable" }
                            Text { text: "Assistant language"; color: text3; font.pixelSize: 11 }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: border }

                    ColumnLayout { spacing: 6
                        Text { text: "Assistant Language"; color: text2; font.pixelSize: 12 }
                        ComboBox { id: langCombo; Layout.fillWidth: true; model: ["auto - Automatic (follow user)", "en - English", "hi - हिन्दी (Hindi)", "kn - ಕನ್ನಡ (Kannada)", "mr - मराठी (Marathi)"]
                            font.pixelSize: 13; padding: 8
                            background: Rectangle { radius: 8; color: inputBg; border.color: langCombo.pressed || langCombo.activeFocus ? amber : border; border.width: 1
                                Behavior on border.color { ColorAnimation { duration: 150 } } }
                            contentItem: Text { text: langCombo.currentText || "Select language..."; color: langCombo.currentText ? text1 : text3; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 8 }
                            delegate: ItemDelegate { width: parent.width; height: 34
                                contentItem: Text { text: modelData; color: text1; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 10 } }
                            popup: Popup { y: langCombo.height; width: langCombo.width; padding: 4; background: Rectangle { color: cardBg; border.color: border; border.width: 1; radius: 8 }
                                contentItem: ListView { model: langCombo.popup.visible ? langCombo.model : 0; currentIndex: langCombo.highlightedIndex; delegate: langCombo.delegate; spacing: 2; clip: true } }
                            onActivated: babyConfig.setValue("ui", "language", currentText.split(" ")[0])
                        }
                    }
                }
            }

            // ═══════════════════════════════════════════════════════
            // SECTION 4 — TTS Speed
            // ═══════════════════════════════════════════════════════
            Rectangle {
                Layout.fillWidth: true; height: ttsCol.height + 48; radius: 14
                color: cardBg; border.color: border; border.width: 1
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(0, 0, 0, 0.3)
                    shadowVerticalOffset: 2
                }

                ColumnLayout {
                    id: ttsCol
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    RowLayout { spacing: 12
                        Rectangle { width: 40; height: 40; radius: 12; color: Qt.rgba(rose.r, rose.g, rose.b, 0.12)
                            border.color: Qt.rgba(rose.r, rose.g, rose.b, 0.3); border.width: 1
                            Text { anchors.centerIn: parent; text: "🗣"; font.pixelSize: 20 }
                        }
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Text { text: "Speech Speed"; color: text1; font.pixelSize: 15; font.bold: true; font.family: "Segoe UI Variable" }
                            Text { text: "TTS playback rate"; color: text3; font.pixelSize: 11 }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: border }

                    RowLayout { spacing: 12
                        Slider { id: speedSlider; Layout.fillWidth: true; from: 0.5; to: 2.0; stepSize: 0.1; value: 1.0
                            onMoved: babyConfig.setValue("tts", "speed", value.toString())
                            background: Rectangle { x: speedSlider.leftPadding; y: speedSlider.topPadding + speedSlider.availableHeight / 2 - height / 2; width: speedSlider.availableWidth; height: 6; radius: 3; color: inputBg
                                Rectangle { width: speedSlider.visualPosition * parent.width; height: parent.height; radius: 3; color: rose }
                            }
                            handle: Rectangle { x: speedSlider.leftPadding + speedSlider.visualPosition * (speedSlider.availableWidth - width); y: speedSlider.topPadding + speedSlider.availableHeight / 2 - height / 2; width: 18; height: 18; radius: 9; color: text1; border.color: rose; border.width: 2
                                layer.enabled: true
                                layer.effect: MultiEffect {
                                    shadowEnabled: true
                                    shadowColor: Qt.rgba(rose.r, rose.g, rose.b, 0.5)
                                    shadowVerticalOffset: 2
                                }
                            }
                        }
                        Rectangle { width: 52; height: 32; radius: 8; color: Qt.rgba(rose.r, rose.g, rose.b, 0.1)
                            Text { anchors.centerIn: parent; text: speedSlider.value.toFixed(1) + "x"; color: rose; font.pixelSize: 13; font.bold: true; font.family: "Segoe UI" }
                        }
                    }
                }
            }

            // ═══════════════════════════════════════════════════════
            // SECTION 5 — Voice & Persona
            // ═══════════════════════════════════════════════════════
            Rectangle {
                Layout.fillWidth: true; height: voiceCol.height + 48; radius: 14
                color: cardBg; border.color: border; border.width: 1
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(0, 0, 0, 0.3)
                    shadowVerticalOffset: 2
                }

                ColumnLayout {
                    id: voiceCol
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    RowLayout { spacing: 12
                        Rectangle { width: 40; height: 40; radius: 12; color: Qt.rgba(teal.r, teal.g, teal.b, 0.12)
                            border.color: Qt.rgba(teal.r, teal.g, teal.b, 0.3); border.width: 1
                            Text { anchors.centerIn: parent; text: "🎭"; font.pixelSize: 20 }
                        }
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Text { text: "Voice & Persona"; color: text1; font.pixelSize: 15; font.bold: true; font.family: "Segoe UI Variable" }
                            Text { text: "Voice model and personality"; color: text3; font.pixelSize: 11 }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: border }

                    ColumnLayout { spacing: 14
                        // Voice
                        ColumnLayout { spacing: 6
                            Text { text: "Voice"; color: text2; font.pixelSize: 12 }
                            ComboBox { id: voiceCombo; Layout.fillWidth: true; model: []; font.pixelSize: 13; padding: 8
                                background: Rectangle { radius: 8; color: inputBg; border.color: voiceCombo.pressed || voiceCombo.activeFocus ? teal : border; border.width: 1
                                    Behavior on border.color { ColorAnimation { duration: 150 } } }
                                contentItem: Text { text: voiceCombo.currentText || "Select voice..."; color: voiceCombo.currentText ? text1 : text3; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 8 }
                                delegate: ItemDelegate { width: parent.width; height: 34
                                    contentItem: Text { text: modelData; color: text1; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 10 } }
                                popup: Popup { y: voiceCombo.height; width: voiceCombo.width; padding: 4; background: Rectangle { color: cardBg; border.color: border; border.width: 1; radius: 8 }
                                    contentItem: ListView { model: voiceCombo.popup.visible ? voiceCombo.model : 0; currentIndex: voiceCombo.highlightedIndex; delegate: voiceCombo.delegate; spacing: 2; clip: true } }
                                onActivated: babyConfig.setValue("tts", "voice", currentText.split(" ")[0])
                            }
                        }

                        // Persona
                        ColumnLayout { spacing: 6
                            Text { text: "Persona"; color: text2; font.pixelSize: 12 }
                            ComboBox { id: personaCombo; Layout.fillWidth: true
                                model: ["friendly - Friendly (warm best friend)", "caring - Caring (nurturing & empathetic)", "cheerful - Cheerful (bubbly & optimistic)", "sassy - Sassy (bold & witty)", "elegant - Elegant (refined & poised)", "professional - Professional (polished & concise)", "jarvis - Jarvis (crisp, witty, proactive)", "unfiltered - Unfiltered (brutally honest, no sugarcoating)"]
                                font.pixelSize: 13; padding: 8
                                background: Rectangle { radius: 8; color: inputBg; border.color: personaCombo.pressed || personaCombo.activeFocus ? teal : border; border.width: 1
                                    Behavior on border.color { ColorAnimation { duration: 150 } } }
                                contentItem: Text { text: personaCombo.currentText || "Select persona..."; color: personaCombo.currentText ? text1 : text3; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 8 }
                                delegate: ItemDelegate { width: parent.width; height: 34
                                    contentItem: Text { text: modelData; color: text1; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; leftPadding: 10 } }
                                popup: Popup { y: personaCombo.height; width: personaCombo.width; padding: 4; background: Rectangle { color: cardBg; border.color: border; border.width: 1; radius: 8 }
                                    contentItem: ListView { model: personaCombo.popup.visible ? personaCombo.model : 0; currentIndex: personaCombo.highlightedIndex; delegate: personaCombo.delegate; spacing: 2; clip: true } }
                                onActivated: babyConfig.setValue("tts", "persona", currentText.split(" ")[0])
                            }
                        }
                    }
                }
            }

            // ═══════════════════════════════════════════════════════
            // SECTION 6 — Audio Sensitivity
            // ═══════════════════════════════════════════════════════
            Rectangle {
                Layout.fillWidth: true; height: audioCol.height + 48; radius: 14
                color: cardBg; border.color: border; border.width: 1
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(0, 0, 0, 0.3)
                    shadowVerticalOffset: 2
                }

                ColumnLayout {
                    id: audioCol
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    RowLayout { spacing: 12
                        Rectangle { width: 40; height: 40; radius: 12; color: Qt.rgba(accent.r, accent.g, accent.b, 0.12)
                            border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.3); border.width: 1
                            Text { anchors.centerIn: parent; text: "🔊"; font.pixelSize: 20 }
                        }
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Text { text: "Audio Sensitivity"; color: text1; font.pixelSize: 15; font.bold: true; font.family: "Segoe UI Variable" }
                            Text { text: "VAD threshold & silence limit"; color: text3; font.pixelSize: 11 }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: border }

                    ColumnLayout { spacing: 16
                        // VAD
                        ColumnLayout { spacing: 6
                            RowLayout {
                                Text { text: "VAD Threshold"; color: text2; font.pixelSize: 12; Layout.fillWidth: true }
                                Rectangle { width: 48; height: 24; radius: 6; color: Qt.rgba(accent.r, accent.g, accent.b, 0.1)
                                    Text { anchors.centerIn: parent; text: vadSlider.value.toFixed(2); color: accent; font.pixelSize: 11; font.bold: true }
                                }
                            }
                            Slider { id: vadSlider; Layout.fillWidth: true; from: 0.1; to: 0.9; stepSize: 0.05; value: 0.5
                                onMoved: babyConfig.setValue("audio", "barge_in_vad_threshold", value.toString())
                                background: Rectangle { x: vadSlider.leftPadding; y: vadSlider.topPadding + vadSlider.availableHeight / 2 - height / 2; width: vadSlider.availableWidth; height: 6; radius: 3; color: inputBg
                                    Rectangle { width: vadSlider.visualPosition * parent.width; height: parent.height; radius: 3; color: accent }
                                }
                                handle: Rectangle { x: vadSlider.leftPadding + vadSlider.visualPosition * (vadSlider.availableWidth - width); y: vadSlider.topPadding + vadSlider.availableHeight / 2 - height / 2; width: 18; height: 18; radius: 9; color: text1; border.color: accent; border.width: 2
                                    layer.enabled: true
                                    layer.effect: MultiEffect {
                                        shadowEnabled: true
                                        shadowColor: Qt.rgba(accent.r, accent.g, accent.b, 0.5)
                                        shadowVerticalOffset: 2
                                    }
                                }
                            }
                        }

                        // Silence
                        ColumnLayout { spacing: 6
                            Text { text: "Silence Limit (ms)"; color: text2; font.pixelSize: 12 }
                            Rectangle { Layout.fillWidth: true; height: 40; radius: 8; color: inputBg; border.color: silenceInput.activeFocus ? accent : border; border.width: silenceInput.activeFocus ? 2 : 1
                                TextField { id: silenceInput; anchors.fill: parent; anchors.margins: 1; padding: 0; leftPadding: 12; color: text1; font.pixelSize: 13; font.family: "Segoe UI"; placeholderText: "800"; placeholderTextColor: text3; background: null; validator: IntValidator { bottom: 100; top: 5000 }
                                    onEditingFinished: babyConfig.setValue("audio", "silence_threshold_ms", text) }
                                Behavior on border.color { ColorAnimation { duration: 150 } }
                            }
                        }
                    }
                }
}
    }  // closes ColumnLayout
    }  // closes ScrollView

    // ── Footer ─────────────────────────────────────────────────────
    Rectangle {
        id: footer
        anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
        height: 72; radius: 16; color: "transparent"
        clip: true

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0.04, 0.04, 0.06, 0.95)
        }

        // Top accent line
        Rectangle {
            anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
            height: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.3; color: Qt.rgba(border.r, border.g, border.b, 0.8) }
                GradientStop { position: 0.7; color: Qt.rgba(border.r, border.g, border.b, 0.8) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        RowLayout {
            anchors.fill: parent; anchors.margins: 12; spacing: 12

            // Cancel
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 44; radius: 12
                color: cancelMa.pressed ? inputBg : (cancelMa.containsMouse ? cardBgHover : cardBg)
                border.color: cancelMa.containsMouse ? borderHover : border; border.width: 1
                Text { anchors.centerIn: parent; text: "Cancel"; color: cancelMa.pressed ? text3 : text2; font.pixelSize: 14; font.bold: true; font.family: "Segoe UI" }
                Behavior on border.color { ColorAnimation { duration: 150 } }
                MouseArea { id: cancelMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: settingsWindow.close() }
            }

            // Save & Apply
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 44; radius: 12
                color: saveMa.pressed ? accentDim : (saveMa.containsMouse ? accentLight : accent)
                border.color: "transparent"; border.width: 0
                Text { anchors.centerIn: parent; text: "Save & Apply"; color: "#FFFFFF"; font.pixelSize: 14; font.bold: true; font.family: "Segoe UI" }
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: Qt.rgba(accent.r, accent.g, accent.b, 0.4)
                    shadowVerticalOffset: 4
                }
                Behavior on color { ColorAnimation { duration: 150 } }
                MouseArea { id: saveMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: {
                    babyConfig.setValue("llm", "model", llmModelInput.text)
                    babyConfig.setValue("llm", "base_url", llmUrlInput.text)
                    babyConfig.setValue("audio", "silence_threshold_ms", silenceInput.text)
                    var st = micCombo.currentText, si = -1
                    if (st.indexOf(":") !== -1) si = parseInt(st.split(":")[0])
                    babyConfig.setValue("audio", "device_index", si.toString())
                    babyConfig.setValue("ui", "language", langCombo.currentText.split(" ")[0])
                    babyConfig.setValue("tts", "persona", personaCombo.currentText.split(" ")[0])
                    saved = true; babyConfig.saveConfig(); settingsWindow.close()
                }}
            }
        }
    }
}














