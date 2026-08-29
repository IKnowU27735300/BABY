# BABY — Local AI Desktop Assistant

A 100% local, private AI desktop assistant for Windows. Wake-word activation,
voice conversation, on-screen "Dynamic Island" UI, file/app/browser automation,
screen vision (screenshots + OCR), biometrics, and an autonomous skill-learning
pipeline — all running on your machine with no data leaving the device.

> Requires **Windows** (uses `os.startfile`, PowerShell, `ms-settings:`, `winreg`)
> and **Python 3.11+**.

---

## Quick start

```bash
cd "S:\CODE\BABY"

# 1. Create the virtual environment (one time)
python -m venv .venv
.\.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install opencv-python        # listed in the docs as a separate step

# 3. (Recommended for dev/testing) Run fully offline — no Ollama needed
#    Edit config.yaml and set:  llm: test_mode: true
#    ...or just run it.

# 4. Run
python main.py
```

### Gemini TTS (for Hindi / Kannada / Marathi speech output)

Kokoro only ships a Hindi voice — it **cannot** render Kannada or Marathi.
To let BABY *speak* those languages, use the Gemini TTS engine:

1. In the project folder create a git-ignored file named **`.env`**:
   ```ini
   GEMINI_API_KEY=your-key-here
   ```
2. In `config.yaml` set:
   ```yaml
   tts:
     engine: gemini
   ```
The key is read (priority: env var → `config.yaml` `tts.gemini_api_key` → `.env`)
without ever being hardcoded in source. `.env` and `config.yaml` are git-ignored,
so the key is never committed. If the key is missing, BABY falls back to Kokoro (Hindi
voice) automatically.

The first run downloads model files on demand (Kokoro TTS, faster-whisper STT,
Silero VAD, embedding model, etc.) so it may take a moment to warm up.

---

## Modes

### Real LLM mode (default)
BABY needs a local [Ollama](https://ollama.com) server with a model pulled.

```bash
# In a separate terminal, once:
ollama pull llama3.2:1b      # or any model you prefer
ollama serve                  # ensure the server is up
```
`main.py` checks Ollama reachability at `http://localhost:11434` on startup
(`config.yaml` → `llm.base_url`). If it can't connect, BABY exits with a hint.

### Test mode (no Ollama)
Set in `config.yaml`:
```yaml
llm:
  test_mode: true
```
BABY runs end-to-end with a stubbed LLM/TTS — useful to validate the GUI,
tool execution, and permission flows without a GPU or model downloads.

---

## Using BABY

After launch you'll see the **Dynamic Island** with inline buttons and a system-tray icon.

| Button | Action |
|--------|--------|
| `▶ BABY` | Toggle assistant activation |
| `🎙` | Mute / unmute microphone |
| `📷` | Enable **Camera** access (needed before camera tools work) |
| `🖥` | Enable **Screen Share** — pick one or more displays (needed before screenshots work) |
| `📺` | *(speaker mute)* |

Behavior notes:
- **Wake word**: the model `models/hey_baby.tflite` is not bundled, so BABY falls
  back to **Ctrl+F12** as the wake trigger (logged at startup).
- **Screen / Camera permissions** are off by default. Vision tools return a clear
  `"permission is not enabled"` error until you grant them via the island buttons.
- Logs are written to `data/logs/baby_*.log`.

---

## Configuration

All settings live in `config.yaml` (typed loader in `core/config.py`). Common knobs:

```yaml
llm:
  model: llama3.2:1b
  base_url: http://localhost:11434
  test_mode: false              # true = test mode (mock LLM)
tts:
  engine: xtts                  # xtts | kokoro | gemini | elevenlabs
  voice: Mahiru
  speed: 1.3
stt:
  model: small                  # faster-whisper size
  language: null                 # null = auto-detect
ui:
  island_x: 580
  island_y: 40
  theme_color: '#7C7CFF'
consent:
  timeout_seconds: 30
```

You can also change settings live from the tray → Settings panel (the QML
`SettingsPanel` binds to `ui/settings_bridge.py`).

---

## Project layout

```
main.py                     Entry point — boots UI + orchestrator
core/                       Config, orchestrator, consent gate, privacy, context
llm/                        Ollama client (streaming + barge-in)
audio/                      Wake word, VAD (Silero), STT (faster-whisper), TTS (Kokoro/XTTS)
ui/                         PySide6 + QML (Dynamic Island, settings, tray, pointer)
tools/                      File, screen, system tools (executors + schemas)
antigravity/                "Anti-Gravity" planner: agents (system/browser/vision/context/learner)
biometrics/                 Face + voice identification
models/                     Local model binaries (git-ignored)
data/                       Logs, conversations, screenshots, skill store (git-ignored)
```

---

## Troubleshooting

| Symptom | Fix |
|----------|-----|
| `Cannot reach Ollama at ...` | Start `ollama serve`, or set `llm.test_mode: true`. |
| QML window won't appear / plugins fail to load | Ensure you're on a real desktop session (not headless). BABY preloads Qt DLLs at startup on Windows. |
| `Screen share permission is not enabled` | Click the `🖥` button and pick a display. |
| `Camera ... could not open` | Grant camera permission in Windows Settings and ensure no other app holds the camera. |
| TTS falls back to Kokoro | Expected if Coqui XTTS fails to load; Kokoro-ONNX is the built-in fallback. |
| Python 3.14 vs 3.11 note | A `.venv` generated with a newer Python works; `pyrightconfig.json` targets 3.11. |

---

## Development

```bash
# Type-check (if pyright installed)
pyright

# Syntax-compile the whole tree
python -m compileall .

# Run the permission/UI smoke tests (see docs/)
#   QUICKSTART_PERMISSIONS.md, PERMISSION_INTEGRATION_TESTS.md
```

See `ARCHITECTURE_DIAGRAM.md`, `IMPLEMENTATION_SUMMARY.md`, and the
`DYNAMIC_ISLAND_UPDATE.md` / `ISLAND_UI_REFERENCE.md` docs for deeper detail.




