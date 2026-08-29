# Permission Control Integration Tests

This document provides manual testing procedures to verify the screen share and camera permission features work correctly end-to-end.

---

## Prerequisites

- Baby app running with Dynamic Island visible
- Terminal or log viewer showing Baby output
- At least 1 display connected (for screen share tests)
- Webcam available (for camera tests)

---

## Test Suite 1: Screen Share Permission

### Test 1.1: Open Screen Picker
**Steps:**
1. Look for the Dynamic Island with inline permission buttons
2. Identify the 🖥 button (screen share)
3. Click the 🖥 button

**Expected Result:**
- Modal dialog appears in center of screen
- Shows title: "Select Screens to Share"
- Displays at least 1 available monitor
- Each monitor shows resolution (e.g., "1920×1080")
- Primary display marked with "(Primary Display)" label
- Apply button is **disabled** (no screens selected yet)
- Cancel button is enabled and clickable

**Failure Cases:**
- Modal doesn't appear → Check DynamicIsland.qml line 795
- Can't see screens → Check getAvailableScreens() in island_controller.py
- Primary display not labeled → Check screenShareModel population in DynamicIsland.qml

---

### Test 1.2: Select Single Screen
**Steps:**
1. Modal is open with screen list
2. Click the checkbox next to Display 1

**Expected Result:**
- Checkbox becomes filled/checked (shows ✓)
- Apply button becomes **enabled** (no longer gray)
- Item background changes to blue (#2A4A7C)
- Item border becomes purple (#7C7CFF)

**Failure Cases:**
- Checkbox doesn't check → Check CheckBox MouseArea in DynamicIsland.qml
- Apply button doesn't enable → Check Apply button enabled binding
- Colors don't change → Check Behavior animations

---

### Test 1.3: Select Multiple Screens
**Prerequisites:** At least 2 displays connected

**Steps:**
1. Modal is open with 2+ screens shown
2. Click checkbox for Display 1
3. Click checkbox for Display 2

**Expected Result:**
- Both checkboxes are checked
- Both items highlighted in blue with purple borders
- Apply button is enabled

**Failure Cases:**
- Only 1 screen can be selected → Check multi-select logic in DynamicIsland.qml
- Selection resets when clicking second screen → Check ListModel updates

---

### Test 1.4: Unselect Screen
**Steps:**
1. Modal with 1+ screens selected
2. Click checkbox of a selected screen

**Expected Result:**
- Checkbox becomes unchecked
- Item background returns to dark gray (#2A2A2E)
- Item border returns to subtle gray
- If this was the last screen, Apply button becomes **disabled**

**Failure Cases:**
- Uncheck doesn't work → Check toggle logic in screenShareModel.setProperty
- Apply button doesn't disable → Check enabled binding in DynamicIsland.qml

---

### Test 1.5: Apply Selection
**Steps:**
1. Modal with 1+ screens selected
2. Click the "Apply" button

**Expected Result:**
- Modal closes smoothly
- 🖥 button changes to 🖥✓ (checkmark added)
- Logs show: `[UI] Screen share selection applied: [1]` (or `[1, 2]` if multiple)
- Permission state is now enabled

**Failure Cases:**
- Modal doesn't close → Check screenPickerDialog.close() in Apply button
- Icon doesn't change → Check screenShareGrantedChanged signal binding
- Logs don't show selection → Check applyScreenShareSelection() in island_controller.py

---

### Test 1.6: Cancel Selection (With Changes)
**Steps:**
1. Modal open with multiple screens
2. Select Display 1
3. Click "Cancel" button

**Expected Result:**
- Modal closes
- 🖥 button shows current state (🖥 or 🖥✓ based on prior selection)
- Selected display is **not** saved (selection discarded)

**Failure Cases:**
- Modal doesn't close → Check Cancel button onClicked
- Selection was accidentally saved → Check that Cancel doesn't call applyScreenShareSelection

---

### Test 1.7: Screen Share Button State Persistence
**Steps:**
1. Select screens and click Apply (🖥 → 🖥✓)
2. Click 🖥✓ button again to reopen modal

**Expected Result:**
- Modal opens with previously selected screens already checked
- Summary shows correct number/names of selected screens

**Failure Cases:**
- Previous selection is lost → Check screenShareSelection property in controller
- Modal shows no screens selected → Check refreshScreenShareModel() logic

---

### Test 1.8: Revoke Screen Share
**Steps:**
1. 🖥✓ button visible (screens already shared)
2. Click 🖥✓ to open modal
3. Uncheck all screens
4. Click Apply

**Expected Result:**
- Modal closes
- 🖥✓ changes back to 🖥
- Logs show: `[UI] Screen share permission cleared`
- Screenshot tools will now fail with permission error

**Failure Cases:**
- Button doesn't change back → Check screenShareGrantedChanged signal
- Logs don't show clearing → Check clearScreenShareSelection() call path

---

## Test Suite 2: Screenshot Tool Permission

### Test 2.1: Screenshot Without Permission
**Steps:**
1. Ensure 🖥 button is **not** checkmarked (🖥, not 🖥✓)
2. In Baby console/code, call: `execute_vision_tool("vision_screenshot", {})`

**Expected Result:**
- Tool returns error dict:
```json
{
  "success": false,
  "error": "Screen share permission is not enabled. Click Screen Share and choose one or more displays first."
}
```
- No screenshot file is created
- Logs show the permission error

**Failure Cases:**
- Screenshot taken despite no permission → Check is_screen_share_enabled() guard
- Wrong error message → Check error string in _take_screenshot()

---

### Test 2.2: Screenshot With Permission
**Steps:**
1. Select screens and enable sharing (🖥✓ visible)
2. Call: `execute_vision_tool("vision_screenshot", {})`

**Expected Result:**
- Tool returns success dict:
```json
{
  "success": true,
  "path": "data/screenshots/screen_20260716_143322.png",
  "screens": [1],
  "message": "Screenshot saved: screen_20260716_143322.png"
}
```
- Image file created at returned path
- Image shows content from selected displays only
- Logs show screenshot saved

**Failure Cases:**
- Permission not respected → Check is_screen_share_enabled() call
- Wrong file created → Check _capture_monitors() path
- Image shows wrong screens → Check mss monitor selection logic

---

### Test 2.3: Multi-Monitor Screenshot
**Prerequisites:** 2+ displays with different content visible

**Steps:**
1. Enable sharing and select 2 displays
2. Place different content on each display
3. Call screenshot tool

**Expected Result:**
- Single composite image created
- Shows content from both displays side-by-side or combined
- No artifacts or black regions between screens

**Failure Cases:**
- Only one display captured → Check _capture_monitors() loop
- Screens misaligned → Check left/top offset calculations
- Image is stretched/scaled → Check PIL Image.paste() positioning

---

## Test Suite 3: Camera Permission

### Test 3.1: Toggle Camera Permission
**Steps:**
1. Locate 📷 button in Dynamic Island
2. Click the 📷 button

**Expected Result:**
- 📷 button changes to 📷✓
- Logs show: `[UI] Camera access permission changed to: True`
- Camera state is enabled

**Failure Cases:**
- Icon doesn't change → Check cameraAccessGrantedChanged signal
- Logs don't show state change → Check toggleCameraAccess() in island_controller.py

---

### Test 3.2: Toggle Camera Permission Off
**Steps:**
1. 📷✓ button visible (camera already enabled)
2. Click the 📷✓ button

**Expected Result:**
- 📷✓ changes back to 📷
- Logs show: `[UI] Camera access permission changed to: False`
- Camera state is disabled

**Failure Cases:**
- Icon doesn't toggle → Check toggleCameraAccess() implementation
- State doesn't update → Check cameraAccessGranted property binding

---

## Test Suite 4: Camera Frame Capture

### Test 4.1: Capture Frame Without Permission
**Steps:**
1. Ensure 📷 button shows 📷 (not 📷✓)
2. Call: `execute_vision_tool("camera_frame", {})`

**Expected Result:**
- Tool returns error dict:
```json
{
  "success": false,
  "error": "Camera access permission is not enabled. Click Camera in the Dynamic Island to grant permission."
}
```
- No frame file created
- Logs show permission denied

**Failure Cases:**
- Frame captured without permission → Check is_camera_access_granted() guard
- Wrong error message → Check error string in _capture_camera_frame()

---

### Test 4.2: Capture Frame With Permission
**Steps:**
1. Click 📷 button to enable camera (📷✓ visible)
2. Call: `execute_vision_tool("camera_frame", {})`

**Expected Result:**
- Tool returns success dict:
```json
{
  "success": true,
  "path": "data/screenshots/camera_20260716_143322.png",
  "message": "Camera frame captured: camera_20260716_143322.png"
}
```
- Image file created at returned path
- Image shows live webcam feed (your face, room, etc.)
- File format is PNG
- Logs show frame captured

**Failure Cases:**
- Permission not respected → Check is_camera_access_granted() call
- OpenCV error → Check cv2 import and device availability
- No frame file created → Check file save in _capture_camera_frame()

---

### Test 4.3: Camera Not Available
**Prerequisites:** No webcam connected or camera device is in use

**Steps:**
1. Enable camera permission (📷✓)
2. Disconnect/block webcam
3. Call: `execute_vision_tool("camera_frame", {})`

**Expected Result:**
- Tool returns error dict:
```json
{
  "success": false,
  "error": "Could not open camera device. Check that the camera is available and not in use."
}
```
- Logs show camera open failure

**Failure Cases:**
- No error returned → Check cv2.VideoCapture().isOpened() check
- App crashes → Check exception handling in _capture_camera_frame()

---

## Test Suite 5: UI State Synchronization

### Test 5.1: Privacy Indicators During Screen Capture
**Steps:**
1. Enable screen sharing (🖥✓)
2. Call screenshot tool
3. During capture, observe top-right corner of island

**Expected Result:**
- While capturing: 📷 indicator appears (orange pill, top-right)
- After capture completes: Indicator remains (if screenshot is processing) or disappears (if instant)
- No visual glitches or overlapping indicators

**Failure Cases:**
- Indicator doesn't appear → Check camActive property binding
- Indicator persists after capture → Check camActive state management

---

### Test 5.2: Privacy Indicators During Camera Frame Capture
**Steps:**
1. Enable camera permission (📷✓)
2. Call camera_frame tool
3. Observe island during capture

**Expected Result:**
- While capturing: 📷 indicator appears (orange pill, top-right)
- Island remains responsive
- User can still access controls

**Failure Cases:**
- Island becomes unresponsive → Check async/blocking behavior in _capture_camera_frame()
- Indicator doesn't update → Check camActive property synchronization

---

## Test Suite 6: Error Handling

### Test 6.1: Permission State Consistency
**Steps:**
1. Enable screen sharing (🖥✓)
2. Call screenshot tool (should succeed)
3. Revoke permission by unchecking all screens (🖥)
4. Call screenshot tool again (should fail)

**Expected Result:**
- First call succeeds (screenshot created)
- Second call fails immediately (permission error)
- No delay or race conditions

**Failure Cases:**
- Race condition: second call succeeds → Check is_screen_share_enabled() timing
- Permission state doesn't update → Check set_screen_share_enabled() propagation

---

### Test 6.2: Modal Dismissal on Escape (Optional Enhancement)
**Steps:**
1. Open screen picker modal
2. Press Escape key

**Expected Result:**
- Modal closes (if ESC handler implemented)
- Selection is discarded (like Cancel button)

**Current Status:** ESC handler not implemented in v1.0
**Future Enhancement:** Add KeyEvent handler for Qt.Key_Escape

---

## Test Suite 7: Permission Persistence (Optional Enhancement)

### Test 7.1: Persist Screen Selection on Restart
**Steps:**
1. Select screens and apply (🖥✓)
2. Close Baby app completely
3. Restart Baby app
4. Click 🖥✓ to reopen modal

**Expected Result:**
- Previously selected screens are still checked
- Summary matches prior selection

**Current Status:** Not implemented in v1.0
**Future Enhancement:** Save selection to config.yaml

---

## Test Suite 8: Accessibility

### Test 8.1: Keyboard Navigation in Modal
**Steps:**
1. Open screen picker modal
2. Use Tab key to navigate between elements

**Expected Result:**
- Tab cycles through: Screen items → Cancel button → Apply button → back to first item
- Enter key selects/toggles checkboxes when focused
- Current focus is visually indicated

**Current Status:** Basic Tab navigation supported by Qt
**Future Enhancement:** Add explicit focus handlers

---

### Test 8.2: Screen Reader Compatibility
**Steps:**
1. Enable screen reader (NVDA, JAWS, or OS screen reader)
2. Open screen picker modal
3. Navigate with arrow keys

**Expected Result:**
- Screen reader announces: "Select Screens to Share" title
- Announces each display: "Display 1, 1920×1080, checkbox, unchecked"
- Announces button states: "Apply button, disabled"

**Current Status:** Basic Qt accessibility support
**Future Enhancement:** Add explicit accessible names and descriptions

---

## Debugging Tips

### View Permission State in Logs
```python
# Add to vision_agent.py for debugging:
logger.info("[VisionDebug] Screen share enabled: {}", is_screen_share_enabled())
logger.info("[VisionDebug] Camera access granted: {}", is_camera_access_granted())
logger.info("[VisionDebug] Selected screens: {}", get_screen_share_selection())
```

### Inspect Controller State
```python
# In Python console or code:
from ui.island_controller import ClaraIslandController
print(f"Screen share: {controller.screenShareGranted}")
print(f"Camera access: {controller.cameraAccessGranted}")
print(f"Selected screens: {controller.screenShareSelection}")
print(f"Screen summary: {controller.screenShareSummary}")
```

### Test Tool Directly
```python
# Call vision tools directly:
from antigravity.agents.vision_agent import execute_vision_tool

result = execute_vision_tool("vision_screenshot", {})
print(result)

result = execute_vision_tool("camera_frame", {})
print(result)
```

### Monitor Permission State Changes
```python
# In tools/screen_tools.py, add logging:
def set_screen_share_enabled(enabled: bool):
    global _SCREEN_SHARE_ENABLED
    old = _SCREEN_SHARE_ENABLED
    _SCREEN_SHARE_ENABLED = bool(enabled) and bool(_SCREEN_SHARE_SELECTION)
    if old != _SCREEN_SHARE_ENABLED:
        logger.info("[ScreenShare] Enabled changed: {} -> {}", old, _SCREEN_SHARE_ENABLED)
```

---

## Known Issues & Limitations

### v1.0 Release

1. **No Permission Persistence**: Permissions reset when app restarts
   - Workaround: Manually re-select screens on each session
   - Fix: Save to config.yaml

2. **No Permission Timeout**: Permissions remain active indefinitely
   - Workaround: Manually revoke if needed
   - Fix: Add 30-min auto-revoke in background task

3. **No Camera Preview**: Modal doesn't show live camera feed
   - Workaround: Enable camera and trust the checkmark
   - Fix: Show thumbnail in modal before applying

4. **Single Camera Device**: Only captures from default webcam (device 0)
   - Workaround: Use OS settings to change default
   - Fix: Allow selecting from multiple cameras

---

**Test Suite Version**: 1.0  
**Updated**: 2026-07-16  
**Status**: Ready for QA




