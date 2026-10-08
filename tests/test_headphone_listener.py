import ctypes
import ctypes.wintypes as wintypes
import time
import unittest
from unittest.mock import MagicMock

from app.config import config
from app.headphone_listener import (
    HeadphoneListener,
    KBDLLHOOKSTRUCT,
    EXTRA_INFO_SYNTHETIC,
    LRESULT,
    HOOKPROC,
    user32,
    kernel32,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_SYSKEYDOWN,
    VK_MEDIA_NEXT_TRACK,
    VK_MEDIA_PREV_TRACK,
    VK_MEDIA_PLAY_PAUSE,
)
from app.nuclear_bridge import NuclearBridge


class TestHeadphoneListener64Bit(unittest.TestCase):
    """Test suite verifying 64-bit ctypes Win32 API signatures and hook callback robustness."""

    def test_ctypes_signatures(self):
        """Verify explicit argtypes and restype are configured on Win32 functions."""
        # user32.CallNextHookEx
        self.assertEqual(
            user32.CallNextHookEx.argtypes,
            [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        )
        self.assertEqual(user32.CallNextHookEx.restype, LRESULT)

        # user32.SetWindowsHookExW
        self.assertEqual(
            user32.SetWindowsHookExW.argtypes,
            [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        )
        self.assertEqual(user32.SetWindowsHookExW.restype, wintypes.HHOOK)

        # user32.UnhookWindowsHookEx
        self.assertEqual(user32.UnhookWindowsHookEx.argtypes, [wintypes.HHOOK])
        self.assertEqual(user32.UnhookWindowsHookEx.restype, wintypes.BOOL)

        # user32.GetMessageW
        self.assertEqual(
            user32.GetMessageW.argtypes,
            [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        )
        self.assertEqual(user32.GetMessageW.restype, wintypes.BOOL)

        # user32.TranslateMessage
        self.assertEqual(
            user32.TranslateMessage.argtypes,
            [ctypes.POINTER(wintypes.MSG)]
        )
        self.assertEqual(user32.TranslateMessage.restype, wintypes.BOOL)

        # user32.DispatchMessageW
        self.assertEqual(
            user32.DispatchMessageW.argtypes,
            [ctypes.POINTER(wintypes.MSG)]
        )
        self.assertEqual(user32.DispatchMessageW.restype, LRESULT)

        # user32.PostThreadMessageW
        self.assertEqual(
            user32.PostThreadMessageW.argtypes,
            [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        )
        self.assertEqual(user32.PostThreadMessageW.restype, wintypes.BOOL)

        # kernel32.GetModuleHandleW
        self.assertEqual(kernel32.GetModuleHandleW.argtypes, [wintypes.LPCWSTR])
        self.assertEqual(kernel32.GetModuleHandleW.restype, wintypes.HMODULE)

        # kernel32.GetCurrentThreadId
        self.assertEqual(kernel32.GetCurrentThreadId.argtypes, [])
        self.assertEqual(kernel32.GetCurrentThreadId.restype, wintypes.DWORD)

        # kernel32.GetLastError
        self.assertEqual(kernel32.GetLastError.argtypes, [])
        self.assertEqual(kernel32.GetLastError.restype, wintypes.DWORD)

    def test_call_next_hook_ex_with_64bit_lparam(self):
        """Verify user32.CallNextHookEx accepts full 64-bit pointer values without OverflowError."""
        test_addresses = [
            0x000001BE0B9FBCD0,  # Example heap address from user bug report
            0x00007FF666F20000,  # Typical 64-bit module address space
            0x00007FFFFFFFF000,  # Near upper 48-bit user mode limit
            0x7FFFFFFFFFFFFFFF,  # Max positive 64-bit signed int
            0xFFFFFFFFFFFFFFFF,  # -1 / 64-bit all-ones
            0,                   # NULL pointer
        ]

        for addr in test_addresses:
            with self.subTest(addr=hex(addr)):
                try:
                    result = user32.CallNextHookEx(None, 0, WM_KEYDOWN, addr)
                    self.assertIsInstance(result, int)
                except ctypes.ArgumentError as e:
                    self.fail(f"user32.CallNextHookEx raised ArgumentError for address {hex(addr)}: {e}")

    def test_hook_callback_non_media_key_passes_through(self):
        """Simulate a regular key event (e.g. 'A') to ensure _hook_callback delegates cleanly."""
        listener = HeadphoneListener(config)

        kbd = KBDLLHOOKSTRUCT(
            vkCode=0x41,  # 'A' key
            scanCode=0x1E,
            flags=0,
            time=1000,
            dwExtraInfo=0
        )
        lParam = ctypes.addressof(kbd)

        # Call _hook_callback with real 64-bit lParam pointer
        result = listener._hook_callback(0, WM_KEYDOWN, lParam)
        self.assertEqual(result, 0)

    def test_hook_callback_synthetic_event_passes_through(self):
        """Simulate an event with EXTRA_INFO_SYNTHETIC to ensure it calls CallNextHookEx directly."""
        listener = HeadphoneListener(config)

        kbd = KBDLLHOOKSTRUCT(
            vkCode=VK_MEDIA_PREV_TRACK,
            scanCode=0,
            flags=0,
            time=1000,
            dwExtraInfo=EXTRA_INFO_SYNTHETIC
        )
        lParam = ctypes.addressof(kbd)

        result = listener._hook_callback(0, WM_KEYDOWN, lParam)
        self.assertEqual(result, 0)

    def test_hook_callback_negative_ncode_passes_through(self):
        """Per Win32 spec, negative nCode must immediately be forwarded without processing."""
        listener = HeadphoneListener(config)

        kbd = KBDLLHOOKSTRUCT(
            vkCode=VK_MEDIA_PLAY_PAUSE,
            scanCode=0,
            flags=0,
            time=1000,
            dwExtraInfo=0
        )
        lParam = ctypes.addressof(kbd)

        result = listener._hook_callback(-1, WM_KEYDOWN, lParam)
        self.assertEqual(result, 0)

    def test_hook_callback_keyup_ignored_and_passed_through(self):
        """WM_KEYUP events should be passed through without triggering action."""
        listener = HeadphoneListener(config)

        kbd = KBDLLHOOKSTRUCT(
            vkCode=VK_MEDIA_PLAY_PAUSE,
            scanCode=0,
            flags=0,
            time=1000,
            dwExtraInfo=0
        )
        lParam = ctypes.addressof(kbd)

        result = listener._hook_callback(0, WM_KEYUP, lParam)
        self.assertEqual(result, 0)

    def test_sony_wh720n_four_clicks_triggers_like(self):
        """Simulate Sony WH-CH720N 4-click sequence (Prev Track + Play/Pause within timeout)."""
        on_like = MagicMock()
        on_prev = MagicMock()
        listener = HeadphoneListener(
            {"trigger_mode": "four_clicks_wh720n", "suppress_original_key": True, "multi_tap_timeout_ms": 650},
            on_trigger_like=on_like,
            on_trigger_previous=on_prev
        )

        kbd_prev = KBDLLHOOKSTRUCT(vkCode=VK_MEDIA_PREV_TRACK, scanCode=0, flags=0, time=100, dwExtraInfo=0)
        kbd_play = KBDLLHOOKSTRUCT(vkCode=VK_MEDIA_PLAY_PAUSE, scanCode=0, flags=0, time=200, dwExtraInfo=0)

        # 1. 3 clicks emit VK_MEDIA_PREV_TRACK -> suppressed while waiting for 4th click
        res1 = listener._hook_callback(0, WM_KEYDOWN, ctypes.addressof(kbd_prev))
        self.assertEqual(res1, 1, "Prev track should be suppressed pending 4th click")

        # 2. 4th click emits VK_MEDIA_PLAY_PAUSE promptly
        res2 = listener._hook_callback(0, WM_KEYDOWN, ctypes.addressof(kbd_play))
        self.assertEqual(res2, 1, "Play/Pause 4th click should be suppressed and trigger like")

        # Give the spawned daemon thread a moment to fire
        time.sleep(0.05)
        on_like.assert_called_once()
        on_prev.assert_not_called()

        # Clean up any leftover timers
        listener.stop()

    def test_sony_wh720n_three_clicks_triggers_previous_on_timeout(self):
        """Simulate Sony WH-CH720N 3-click sequence where NO 4th click arrives -> fires prev."""
        on_like = MagicMock()
        on_prev = MagicMock()
        listener = HeadphoneListener(
            {"trigger_mode": "four_clicks_wh720n", "suppress_original_key": True, "multi_tap_timeout_ms": 650},
            on_trigger_like=on_like,
            on_trigger_previous=on_prev
        )

        kbd_prev = KBDLLHOOKSTRUCT(vkCode=VK_MEDIA_PREV_TRACK, scanCode=0, flags=0, time=100, dwExtraInfo=0)

        # 3 clicks emit VK_MEDIA_PREV_TRACK
        res = listener._hook_callback(0, WM_KEYDOWN, ctypes.addressof(kbd_prev))
        self.assertEqual(res, 1)

        # Wait for 420ms timer to expire
        time.sleep(0.55)

        on_like.assert_not_called()
        on_prev.assert_called_once()

        listener.stop()

    def test_nuclear_bridge_keybd_event_64bit(self):
        """Verify nuclear_bridge keybd_event handles 64-bit extra info without error."""
        bridge = NuclearBridge(config)
        # trigger_previous falls back to keybd_event when companion plugin is disconnected
        success = bridge.trigger_previous()
        self.assertTrue(success)

    def test_listener_lifecycle_start_and_stop(self):
        """Verify listener starts low-level hook and uninstalls cleanly without error."""
        listener = HeadphoneListener(config)
        listener.start()
        self.assertIsNotNone(listener.hook, "Hook handle should not be None after start()")
        self.assertIsNotNone(listener.hook_thread_id)
        self.assertTrue(listener.hook_thread.is_alive())

        # Stop and verify cleanup
        listener.stop()
        time.sleep(0.1)
        self.assertFalse(listener.hook_thread.is_alive())
        self.assertIsNone(listener.hook)

    def test_hook_callback_null_lparam_passes_through(self):
        """Verify NULL or 0 lParam safely forwards to CallNextHookEx without crash."""
        listener = HeadphoneListener(config)
        self.assertEqual(listener._hook_callback(0, WM_KEYDOWN, 0), 0)

    def test_other_trigger_modes(self):
        """Verify other trigger modes like double_tap_play work correctly."""
        modes = [
            ("four_taps_play", VK_MEDIA_PLAY_PAUSE, 4),
            ("triple_click_prev", VK_MEDIA_PREV_TRACK, 1),
            ("double_tap_play", VK_MEDIA_PLAY_PAUSE, 2),
            ("triple_tap_play", VK_MEDIA_PLAY_PAUSE, 3),
            ("double_tap_next", VK_MEDIA_NEXT_TRACK, 2),
            ("single_prev", VK_MEDIA_PREV_TRACK, 1),
        ]

        for mode, vk, required_taps in modes:
            with self.subTest(mode=mode):
                on_like = MagicMock()
                listener = HeadphoneListener(
                    {"trigger_mode": mode, "suppress_original_key": True, "multi_tap_timeout_ms": 650},
                    on_trigger_like=on_like
                )
                kbd = KBDLLHOOKSTRUCT(vkCode=vk, scanCode=0, flags=0, time=100, dwExtraInfo=0)
                lParam = ctypes.addressof(kbd)

                res = None
                for _ in range(required_taps):
                    res = listener._hook_callback(0, WM_KEYDOWN, lParam)

                self.assertEqual(res, 1)
                time.sleep(0.05)
                on_like.assert_called()
                listener.stop()


if __name__ == "__main__":
    unittest.main()
