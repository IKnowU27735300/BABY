# Quick Start: Screen Share & Camera Permissions

Get up and running with the new Dynamic Island permission controls in 5 minutes.

---

## Install Dependencies

```bash
pip install opencv-python
```

That's it! Everything else is already in the project.

---

## Boot Baby

```bash
python main.py
# or however you normally start Baby
```

You should see the Dynamic Island with 5 inline buttons:
```
[ ▶ Baby │ 🔊 │ 🎙 │ 🖥 │ 📷 ]
```

---

## Enable Screen Sharing (2 minutes)

### Step 1: Click the 🖥 button
A modal appears showing your displays.

### Step 2: Select screen(s)
- Click the checkbox for Display 1 (or any display)
- Multi-select is supported (click multiple)
- Primary display has a label

### Step 3: Click "Apply"
- Modal closes
- 🖥 changes to 🖥✓
- **Done!** Screenshots now work.

### To disable: 
- Click 🖥✓ again
- Uncheck all displays
- Click "Apply"

---

## Enable Camera (10 seconds)

### Step 1: Click the 📷 button
That's it!

- 📷 changes to 📷✓
- **Done!** Camera tools now work.

### To disable:
- Click 📷✓ again
- Done.

---

## Test It Works

### Test Screenshot
In Python or via Baby prompt:
```python
from antigravity.agents.vision_agent import execute_vision_tool
result = execute_vision_tool("vision_screenshot", {})
print(result)
```

Expected:
```
{
  'success': True, 
  'path': 'data/screenshots/screen_20260716_143322.png',
  'screens': [1]
}
```

### Test Camera
```python
result = execute_vision_tool("camera_frame", {})
print(result)
```

Expected:
```
{
  'success': True,
  'path': 'data/screenshots/camera_20260716_143322.png',
  'message': 'Camera frame captured: camera_...'
}
```

### Test Permissions
Without permissions enabled, tools return clear errors:
```
{
  'success': False,
  'error': 'Screen share permission is not enabled. Click Screen Share and choose one or more displays first.'
}
```

---

## Visual Indicators

### Permission Status
- **🖥** = Screen sharing OFF (can't screenshot)
- **🖥✓** = Screen sharing ON (can screenshot)
- **📷** = Camera OFF (can't capture frames)
- **📷✓** = Camera ON (can capture frames)

### While Capturing
- Look top-right of Dynamic Island
- You'll see privacy indicator pills:
  - **Red 🎙** = Microphone recording (if enabled)
  - **Orange 📷** = Camera capturing

---

## Common Issues

### "Permission is not enabled" error
**Problem**: Tool returns permission error  
**Solution**: Click the permission button (🖥 or 📷) and grant access

### Modal won't open
**Problem**: Can't click 🖥 button  
**Solution**: Try double-click or check that QML loaded correctly

### No displays shown in modal
**Problem**: Screen picker modal is empty  
**Solution**: Your displays may not be enumerated. Check system displays are connected

### Camera returns "Could not open device"
**Problem**: Camera frame capture fails  
**Solution**: 
- Check camera is connected
- Check camera isn't already in use (other app)
- Check camera permissions in OS settings

### OpenCV import error
**Problem**: `ModuleNotFoundError: No module named 'cv2'`  
**Solution**: `pip install opencv-python`

---

## Architecture Summary

### Frontend (What you see)
- **QML**: Dynamic Island with permission buttons
- **Controller**: Python bridge between QML and backend

### Backend (What works)
- **Permission State**: Stored in `tools/screen_tools.py`
- **Vision Agent**: Checks permission before capturing
- **Tools**: 
  - `vision_screenshot` (needs screen share)
  - `camera_frame` (needs camera access)

### Data Flow
```
User clicks button
  ↓
QML signal → Python slot
  ↓
Permission state updates
  ↓
Vision tool checks permission
  ↓
Success or error returned
```

---

## Key Files (Understand the code)

| File | Purpose |
|------|---------|
| `ui/qml/DynamicIsland.qml` | The 🖥 📷 buttons + screen picker modal |
| `ui/island_controller.py` | Permission properties + slots |
| `tools/screen_tools.py` | Permission state variables |
| `antigravity/agents/vision_agent.py` | Screenshot + camera tools |

---

## Pro Tips

### Debug permission state
```python
from tools.screen_tools import is_screen_share_enabled, get_screen_share_selection
print(f"Screen share enabled: {is_screen_share_enabled()}")
print(f"Selected screens: {get_screen_share_selection()}")
```

### View all available screens
```python
from ui.island_controller import ClaraIslandController
controller = ClaraIslandController(config)
screens = controller.getAvailableScreens()
for s in screens:
    print(f"{s['index']}: {s['label']}")
```

### Manually set permission
```python
from tools.screen_tools import set_screen_share_selection, set_screen_share_enabled
set_screen_share_selection([1, 2])  # Screens 1 and 2
set_screen_share_enabled(True)
```

### Monitor permission changes in logs
Filter logs for:
- `[UI] Screen share selection applied:`
- `[Camera] Frame captured:`
- `[ScreenShare]` 

---

## What's Next?

After confirming permissions work:

1. **Integrate with assistants**: Have Baby ask for permission when she needs visual access
2. **Test in conversations**: Try: "Baby, show me what you see" or "Can I see your face?"
3. **Review logs**: Check `data/logs/` for permission state changes
4. **Give feedback**: Permission workflow feels natural?

---

## Full Documentation

- **Feature Overview**: `DYNAMIC_ISLAND_UPDATE.md`
- **UI Visual Guide**: `ISLAND_UI_REFERENCE.md`
- **Testing Procedures**: `PERMISSION_INTEGRATION_TESTS.md`
- **Implementation Details**: `IMPLEMENTATION_SUMMARY.md`

---

## Support

**Permission denied?** Click the button (🖥 or 📷)

**Button won't work?** Check system logs and python console for errors

**Need help?** See `IMPLEMENTATION_SUMMARY.md` under "Support & Debugging"

---

**Version**: 1.0  
**Last Updated**: 2026-07-16  
**Status**: Ready to use




