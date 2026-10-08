import os
import sys
import argparse
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from app.config import config
from app.nuclear_bridge import NuclearBridge
from app.headphone_listener import HeadphoneListener
from app.feedback import FeedbackManager
from app.autostart import StartupManager
from app.ui import MainWindow

def main():
    parser = argparse.ArgumentParser(description="NuclearHeart - Headphone Button to Like Translator")
    parser.add_argument("--startup", action="store_true", help="Launch minimized to system tray on Windows boot")
    parser.add_argument("--minimized", action="store_true", help="Launch minimized to system tray")
    parser.add_argument("--install-plugin", action="store_true", help="Install Nuclear companion plugin and exit")
    parser.add_argument("--test-like", action="store_true", help="Trigger a like on currently playing song and exit")
    args = parser.parse_args()

    bridge = NuclearBridge(config)
    feedback = FeedbackManager(config)
    autostart = StartupManager()

    if args.install_plugin:
        success, msg = bridge.install_companion_plugin()
        print(f"Plugin install result: {success} ({msg})")
        return 0 if success else 1

    if args.test_like:
        success, status, track = bridge.trigger_like()
        print(f"Test like result: {status} for track: {track.get('title') if track else 'None'}")
        if status in ("liked", "already_favorite", "command_sent_to_plugin"):
            feedback.play_chime("liked")
        return 0

    # Start WebSocket server for companion plugin
    bridge.start_websocket_server()

    # Create Qt App
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Initialize main window
    window = MainWindow(config, bridge, None, feedback, autostart)

    # Initialize Headphone Listener hooked to trigger like and previous
    listener = HeadphoneListener(
        config,
        on_trigger_like=window.trigger_like_action,
        on_trigger_previous=bridge.trigger_previous
    )
    window.set_listener(listener)
    listener.start()

    # Determine whether to show UI on launch
    start_minimized = args.startup or args.minimized or config.get("start_minimized", False)
    if not start_minimized:
        window.show_and_activate()
    else:
        print("[NuclearHeart] Running in background system tray")

    # Run Qt Event Loop
    exit_code = app.exec()
    
    # Clean shutdown
    listener.stop()
    bridge.stop_websocket_server()
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
