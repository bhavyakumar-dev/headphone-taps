import ctypes
import ctypes.wintypes as wintypes
import time
import sys
import threading

def _safe_print(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            encoding = sys.stdout.encoding or "utf-8"
            print(msg.encode(encoding, errors="replace").decode(encoding))
        except Exception:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
    except Exception:
        pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

# Virtual key codes
VK_MEDIA_NEXT_TRACK = 0xB0  # 176
VK_MEDIA_PREV_TRACK = 0xB1  # 177
VK_MEDIA_STOP = 0xB2        # 178
VK_MEDIA_PLAY_PAUSE = 0xB3  # 179
VK_VOLUME_MUTE = 0xAD       # 173
VK_VOLUME_DOWN = 0xAE       # 174
VK_VOLUME_UP = 0xAF         # 175

KEY_NAMES = {
    VK_MEDIA_PLAY_PAUSE: "Play / Pause",
    VK_MEDIA_NEXT_TRACK: "Next Track",
    VK_MEDIA_PREV_TRACK: "Previous Track",
    VK_MEDIA_STOP: "Stop",
    VK_VOLUME_MUTE: "Volume Mute",
    VK_VOLUME_DOWN: "Volume Down",
    VK_VOLUME_UP: "Volume Up",
}

LRESULT = ctypes.c_int64
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

# Explicit 64-bit Win32 API signatures to prevent 32-bit c_int truncation and OverflowError
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode', wintypes.DWORD),
        ('scanCode', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_ulonglong)
    ]

EXTRA_INFO_SYNTHETIC = 0xDEADC0DE

class HeadphoneListener:
    def __init__(self, config, on_trigger_like=None, on_trigger_previous=None, on_key_event=None):
        self.config = config
        self.on_trigger_like = on_trigger_like
        self.on_trigger_previous = on_trigger_previous
        self.on_key_event = on_key_event
        
        self.hook = None
        self.hook_thread = None
        self.hook_thread_id = None
        self._hook_proc_ref = None  # Prevent GC of ctypes callback
        
        # State tracking for multi-taps & sequences
        self._last_key = None
        self._tap_count = 0
        self._last_tap_time = 0.0
        self._lock = threading.Lock()

        # Specific state for Sony WH-CH720N (4-Clicks like, 3-clicks prev/replay)
        self._pending_prev_timer = None
        self._prev_click_time = 0.0

    def _hook_callback(self, nCode, wParam, lParam):
        if not lParam:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            try:
                kbd = KBDLLHOOKSTRUCT.from_address(lParam)
                
                # If this is our own synthetic replay, let it pass straight through
                if kbd.dwExtraInfo == EXTRA_INFO_SYNTHETIC:
                    return user32.CallNextHookEx(None, nCode, wParam, lParam)

                vk_code = kbd.vkCode
                
                # Check if it's a media key
                if vk_code in KEY_NAMES:
                    suppress = self._handle_media_key(vk_code)
                    if suppress and self.config.get("suppress_original_key", True):
                        return 1  # Swallow key event
            except Exception as e:
                _safe_print(f"[HeadphoneListener] Hook callback error: {e}")

        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _on_prev_timeout(self):
        """Called when 3 clicks occurred on WH-CH720N and no 4th click followed"""
        with self._lock:
            self._pending_prev_timer = None
            self._prev_click_time = 0.0

        _safe_print("[HeadphoneListener] WH-CH720N: 3 Clicks confirmed -> Previous Track / Replay")
        if self.on_key_event:
            self.on_key_event({
                "vk_code": VK_MEDIA_PREV_TRACK,
                "key_name": "Previous Track (3 Clicks)",
                "tap_count": 3,
                "timestamp": time.time(),
                "triggered": False,
                "action_desc": "3 Clicks: Replaying / Previous Track"
            })

        if self.on_trigger_previous:
            threading.Thread(target=self.on_trigger_previous, daemon=True).start()

    def _handle_media_key(self, vk_code):
        now = time.time()
        timeout = self.config.get("multi_tap_timeout_ms", 650) / 1000.0
        mode = self.config.get("trigger_mode", "four_clicks_wh720n")
        key_name = KEY_NAMES.get(vk_code, f"Key 0x{vk_code:02X}")

        with self._lock:
            if self._last_key == vk_code and (now - self._last_tap_time) < timeout:
                self._tap_count += 1
            else:
                self._tap_count = 1
                self._last_key = vk_code

            self._last_tap_time = now
            current_count = self._tap_count

        should_trigger_like = False
        suppress_key = False
        action_desc = ""

        # =========================================================================
        # Mode: four_clicks_wh720n (Sony WH-CH720N)
        # 3 Clicks natively emits VK_MEDIA_PREV_TRACK (replays/previous track)
        # 4 Clicks emits VK_MEDIA_PREV_TRACK + VK_MEDIA_PLAY_PAUSE within ~650ms
        # =========================================================================
        if mode == "four_clicks_wh720n":
            if vk_code == VK_MEDIA_PREV_TRACK:
                # 3rd click reached!
                with self._lock:
                    if self._pending_prev_timer:
                        self._pending_prev_timer.cancel()
                    self._prev_click_time = now
                    # Delay 420ms to see if a 4th click arrives
                    self._pending_prev_timer = threading.Timer(0.42, self._on_prev_timeout)
                    self._pending_prev_timer.start()

                suppress_key = True  # Hold back event until 420ms timer decides
                action_desc = "3 Clicks detected -> Waiting for 4th click..."

            elif vk_code == VK_MEDIA_PLAY_PAUSE:
                time_since_prev = now - self._prev_click_time
                is_4th_click = (self._pending_prev_timer is not None or time_since_prev < 0.65) or (current_count == 4)

                if is_4th_click:
                    # 4TH CLICK CONFIRMED!
                    with self._lock:
                        if self._pending_prev_timer:
                            self._pending_prev_timer.cancel()
                            self._pending_prev_timer = None
                        self._prev_click_time = 0.0

                    should_trigger_like = True
                    suppress_key = True
                    action_desc = "❤️ 4 Clicks (WH-CH720N) -> LIKED CURRENT SONG!"
                else:
                    action_desc = f"Play/Pause (Tap #{current_count})"

            elif current_count == 4:
                # 4 taps on any button
                should_trigger_like = True
                suppress_key = True
                action_desc = "❤️ 4 Clicks -> LIKED CURRENT SONG!"

        elif mode == "four_taps_play":
            if vk_code == VK_MEDIA_PLAY_PAUSE and current_count >= 4:
                should_trigger_like = True
                suppress_key = True
                action_desc = "❤️ 4 Taps Play/Pause -> LIKED CURRENT SONG!"

        elif mode == "triple_click_prev":
            if vk_code == VK_MEDIA_PREV_TRACK:
                should_trigger_like = True
                suppress_key = True
                action_desc = "❤️ 3 Clicks (Prev) -> LIKED CURRENT SONG!"

        elif mode == "double_tap_play":
            if vk_code == VK_MEDIA_PLAY_PAUSE and current_count == 2:
                should_trigger_like = True
                suppress_key = True
                action_desc = "❤️ 2 Taps Play/Pause -> LIKED CURRENT SONG!"

        elif mode == "triple_tap_play":
            if vk_code == VK_MEDIA_PLAY_PAUSE and current_count >= 3:
                should_trigger_like = True
                suppress_key = True
                action_desc = "❤️ 3 Taps Play/Pause -> LIKED CURRENT SONG!"

        elif mode == "double_tap_next":
            if vk_code == VK_MEDIA_NEXT_TRACK and current_count == 2:
                should_trigger_like = True
                suppress_key = True
                action_desc = "❤️ 2 Taps Next Track -> LIKED CURRENT SONG!"

        elif mode == "single_prev":
            if vk_code == VK_MEDIA_PREV_TRACK:
                should_trigger_like = True
                suppress_key = True
                action_desc = "❤️ Previous Track Button -> LIKED CURRENT SONG!"

        # Notify UI event log
        if self.on_key_event:
            self.on_key_event({
                "vk_code": vk_code,
                "key_name": key_name,
                "tap_count": current_count,
                "timestamp": now,
                "triggered": should_trigger_like,
                "action_desc": action_desc
            })

        if should_trigger_like:
            _safe_print(f"[HeadphoneListener] {action_desc}")
            if self.on_trigger_like:
                threading.Thread(target=self.on_trigger_like, daemon=True).start()

        return suppress_key

    def start(self):
        if self.hook_thread and self.hook_thread.is_alive():
            return

        ready_event = threading.Event()

        def _thread_target():
            self.hook_thread_id = kernel32.GetCurrentThreadId()
            self._hook_proc_ref = HOOKPROC(self._hook_callback)
            
            h_mod = kernel32.GetModuleHandleW(None)
            self.hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc_ref, h_mod, 0)
            if not self.hook:
                err = kernel32.GetLastError()
                _safe_print(f"[HeadphoneListener] Failed to set hook! Error: {err}")
                ready_event.set()
                return

            _safe_print(f"[HeadphoneListener] Low-level hook installed successfully (Thread ID {self.hook_thread_id})")
            ready_event.set()

            # Win32 Message Loop
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            if self.hook:
                user32.UnhookWindowsHookEx(self.hook)
                self.hook = None
            _safe_print("[HeadphoneListener] Hook uninstalled cleanly")

        self.hook_thread = threading.Thread(target=_thread_target, daemon=True)
        self.hook_thread.start()
        ready_event.wait(timeout=2.0)

    def stop(self):
        with self._lock:
            if self._pending_prev_timer:
                self._pending_prev_timer.cancel()
                self._pending_prev_timer = None

        if self.hook_thread_id:
            user32.PostThreadMessageW(self.hook_thread_id, WM_QUIT, 0, 0)
        if self.hook_thread and self.hook_thread.is_alive():
            self.hook_thread.join(timeout=1.0)
