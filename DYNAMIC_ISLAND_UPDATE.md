# Dynamic Island Permission Controls Update

## Overview
Updated the Baby Dynamic Island UI to include screen sharing and camera permission controls. Users can now grant or revoke access to screens and camera before the assistant performs any visual operations.

---

## Components Implemented

### 1. **Screen Share Permission Button** (Dynamic Island)
- **Icon**: 🖥 (desktop/screen emoji)
- **Active State**: 🖥✓ (when screens selected)
- **Location**: Inline in Dynamic Island control bar (after mute buttons)
- **Behavior**:
  - Click to open screen selection modal
  - Shows confirmation checkmark when screens are selected
  - Prevents screen capture if no screens selected

### 2. **Camera Permission Button** (Dynamic Island)
- **Icon**: 📷 (camera emoji)  
- **Active State**: 📷✓ (when camera access granted)
- **Location**: Inline in Dynamic Island control bar (after screen share button)
- **Behavior**:
  - Single-click toggle to grant/revoke camera access
  - Shows confirmation checkmark when enabled
  - Prevents camera frame capture if not granted

### 3. **Screen Selection Modal Dialog**
- **Trigger**: Click screen share button (🖥)
- **Features**:
  - Multi-select screen picker
  - Shows all available displays with resolution
  - Primary display auto-selected on first open
  - Visual checkboxes for each screen
  - Cancel/Apply buttons
  - Real-time selection tracking
  - Closes automatically on Apply

---

## Technical Architecture

### Backend (Python)

#### `ui/island_controller.py`
New properties and methods:
```python
# Properties
@Property(bool, notify=screenShareGrantedChanged)
def screenShareGranted(self)

@Property(list, notify=screenShareSelectionChanged)
def screenShareSelection(self)

@Property(str, notify=screenShareSelectionChanged)
def screenShareSummary(self)

@Property(bool, notify=cameraAccessGrantedChanged)
def cameraAccessGranted(self)

# Slots (QML-callable methods)
@Slot(result=list)
def getAvailableScreens(self) -> list[dict]  # Enumerate system displays

@Slot(str)
def applyScreenShareSelection(self, selection_json: str)  # Save selection

@Slot()
def toggleCameraAccess(self)  # Toggle camera permission

@Slot()
def clearScreenShareSelection(self)  # Revoke screen access
```

#### `tools/screen_tools.py`
Screen capture state management:
```python
_SCREEN_SHARE_ENABLED: bool = False
_SCREEN_SHARE_SELECTION: list[int] = []

def set_screen_share_selection(indices: list[int])  # UI sets selected screens
def set_screen_share_enabled(enabled: bool)         # UI enables/disables sharing
def is_screen_share_enabled() -> bool               # Tools check before capturing
def get_screen_share_selection() -> list[int]       # Get selected screen indices

def _capture_monitors() -> tuple[Image, list[int]]  # Capture selected screens only
```

#### `antigravity/agents/vision_agent.py`
Permission-aware vision tools:
```python
_UI_CONTROLLER = None

def set_ui_controller(controller)      # Register UI controller for permission checks
def is_camera_access_granted() -> bool # Check camera permission

# Updated tools:
def _take_screenshot()                 # Checks is_screen_share_enabled()
def _capture_camera_frame()            # New tool - checks is_camera_access_granted()

# New vision tool schema:
"camera_frame": {
    "description": "Capture a frame from user's camera",
    "requires": "camera permission granted in Dynamic Island"
}
```

### Frontend (QML)

#### `ui/qml/DynamicIsland.qml`
**Screen Share Button** (in main control row):
- 22×22 circular button
- Hoverable with dynamic color feedback
- Displays 🖥✓ when screens selected
- Opens `screenPickerDialog` on click

**Camera Button** (in main control row):
- 22×22 circular button
- Single-click toggle
- Displays 📷✓ when enabled
- Calls `claraController.toggleCameraAccess()`

**Screen Picker Modal** (`screenPickerDialog`):
- Overlay with darkened background
- Centered dialog box (400px wide, up to 600px tall)
- Scrollable list of available screens
- Checkbox selection for each screen
- Shows primary display label
- Resolution info (e.g., "1920×1080")
- Cancel/Apply button row
- Apply button disabled if no screens selected

**Data Model** (`screenShareModel`):
- QML ListModel populated from `getAvailableScreens()`
- Tracks `selected` state for each screen
- Pre-selects primary display if no prior selection

---

## User Workflow

### Scenario 1: Grant Screen Share Access
1. User sees Dynamic Island with inline buttons
2. Clicks 🖥 button to open screen picker
3. Modal appears showing available displays
4. User checks boxes for screens to share (can select multiple)
5. Clicks Apply
6. Screen button changes to 🖥✓
7. Assistant can now call `take_screenshot()` and capture selected screens

### Scenario 2: Grant Camera Access
1. User sees Dynamic Island with inline buttons
2. Clicks 📷 button to toggle permission
3. Camera button changes to 📷✓
4. Assistant can now call `camera_frame()` and capture webcam

### Scenario 3: Revoke Permissions
- Click 🖥 button and select Apply with no screens → revokes screen share
- Click 📷 button again → toggles camera permission off

---

## Permission Enforcement

### Screenshot/Screen Capture
Before `take_screenshot()` executes:
1. Check `is_screen_share_enabled()`
2. If False, return error: "Screen share permission is not enabled. Click Screen Share and choose one or more displays first."
3. If True, capture only the selected screens (single or composite image)

### Camera Frame Capture
Before `camera_frame()` executes (new tool):
1. Check `is_camera_access_granted()`
2. If False, return error: "Camera access permission is not enabled. Click Camera in the Dynamic Island to grant permission."
3. If True, capture frame from webcam and save to `data/screenshots/camera_TIMESTAMP.png`

---

## File Changes Summary

| File | Changes |
|------|---------|
| `ui/island_controller.py` | +97 lines: Screen/camera permission properties & slots |
| `ui/qml/DynamicIsland.qml` | +39 lines: Screen/camera buttons + modal dialog |
| `tools/screen_tools.py` | +73 lines: Screen selection state management, multi-monitor capture |
| `antigravity/agents/vision_agent.py` | +14-18 lines: Camera frame capture, permission checks, UI controller integration |

---

## Dependencies

**New Python Packages Required** (if not already installed):
- `opencv-python` (cv2) — for camera frame capture
- `mss` — for multi-monitor screenshot (should already be installed)
- `PySide6` — for QML/Qt (already required)

**Install**:
```bash
pip install opencv-python
```

---

## Integration Points

### Where the Permission Flow Connects

1. **User grants permission in UI** → `claraController.applyScreenShareSelection()` / `toggleCameraAccess()`
2. **Controller stores state** → `set_screen_share_selection()` / `_camera_access_granted`
3. **Tools check state** → `is_screen_share_enabled()` / `is_camera_access_granted()`
4. **Agent respects check** → Returns error or proceeds based on permission
5. **Assistant receives feedback** → Can inform user of permission requirement or use granted access

---

## Code Examples

### Vision Agent Integration (Python)
```python
from ui.island_controller import ClaraIslandController
from antigravity.agents.vision_agent import set_ui_controller

# During app initialization:
controller = ClaraIslandController(config)
set_ui_controller(controller)  # Register for permission checks
```

### QML Usage
```qml
// Open screen picker
screenPickerDialog.open()

// Apply selection
claraController.applyScreenShareSelection(JSON.stringify([1, 2]))

// Toggle camera
claraController.toggleCameraAccess()

// Check current state
if (claraController.screenShareGranted) { /* show indicator */ }
if (claraController.cameraAccessGranted) { /* show indicator */ }
```

### Python Tool Execution
```python
# Before this executes, permission is checked:
result = execute_vision_tool("take_screenshot", {})

# If permission denied:
# {"success": False, "error": "Screen share permission is not enabled..."}

# If permission granted:
# {"success": True, "path": "data/screenshots/screen_20260716_143322.png"}
```

---

**Version**: 1.0  
**Last Updated**: 2026-07-16  
**Status**: Ready for Testing




