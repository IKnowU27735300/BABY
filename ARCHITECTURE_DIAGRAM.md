# Permission Controls - Architecture & Diagram

Visual overview of how permissions flow through the system.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Baby DESKTOP ASSISTANT                      │
└─────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│         DYNAMIC ISLAND (QML Frontend)      │
│  ┌────────────────────────────────────────┐│
│  │ [▶ Baby│🔊│🎙│🖥│📷]                ││  ← Permission buttons
│  └────────────────────────────────────────┘│
│                                              │
│  🖥 Click → Screen Picker Modal               │
│  ┌────────────────────────────────────────┐│
│  │ Select Screens to Share                ││
│  │ ☐ Display 1 - 1920×1080                ││
│  │ ☑ Display 2 - 2560×1440                ││
│  │          [Cancel] [Apply]              ││
│  └────────────────────────────────────────┘│
│                                              │
│  📷 Click → Permission Toggled               │
└────────────────────────────────────────────┘
         ↓ Qt Signals/Slots ↓
         
┌────────────────────────────────────────────┐
│     ISLAND CONTROLLER (Python Bridge)       │
│  ui/island_controller.py                   │
│                                              │
│  Properties:                                 │
│  • screenShareGranted: bool                 │
│  • screenShareSelection: list[int]          │
│  • cameraAccessGranted: bool                │
│                                              │
│  Slots:                                      │
│  • getAvailableScreens()                    │
│  • applyScreenShareSelection(json)          │
│  • toggleCameraAccess()                     │
└────────────────────────────────────────────┘
         ↓ Python Function Calls ↓
         
┌────────────────────────────────────────────┐
│      SCREEN TOOLS (Permission State)        │
│  tools/screen_tools.py                     │
│                                              │
│  Global State:                               │
│  _SCREEN_SHARE_ENABLED: bool                │
│  _SCREEN_SHARE_SELECTION: list[int]        │
│                                              │
│  Functions:                                  │
│  • set_screen_share_selection([1,2])        │
│  • set_screen_share_enabled(True)           │
│  • is_screen_share_enabled() → bool        │
│  • get_screen_share_selection() → list     │
│  • _capture_monitors() → Image             │
│                                              │
│  • set_camera_access(enabled)               │
│  • is_camera_access_granted() → bool        │
└────────────────────────────────────────────┘
         ↓ Permission Checks ↓
         
┌────────────────────────────────────────────┐
│       VISION AGENT (Tool Execution)         │
│  antigravity/agents/vision_agent.py        │
│                                              │
│  Tools:                                      │
│  • vision_screenshot()                      │
│    ├─ Check: is_screen_share_enabled()     │
│    ├─ Success: Capture selected screens    │
│    └─ Failure: Return permission error     │
│                                              │
│  • camera_frame()                           │
│    ├─ Check: is_camera_access_granted()    │
│    ├─ Success: Capture webcam frame        │
│    └─ Failure: Return permission error     │
│                                              │
│  • vision_read_screen()                     │
│  • vision_locate_text()                     │
│  • vision_describe_screen()                 │
└────────────────────────────────────────────┘
         ↓ Results to Assistant ↓
         
┌────────────────────────────────────────────┐
│        OLLAMA LLM / ASSISTANT BRAIN         │
│  Uses visual data to inform responses       │
└────────────────────────────────────────────┘
```

---

## Permission Check Flow Diagram

### Screenshot with Permission

```
User clicks [Activate] 
    ↓
Baby asks for screen access
    ↓
User clicks 🖥 button
    ↓
Screen picker modal opens
    ↓
User selects Display 1 and clicks Apply
    ↓
Island controller: screenShareGranted = True
Island controller: screenShareSelection = [1]
    ↓
set_screen_share_selection([1])
    ↓
_SCREEN_SHARE_ENABLED = True
_SCREEN_SHARE_SELECTION = [1]
    ↓
Baby calls: execute_vision_tool("vision_screenshot", {})
    ↓
is_screen_share_enabled() → True ✓
    ↓
_capture_monitors() captures Display 1
    ↓
Image saved: data/screenshots/screen_20260716_143322.png
    ↓
Return: {
  "success": true,
  "path": "data/screenshots/screen_20260716_143322.png",
  "screens": [1]
}
    ↓
Baby analyzes image and responds
```

### Screenshot WITHOUT Permission

```
User does NOT click 🖥 button
    ↓
screenShareGranted = False
screenShareSelection = []
_SCREEN_SHARE_ENABLED = False
    ↓
Baby calls: execute_vision_tool("vision_screenshot", {})
    ↓
is_screen_share_enabled() → False ✗
    ↓
Return: {
  "success": false,
  "error": "Screen share permission is not enabled. 
            Click Screen Share and choose one or more displays first."
}
    ↓
Baby tells user: "I need screen access"
    ↓
User sees error and clicks 🖥
    ↓
[Returns to first flow above]
```

---

## Camera Permission State Machine

```
START
  │
  ├─ 📷 Click
  │    └─ cameraAccessGranted = True
  │         └─ Icon: 📷 → 📷✓
  │         └─ camera_frame() now works ✓
  │         └─ State: ENABLED
  │
  └─ 📷✓ Click
       └─ cameraAccessGranted = False
            └─ Icon: 📷✓ → 📷
            └─ camera_frame() returns permission error ✗
            └─ State: DISABLED
```

---

## Screen Selection State Machine

```
START
  │
  ├─ Click 🖥
  │    └─ Modal opens
  │    └─ getAvailableScreens() populates list
  │    └─ Primary display pre-selected
  │    └─ Apply button DISABLED (no selection yet)
  │
  ├─ User checks Display 1
  │    └─ screenShareModel.selected = True
  │    └─ Item background: blue
  │    └─ Apply button ENABLED
  │
  ├─ User checks Display 2
  │    └─ screenShareModel.selected = True
  │    └─ Apply button still ENABLED
  │
  ├─ User clicks Apply
  │    └─ screenShareSelection = [1, 2]
  │    └─ set_screen_share_selection([1, 2])
  │    └─ Modal closes
  │    └─ Icon: 🖥 → 🖥✓
  │    └─ vision_screenshot() now captures displays 1 & 2
  │
  └─ Click 🖥✓
       └─ Modal opens with [1, 2] pre-selected
       ├─ User unselects all
       │    └─ Apply button DISABLED
       ├─ User clicks Apply
       │    └─ screenShareSelection = []
       │    └─ set_screen_share_selection([])
       │    └─ Icon: 🖥✓ → 🖥
       │    └─ vision_screenshot() now returns permission error
       └─ [Back to START]
```

---

## Component Interaction Matrix

```
┌─────────────────────────┬──────────┬──────────┬──────────┐
│ Component               │ Read     │ Write    │ Signal   │
├─────────────────────────┼──────────┼──────────┼──────────┤
│ DynamicIsland.qml       │ Permission Props │ Button Click │
│ (QML Frontend)          │ Screen List      │ Selection    │
├─────────────────────────┼──────────┼──────────┼──────────┤
│ island_controller.py    │ QML      │ Slot     │ Property │
│ (Python Bridge)         │ Signals  │ Execute  │ Changed  │
├─────────────────────────┼──────────┼──────────┼──────────┤
│ screen_tools.py         │ Request  │ State    │ None     │
│ (Permission State)      │ Check    │ Update   │          │
├─────────────────────────┼──────────┼──────────┼──────────┤
│ vision_agent.py         │ State    │ Tool     │ Result   │
│ (Vision Tools)          │ Check    │ Execute  │ Return   │
└─────────────────────────┴──────────┴──────────┴──────────┘
```

---

## Data Flow for Screenshot with Multiple Displays

```
[User selects Display 1, 2, 3 and applies]
         ↓
set_screen_share_selection([1, 2, 3])
         ↓
_SCREEN_SHARE_SELECTION = [1, 2, 3]
         ↓
Baby: execute_vision_tool("vision_screenshot", {})
         ↓
is_screen_share_enabled() → True
         ↓
_capture_monitors():
    ├─ Get selected monitors from mss: [1, 2, 3]
    ├─ Calculate bounding box:
    │  ├─ left = min(monitor["left"] for all)
    │  ├─ top = min(monitor["top"] for all)
    │  ├─ right = max(monitor["left"] + monitor["width"])
    │  ├─ bottom = max(monitor["top"] + monitor["height"])
    │
    ├─ Create canvas:
    │  └─ Image.new("RGB", (right-left, bottom-top))
    │
    ├─ Capture each monitor:
    │  ├─ shot = sct.grab(monitor)
    │  ├─ img = Image.frombytes("RGB", shot.size, shot.rgb)
    │  └─ canvas.paste(img, offset)
    │
    └─ Save composite: data/screenshots/screen_20260716_143322.png
         ↓
Return: {
  "success": true,
  "path": "data/screenshots/screen_20260716_143322.png",
  "screens": [1, 2, 3]
}
```

---

## Camera Frame Capture Flow

```
[User enables camera: 📷✓]
         ↓
cameraAccessGranted = True
         ↓
Baby: execute_vision_tool("camera_frame", {})
         ↓
is_camera_access_granted() → True
         ↓
_capture_camera_frame():
    ├─ cap = cv2.VideoCapture(0)
    ├─ cap.isOpened() → True
    ├─ ret, frame = cap.read()
    ├─ cap.release()
    │
    ├─ Convert BGR → RGB:
    │  └─ frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    │
    ├─ Convert numpy array → PIL Image:
    │  └─ img = Image.fromarray(frame_rgb)
    │
    └─ Save: data/screenshots/camera_20260716_143322.png
         ↓
Return: {
  "success": true,
  "path": "data/screenshots/camera_20260716_143322.png",
  "message": "Camera frame captured: camera_20260716_143322.png"
}
```

---

## Error Handling Paths

```
SCREENSHOT PERMISSION ERROR:
  is_screen_share_enabled() → False
         ↓
  Return error dict:
  {
    "success": False,
    "error": "Screen share permission is not enabled. 
              Click Screen Share and choose one or more displays first."
  }
         ↓
  Baby relays to user


CAMERA PERMISSION ERROR:
  is_camera_access_granted() → False
         ↓
  Return error dict:
  {
    "success": False,
    "error": "Camera access permission is not enabled. 
              Click Camera in the Dynamic Island to grant permission."
  }
         ↓
  Baby relays to user


CAMERA DEVICE ERROR:
  cv2.VideoCapture(0).isOpened() → False
         ↓
  Return error dict:
  {
    "success": False,
    "error": "Could not open camera device. 
              Check that the camera is available and not in use."
  }
         ↓
  Baby relays to user
```

---

## State Diagram: Complete Permission Lifecycle

```
                    ┌─────────────────┐
                    │  APP STARTUP    │
                    └────────┬────────┘
                             ↓
        ┌────────────────────────────────────┐
        │ Register UI controller with         │
        │ vision agent for permission checks  │
        └────────────────────┬───────────────┘
                             ↓
        ┌────────────────────────────────────┐
        │  screenShareGranted = False         │
        │  screenShareSelection = []          │
        │  cameraAccessGranted = False        │
        │  🖥 shows as 🖥                      │
        │  📷 shows as 📷                      │
        └────────────────────┬───────────────┘
                             ↓
        ┌────────────────────────────────────┐
        │ User clicks 🖥 button                │
        │ (or continues with 📷)              │
        └────────────────────┬───────────────┘
                             ↓
        ┌────────────────────────────────────┐
        │ screenShareGranted = True           │
        │ screenShareSelection = [1]          │
        │ 🖥 changes to 🖥✓                    │
        └────────────────────┬───────────────┘
                             ↓
        ┌────────────────────────────────────┐
        │ is_screen_share_enabled() = True    │
        │ Screenshot tools now work           │
        └────────────────────┬───────────────┘
                             ↓
        ┌────────────────────────────────────┐
        │ User clicks 🖥✓, unselects, Apply   │
        │ (or continues with usage)           │
        └────────────────────┬───────────────┘
                             ↓
        ┌────────────────────────────────────┐
        │ screenShareGranted = False          │
        │ screenShareSelection = []           │
        │ 🖥 changes back to 🖥               │
        └────────────────────┬───────────────┘
                             ↓
        [Loop back or Exit]
```

---

## Request → Response Flow Example

```
REQUEST: Take screenshot of Display 1 & 2

  ┌─ ui/qml/DynamicIsland.qml
  │  └─ User selects Display 1, 2 in modal
  │
  ├─ ui/island_controller.py
  │  └─ applyScreenShareSelection([1, 2])
  │     └─ set_screen_share_selection([1, 2])
  │     └─ set_screen_share_enabled(True)
  │
  ├─ tools/screen_tools.py
  │  └─ _SCREEN_SHARE_ENABLED = True
  │  └─ _SCREEN_SHARE_SELECTION = [1, 2]
  │
  ├─ antigravity/agents/vision_agent.py
  │  └─ execute_vision_tool("vision_screenshot", {})
  │     └─ _take_screenshot()
  │        └─ is_screen_share_enabled() → True ✓
  │        └─ _capture_monitors()
  │           └─ Get mss monitors [1, 2]
  │           └─ Create composite image
  │           └─ Save to file
  │           └─ Return {success: true, path: "...", screens: [1, 2]}
  │
  ├─ antigravity/admin.py (LLM Router)
  │  └─ Route to appropriate agent
  │  └─ Parse response
  │
  └─ core/orchestrator.py
     └─ Return to user: "I've captured your screens"
```

---

**Version**: 1.0  
**Created**: 2026-07-16  
**Purpose**: Visual documentation of architecture and data flows




