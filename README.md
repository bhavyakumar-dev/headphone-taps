# 🎧 Headphone Taps (NuclearHeart)

> **Translate Bluetooth headphone button actions into instant Like/Favorite actions in Nuclear Music Player.**  
> Crafted specifically with first-class support for **Sony WH-CH720N** multi-button taps, alongside universal support for AirPods, Bose, Galaxy Buds, Beats, and other Bluetooth headsets.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078d7.svg)](https://www.microsoft.com/windows)
[![Player: Nuclear](https://img.shields.io/badge/Player-Nuclear%20Music-9333ea.svg)](https://nuclear.js.org/)

---

## 💡 Overview

When listening to music with headphones on Windows, switching active windows or unlocking your screen just to hit the "Favorite" heart icon disrupts your workflow.

**Headphone Taps** runs silently in your Windows system tray, listens for designated multi-tap headphone button sequences via a low-level keyboard hook (`WH_KEYBOARD_LL`), and dispatches instant **Like/Favorite** actions to **Nuclear Music Player**.

An affirmative audio chime (`A5 -> E6`, 880 Hz to 1318 Hz) sounds directly through your headphones so you know the track was favorited without looking away from your work.

---

## 🎧 Sony WH-CH720N Tap Architecture

The Sony WH-CH720N headphones feature a multi-function playback button with standard firmware mappings. **Headphone Taps** preserves native behaviors while unlocking 4-click Likes:

| Headphone Action | Hardware / OS Keycode | Headphone Taps Result |
| :--- | :--- | :--- |
| **1 Click** | `VK_MEDIA_PLAY_PAUSE` (`0xB3`) | **Play / Pause** (Standard Windows media control) |
| **2 Clicks** | `VK_MEDIA_NEXT_TRACK` (`0xB0`) | **Next Track** (Skips to next song in queue) |
| **3 Clicks** | `VK_MEDIA_PREV_TRACK` (`0xB1`) | **Previous Track / Replay** (1st time replays current song from 0:00, consecutive press goes to previous track) |
| **4 Clicks** | Multi-tap Sequence | **❤️ LIKES CURRENT SONG IN NUCLEAR** |

### ⚡ How the 4-Click Discrimination Works:
1. When you press the center button **3 times**:
   - The headphone firmware emits `VK_MEDIA_PREV_TRACK`.
   - Headphone Taps intercepts the keystroke and sets a 420 ms evaluation timer.
   - **If no 4th click arrives within 420 ms:** The timer expires, and Headphone Taps transparently forwards `Previous Track` to Nuclear to replay or skip back.
2. When you press the center button **4 times**:
   - The 4th click arrives within the 420 ms window.
   - Headphone Taps immediately cancels the previous-track timer, suppresses the 4th click from pausing your music, and fires the **Like** action.
   - You hear an ascending two-tone confirmation chime in your headphones, and your song continues playing seamlessly.

---

## ⚡ Dual-Engine Nuclear Integration

Headphone Taps uses a resilient dual-engine architecture to interact with Nuclear Music Player:

```
[ Headphone Multi-Tap (4 Clicks) ]
               │
               ▼
   [ Windows WH_KEYBOARD_LL Hook ]
               │
      ┌────────┴────────┐
      ▼                 ▼
 [ Engine 1 ]      [ Engine 2 ]
Live WebSocket   Direct File Sync
  (Port 39281)     (Atomic JSON)
      │                 │
      ▼                 ▼
Nuclear Plugin   favorites.json &
API Dispatch       queue.json
      │                 │
      └────────┬────────┘
               ▼
[ In-App Toast + Audio Chime + Desktop Notification ]
```

1. **Engine 1 — Live WebSocket Companion Plugin (`ws://127.0.0.1:39281`)**:
   - Runs an in-process plugin inside Nuclear's Electron environment (`%APPDATA%\com.nuclearplayer\plugins`).
   - Invokes Nuclear's internal API (`api.Favorites.addTrack()`) for instant in-app heart animation, UI state update, and floating toast notification.
2. **Engine 2 — Direct Atomic Profile Sync (Fail-Safe)**:
   - Directly monitors Nuclear's active queue (`queue.json`).
   - Writes directly to `favorites.json` using atomic file swapping with ISO-8601 timestamps and canonical track metadata.
   - Functions autonomously even if plugins are disabled or while Nuclear is reloading.

---

## 🔔 Feedback Modes

- **In-Headphone Audio Chime**: Synthesized two-tone pleasant chime (`A5 -> E6`) using Windows audio primitives, giving immediate feedback without opening any windows.
- **Windows Desktop Toast**: Modern Windows notification displaying the liked track title and artist name.
- **Nuclear In-App Banner**: Floating glassmorphic notification rendered directly inside Nuclear Music Player.

---

## 🛠️ Installation & Setup

### Prerequisites
- Windows 10 or Windows 11
- Python 3.10 or higher
- [Nuclear Music Player](https://nuclear.js.org/)

### 1. Clone the Repository
```bash
git clone https://github.com/bhavyakumar-dev/headphone-taps.git
cd headphone-taps
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. One-Click Setup (Recommended)
Double-click `setup_startup.bat` or run:
```cmd
setup_startup.bat
```
This script will:
1. Register the companion plugin into your Nuclear profile.
2. Add a silent background entry to Windows Startup registry.
3. Launch Headphone Taps minimized to the system tray.

### 4. Manual Launch
To launch the Control Panel GUI directly:
```bash
python app/main.py
```
Or double-click `run.bat`.

---

## 🎛️ Interactive Headphone Button Tester

To calibrate or verify button timings on your specific headphone hardware:

```bash
python test_headphone_hook.py
```

Press your headphone buttons to see real-time virtual keycodes, tap intervals, and trigger detections in your terminal:
```text
[17:30:12.410] 🎧 Key: Previous Track (0xb1) | Tap Count: 1 -> 3 Clicks detected -> Waiting for 4th click...
[17:30:12.630] 🎧 Key: Play / Pause (0xb3)   | Tap Count: 2 -> ❤️ 4 Clicks (WH-CH720N) -> LIKED CURRENT SONG!
>>> [TRIGGER DETECTED] Translating to Nuclear Like action...
>>> Result: LIKED | 'Midnight City' by M83
```

---

## 📁 Repository Layout

```
headphone-taps/
├── app/
│   ├── __init__.py
│   ├── main.py                   # CLI & GUI entry point with arguments
│   ├── config.py                 # Persistent settings (%APPDATA%\NuclearHeart\config.json)
│   ├── headphone_listener.py     # Win32 WH_KEYBOARD_LL hook & multi-tap state machine
│   ├── nuclear_bridge.py         # Dual-engine WebSocket server & JSON file sync
│   ├── feedback.py               # Audio chime synthesizer & notification dispatch
│   ├── autostart.py              # Windows Registry startup manager
│   └── ui.py                     # PyQt6 dark control panel & system tray manager
├── nuclear-plugin/
│   ├── package.json              # Nuclear plugin manifest
│   └── index.js                  # Electron runtime plugin script
├── launch_silent.vbs             # Windows VBScript runner for silent boot
├── run.bat                       # Control panel launch batch script
├── setup_startup.bat             # 1-Click installer and autostart registration
├── test_headphone_hook.py        # Interactive CLI button tap tester
├── requirements.txt              # Python requirements (PyQt6, websockets, pywin32)
├── LICENSE                       # MIT License
└── README.md                     # Documentation
```

---

## ⚙️ Configuration Reference

Configuration is saved in `%APPDATA%\NuclearHeart\config.json`:

```json
{
  "trigger_mode": "four_clicks_wh720n",
  "multi_tap_timeout_ms": 650,
  "suppress_original_key": true,
  "audio_chime": true,
  "desktop_notifications": true,
  "start_with_windows": true,
  "start_minimized": true,
  "ws_port": 39281
}
```

Available trigger modes:
- `four_clicks_wh720n`: **4 Clicks** on Sony WH-CH720N (3 clicks = Previous Track/Replay).
- `four_taps_play`: 4 rapid taps on Play/Pause button.
- `triple_click_prev`: Triple-click Previous Track button.
- `double_tap_play`: 2 rapid taps on Play/Pause.
- `triple_tap_play`: 3 rapid taps on Play/Pause.
- `double_tap_next`: 2 rapid taps on Next Track button.
- `single_prev`: Remap single Previous Track button to Like.

---

## 📄 License

Distributed under the [MIT License](LICENSE). Copyright (c) 2026 Bhavya Kumar.
