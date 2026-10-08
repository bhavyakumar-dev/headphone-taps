import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.config import config
from app.headphone_listener import HeadphoneListener
from app.nuclear_bridge import NuclearBridge
from app.feedback import FeedbackManager

def main():
    print("=" * 60)
    print("   NuclearHeart - Headphone Button Interactive Tester")
    print("=" * 60)
    print("\nPress buttons on your Bluetooth or wired headphones...")
    print("Available buttons: Single/Double/Triple click, Play/Pause, Next, Prev.\n")
    print(f"Current Configured Trigger Mode: {config.get('trigger_mode')}")
    print(f"Multi-Tap Timeout: {config.get('multi_tap_timeout_ms')} ms")
    print("-" * 60)

    bridge = NuclearBridge(config)
    feedback = FeedbackManager(config)

    def on_like_triggered():
        print("\n>>> [TRIGGER DETECTED] Translating to Nuclear Like action...")
        success, status, track = bridge.trigger_like()
        if track:
            title = track.get("title", "Unknown")
            artist = track.get("artist", "Unknown")
            print(f">>> Result: {status.upper()} | '{title}' by {artist}")
            if status in ("liked", "already_favorite", "command_sent_to_plugin"):
                feedback.play_chime("liked")
        else:
            print(">>> Result: No track currently playing in Nuclear Player.")
            feedback.play_chime("error")
        print("-" * 60)

    def on_prev_triggered():
        print("\n>>> [3 CLICKS DETECTED] Triggering Previous Track / Replay in Nuclear...")
        bridge.trigger_previous()
        print("-" * 60)

    def on_key_event(event):
        now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        key = event["key_name"]
        vk = hex(event["vk_code"])
        count = event["tap_count"]
        triggered = event["triggered"]
        action_desc = event.get("action_desc", "")

        status_flag = f" -> {action_desc}" if action_desc else (" [MATCHED TRIGGER -> LIKE!]" if triggered else "")
        print(f"[{now_str}] 🎧 Key: {key} ({vk}) | Tap Count: {count}{status_flag}")

    listener = HeadphoneListener(
        config,
        on_trigger_like=on_like_triggered,
        on_trigger_previous=on_prev_triggered,
        on_key_event=on_key_event
    )

    listener.start()
    print("Hook active. Press Ctrl+C in this terminal to exit.\n")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping listener...")
        listener.stop()
        print("Done.")

if __name__ == "__main__":
    main()
