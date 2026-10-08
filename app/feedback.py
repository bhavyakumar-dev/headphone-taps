import threading
import time
import winsound

class FeedbackManager:
    def __init__(self, config):
        self.config = config
        self._tray_icon = None

    def set_tray_icon(self, tray_icon):
        self._tray_icon = tray_icon

    def play_chime(self, chime_type="liked"):
        if not self.config.get("audio_chime", True):
            return

        def _worker():
            try:
                if chime_type == "liked":
                    # Ascending two-tone cheerful chime (A5 -> E6)
                    winsound.Beep(880, 80)
                    time.sleep(0.02)
                    winsound.Beep(1318, 120)
                elif chime_type == "already_favorite":
                    # Soft double blip (C6, C6)
                    winsound.Beep(1046, 60)
                    time.sleep(0.04)
                    winsound.Beep(1046, 60)
                elif chime_type == "error":
                    # Low buzz (A4)
                    winsound.Beep(440, 150)
                else:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception as e:
                # Fallback to system message beep
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def show_notification(self, title, message, icon_type="info"):
        if not self.config.get("desktop_notifications", True):
            return

        if self._tray_icon:
            try:
                from PyQt6.QtWidgets import QSystemTrayIcon
                q_icon = QSystemTrayIcon.MessageIcon.Information
                if icon_type == "warning":
                    q_icon = QSystemTrayIcon.MessageIcon.Warning
                elif icon_type == "error":
                    q_icon = QSystemTrayIcon.MessageIcon.Critical

                self._tray_icon.showMessage(title, message, q_icon, 3000)
            except Exception as e:
                print(f"[Feedback] Notification error: {e}")
