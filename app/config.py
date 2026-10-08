import os
import json
from pathlib import Path

DEFAULT_CONFIG = {
    "trigger_mode": "four_clicks_wh720n",  # four_clicks_wh720n, four_taps_play, triple_click_prev, double_tap_play, triple_tap_play, double_tap_next, single_prev
    "multi_tap_timeout_ms": 650,
    "suppress_original_key": True,
    "audio_chime": True,
    "desktop_notifications": True,
    "start_with_windows": True,
    "start_minimized": True,
    "ws_port": 39281,
    "nuclear_profile_dir": ""
}

class AppConfig:
    def __init__(self):
        appdata = os.environ.get("APPDATA", "")
        self.config_dir = Path(appdata) / "NuclearHeart" if appdata else Path.home() / ".nuclearheart"
        self.config_file = self.config_dir / "config.json"
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
        except Exception as e:
            print(f"[Config] Error loading config: {e}")

    def save(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

config = AppConfig()
