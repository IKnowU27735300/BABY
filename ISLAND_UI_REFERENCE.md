# Dynamic Island UI Reference Guide

## Island State Views

### IDLE State
```
┌─────────────────────────────────┐
│ ▶  Baby  │ 🔊 │ 🎙 │ 🖥 │ 📷 │
└─────────────────────────────────┘
```
- **▶**: Activate button (click to start listening)
- **Baby**: Text label
- **🔊**: Speaker mute toggle
- **🎙**: Microphone mute toggle  
- **🖥**: Screen share (select screens)
- **📷**: Camera permission toggle

### LISTENING State
```
┌──────────────────────────────────────────────┐
│ ■  ▁▂▃▄▅ Listening...  │ 🔊 │ 🎙 │ 🖥 │ 📷 │
└──────────────────────────────────────────────┘
```
- **■**: Stop/deactivate button
- **▁▂▃▄▅**: Animated waveform bars
- **Listening...**: Status text
- Mute buttons and permission controls available

### THINKING State
```
┌─────────────────────────────────────────────────┐
│ ■  ◯ Thinking... Agent │ 🔊 │ 🎙 │ 🖥 │ 📷 │
└─────────────────────────────────────────────────┘
```
- **■**: Stop button
- **◯**: Spinning gradient ring (visual thinking indicator)
- **Thinking... Agent**: Status and agent name
- Mute buttons and permission controls available

### SPEAKING State
```
┌──────────────────────────────────────────────────────────┐
│ ■  Baby                 │ 🔊 │ 🎙 │ 🖥 │ 📷 │          │
│ The user's task has been completed successfully. The... │
└──────────────────────────────────────────────────────────┘
```
- **■**: Stop button
- **Baby**: Assistant name in green
- Large text area with response content
- Auto-wraps and grows to show full message
- Mute buttons and permission controls available

### CONSENT State
```
┌──────────────────────────────────────────────────────────┐
│ 🟢 Quick Action          │ 🔊 │ 🎙 │ 🖥 │ 📷 │          │
│ Baby wants to access your Gmail inbox to send a msg... │
│                                                          │
│           ✓ Approve          ✕ Deny                     │
└──────────────────────────────────────────────────────────┘
```
- **🟢**: Risk indicator (green=low, orange=medium, red=high)
- **Risk label**: Quick Action / Action Required / HIGH RISK
- Large planning/action text
- **Approve/Deny buttons**: Full-width interactive controls
- Mute buttons and permission controls available

### ERROR State
```
┌─────────────────────────────┐
│ ■  ⚠ Something went wrong   │ 🔊 │ 🎙 │ 🖥 │ 📷 │
└─────────────────────────────┘
```
- **■**: Stop/deactivate button
- **⚠**: Red error indicator
- **Error message**: Brief description
- Mute buttons and permission controls available

---

## Permission Button States

### Screen Share Button (🖥)

#### Unpermitted (Unselected)
```
┌─────┐
│ 🖥  │ ← Icon: desktop with no checkmark
└─────┘
Background: Dark gray (#1A1A1E)
Hover: Slightly lighter (#2A2A2E)
```

#### Permitted (Selected)
```
┌─────┐
│ 🖥✓ │ ← Icon: desktop with white checkmark
└─────┘
Background: Dark gray (same)
Visual: Checkmark overlaid on desktop icon
```

### Camera Permission Button (📷)

#### Unpermitted (Disabled)
```
┌──────┐
│ 📷   │ ← Icon: camera
└──────┘
Background: Dark gray (#1A1A1E)
Hover: Slightly lighter (#2A2A2E)
```

#### Permitted (Enabled)
```
┌──────┐
│ 📷✓  │ ← Icon: camera with white checkmark
└──────┘
Background: Dark gray (same)
Visual: Checkmark overlaid on camera icon
```

---

## Screen Share Picker Modal

### Modal Layout
```
┌────────────────────────────────────┐
│ Select Screens to Share             │
│                                     │
│ Choose one or more displays...       │
│                                     │
│ ┌────────────────────────────────┐ │
│ │ ☐ Display 1 - 1920x1080        │ │
│ │   (Primary Display)              │ │
│ ├────────────────────────────────┤ │
│ │ ☑ Display 2 - 2560x1440        │ │
│ │                                 │ │
│ ├────────────────────────────────┤ │
│ │ ☐ Display 3 - 1024x768         │ │
│ │                                 │ │
│ └────────────────────────────────┘ │
│                                     │
│      [ Cancel ]     [ Apply ]       │
│                                     │
└────────────────────────────────────┘
```

### Screen Selection Item (Unchecked)
```
┌──────────────────────────────────┐
│ ☐  Display 1 - 1920x1080        │
│    (Primary Display)              │
└──────────────────────────────────┘
Background: Dark gray (#2A2A2E)
Border: Subtle light gray
Hover: Slight highlight
```

### Screen Selection Item (Checked)
```
┌──────────────────────────────────┐
│ ☑  Display 2 - 2560x1440        │
│                                   │
└──────────────────────────────────┘
Background: Dark blue (#2A4A7C)
Border: Purple (#7C7CFF)
Checkbox: Purple background with white checkmark
```

### Button States

**Cancel Button**
- Default: Dark (#1A1A1E) with subtle border
- Hover: Slightly lighter (#2A2A2E)
- Pressed: Slightly darker
- Text: Gray (#888)

**Apply Button**
- Disabled (no screens selected): Gray with reduced opacity
- Enabled: Purple (#7C7CFF)
- Hover: Lighter purple (#7C9CFF)
- Pressed: Deeper purple (#5E8DFF)
- Text: White (or gray if disabled)

---

## Privacy Indicator Pills (Top-Right Corner)

### Microphone Active
```
┌────┐
│ 🎙 │ Microphone is actively recording
└────┘
Background: Red (#FF453A)
Position: Top-right of island
Size: 20x20px circle
```

### Camera Active
```
┌────┐
│ 📷 │ Camera is actively capturing
└────┘
Background: Orange (#FF9F0A)
Position: Top-right of island (below mic if both active)
Size: 20x20px circle
```

### Both Active
```
┌────┐
│ 🎙 │
├────┤
│ 📷 │
└────┘
Stacked vertically, top-right corner
```

---

## Interaction Flows

### Flow 1: Enable Screen Share
```
1. User clicks 🖥 button
   ↓
2. Screen picker modal appears
   ↓
3. User checks displays (1 or more)
   ↓
4. User clicks "Apply"
   ↓
5. Modal closes
   ↓
6. 🖥 button changes to 🖥✓
   ↓
7. Screenshot tools now enabled
```

### Flow 2: Disable Screen Share
```
1. User clicks 🖥✓ button (when already enabled)
   ↓
2. Screen picker modal appears with previous selection
   ↓
3. User unchecks all displays
   ↓
4. User clicks "Apply"
   ↓
5. Modal closes
   ↓
6. 🖥✓ button changes back to 🖥
   ↓
7. Screenshot tools now disabled
```

### Flow 3: Enable Camera
```
1. User clicks 📷 button
   ↓
2. 📷 button changes to 📷✓
   ↓
3. Camera tools now enabled
```

### Flow 4: Disable Camera
```
1. User clicks 📷✓ button (when already enabled)
   ↓
2. 📷✓ button changes back to 📷
   ↓
3. Camera tools now disabled
```

---

## Color Palette

| Element | Default | Hover | Pressed | Disabled |
|---------|---------|-------|---------|----------|
| Permission Button | #1A1A1E | #2A2A2E | #35353A | N/A |
| Apply Button | #7C7CFF | #7C9CFF | #5E8DFF | #666 |
| Cancel Button | #1A1A1E | #2A2A2E | #35353A | N/A |
| Screen Item (unchecked) | #2A2A2E | #3A3A3E | N/A | N/A |
| Screen Item (checked) | #2A4A7C | #3A5A9E | N/A | N/A |
| Checkbox (unchecked) | #1A1A1E | N/A | N/A | N/A |
| Checkbox (checked) | #7C7CFF | N/A | N/A | N/A |
| Mic Active Indicator | #FF453A | N/A | N/A | N/A |
| Camera Active Indicator | #FF9F0A | N/A | N/A | N/A |

---

## Typography

All UI text uses system font stack:
```
Font Family: "SF Pro Display, Segoe UI, sans-serif"
Default Size: 13px
```

### Text Classes
- **Large Headers**: 16px, bold (modal title)
- **Normal Text**: 13px (labels, messages)
- **Small Text**: 12px (descriptions, details)
- **Tiny Text**: 10px (primary display label)

---

## Accessibility Notes

- All interactive elements have hover states (cursor changes to PointingHandCursor)
- Color transitions smooth (150ms duration)
- Text contrast maintained for readability
- Focus states indicated through color changes
- Checkboxes clearly show selected/unselected state
- Error states use red (#FF453A)
- Success/active states use purple (#7C7CFF) or green (#30D158)

---

## Animation Timings

- Button hover/press: 150ms
- Modal transitions: 300ms (opacity fade)
- Permission state changes: 150ms color transition
- Island resize on state change: 250-600ms depending on dimension

---

**Version**: 1.0  
**Created**: 2026-07-16  
**Status**: Complete




