import os
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider, QCheckBox, QFrame,
    QTextEdit, QSystemTrayIcon, QMenu, QGroupBox, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush, QAction

class SignalBridge(QObject):
    track_changed = pyqtSignal(dict)
    like_result = pyqtSignal(dict)
    key_event = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

def create_app_icon():
    """Generates a crisp modern purple heart tray icon using QPainter"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Rounded purple background tile
    painter.setBrush(QBrush(QColor("#9333ea")))
    painter.setPen(QPen(QColor("#c084fc"), 2))
    painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
    
    # White heart shape in the center
    painter.setBrush(QBrush(QColor("#ffffff")))
    painter.setPen(Qt.PenStyle.NoPen)
    
    # Draw heart using font emoji or polygon
    font = QFont("Segoe UI Emoji", 26)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "❤️")
    
    painter.end()
    return QIcon(pixmap)

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0d0d12;
    color: #e2e8f0;
    font-family: 'Segoe UI', -apple-system, sans-serif;
    font-size: 13px;
}

QFrame.card {
    background-color: #161622;
    border: 1px solid #28283d;
    border-radius: 12px;
    padding: 12px;
}

QLabel.title {
    font-size: 18px;
    font-weight: 800;
    color: #f8fafc;
}

QLabel.subtitle {
    font-size: 12px;
    color: #94a3b8;
}

QLabel.track_title {
    font-size: 16px;
    font-weight: 700;
    color: #f1f5f9;
}

QLabel.track_artist {
    font-size: 13px;
    color: #c084fc;
    font-weight: 600;
}

QPushButton.primary {
    background-color: #9333ea;
    color: #ffffff;
    font-weight: 700;
    border-radius: 8px;
    padding: 8px 16px;
    border: none;
}
QPushButton.primary:hover {
    background-color: #a855f7;
}
QPushButton.primary:pressed {
    background-color: #7e22ce;
}

QPushButton.secondary {
    background-color: #262638;
    color: #e2e8f0;
    border-radius: 8px;
    padding: 6px 14px;
    border: 1px solid #3b3b54;
}
QPushButton.secondary:hover {
    background-color: #32324a;
    border-color: #6366f1;
}

QComboBox {
    background-color: #1e1e2d;
    border: 1px solid #3b3b54;
    border-radius: 8px;
    padding: 6px 10px;
    color: #f1f5f9;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #1e1e2d;
    color: #f1f5f9;
    selection-background-color: #9333ea;
}

QCheckBox {
    spacing: 8px;
    color: #e2e8f0;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #475569;
    background: #1e1e2d;
}
QCheckBox::indicator:checked {
    background: #9333ea;
    border-color: #c084fc;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #27273a;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #9333ea;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #9333ea;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
}

QTextEdit {
    background-color: #111119;
    border: 1px solid #27273a;
    border-radius: 8px;
    color: #a1a1aa;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    padding: 6px;
}
"""

class MainWindow(QMainWindow):
    def __init__(self, config, bridge, listener, feedback, autostart):
        super().__init__()
        self.config = config
        self.bridge = bridge
        self.listener = listener
        self.feedback = feedback
        self.autostart = autostart
        
        self.signals = SignalBridge()
        self._init_signals()
        
        self.setWindowTitle("NuclearHeart - Headphone Like Translator")
        self.resize(600, 720)
        self.setStyleSheet(DARK_STYLESHEET)
        
        self.app_icon = create_app_icon()
        self.setWindowIcon(self.app_icon)
        
        self._setup_ui()
        self._setup_tray()
        
        # Periodic polling timer for Nuclear current track
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_status)
        self.poll_timer.start(2500)
        
        self._poll_status()

    def _init_signals(self):
        self.signals.track_changed.connect(self._on_track_changed)
        self.signals.like_result.connect(self._on_like_result)
        self.signals.key_event.connect(self._on_key_event)
        self.signals.connection_changed.connect(self._on_connection_changed)

        self.bridge.on_track_changed_callback = lambda t: self.signals.track_changed.emit(t)
        self.bridge.on_like_result_callback = lambda r: self.signals.like_result.emit(r)
        self.bridge.on_connection_status_callback = lambda c: self.signals.connection_changed.emit(c)
        if self.listener:
            self.listener.on_key_event = lambda e: self.signals.key_event.emit(e)

    def set_listener(self, listener):
        self.listener = listener
        if self.listener:
            self.listener.on_key_event = lambda e: self.signals.key_event.emit(e)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Top Header
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("NuclearHeart")
        title.setProperty("class", "title")
        subtitle = QLabel("Headphone Button to Like Translator for Nuclear Music Player")
        subtitle.setProperty("class", "subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        self.status_badge = QLabel("● Checking...")
        self.status_badge.setStyleSheet("font-weight: 700; color: #94a3b8; padding: 4px 10px; border-radius: 6px; background: #1e1e2e;")
        header_layout.addWidget(self.status_badge)
        layout.addLayout(header_layout)

        # 2. Now Playing Card
        now_card = QFrame()
        now_card.setProperty("class", "card")
        now_layout = QHBoxLayout(now_card)
        now_layout.setSpacing(16)

        self.album_art_label = QLabel("🎵")
        self.album_art_label.setFixedSize(70, 70)
        self.album_art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_art_label.setStyleSheet("background: #242436; border-radius: 8px; font-size: 32px;")
        now_layout.addWidget(self.album_art_label)

        info_layout = QVBoxLayout()
        self.song_title_label = QLabel("Waiting for Nuclear Player...")
        self.song_title_label.setProperty("class", "track_title")
        self.song_artist_label = QLabel("Start playback in Nuclear")
        self.song_artist_label.setProperty("class", "track_artist")
        self.fav_status_label = QLabel("🤍 Not in Favorites")
        self.fav_status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        
        info_layout.addWidget(self.song_title_label)
        info_layout.addWidget(self.song_artist_label)
        info_layout.addWidget(self.fav_status_label)
        now_layout.addLayout(info_layout, stretch=1)

        self.btn_manual_like = QPushButton("❤️ Like Song")
        self.btn_manual_like.setProperty("class", "primary")
        self.btn_manual_like.setMinimumHeight(44)
        self.btn_manual_like.clicked.connect(self.trigger_like_action)
        now_layout.addWidget(self.btn_manual_like)
        layout.addWidget(now_card)

        # 3. Headphone Button Trigger Settings
        trigger_card = QFrame()
        trigger_card.setProperty("class", "card")
        t_layout = QVBoxLayout(trigger_card)
        t_layout.setSpacing(10)

        t_title = QLabel("🎧 Headphone Button Trigger")
        t_title.setStyleSheet("font-weight: 700; color: #f1f5f9;")
        t_layout.addWidget(t_title)

        mode_row = QHBoxLayout()
        mode_label = QLabel("Action Trigger:")
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("🎧 Sony WH-CH720N (4 Clicks = Like, 3 Clicks = Prev/Replay)", "four_clicks_wh720n")
        self.combo_mode.addItem("🎧 4 Taps Play/Pause Button", "four_taps_play")
        self.combo_mode.addItem("Triple-Click (Previous Track) [AirPods, Bose, Buds]", "triple_click_prev")
        self.combo_mode.addItem("Double-Tap Play/Pause Button", "double_tap_play")
        self.combo_mode.addItem("Triple-Tap Play/Pause Button", "triple_tap_play")
        self.combo_mode.addItem("Double-Tap Next Track Button", "double_tap_next")
        self.combo_mode.addItem("Single-Click Previous Track Button", "single_prev")

        current_mode = self.config.get("trigger_mode", "four_clicks_wh720n")
        idx = self.combo_mode.findData(current_mode)
        if idx >= 0:
            self.combo_mode.setCurrentIndex(idx)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.combo_mode, stretch=1)
        t_layout.addLayout(mode_row)

        # Timeout slider
        timeout_row = QHBoxLayout()
        self.timeout_label = QLabel("Multi-tap Timeout: 650 ms")
        self.slider_timeout = QSlider(Qt.Orientation.Horizontal)
        self.slider_timeout.setRange(300, 1200)
        self.slider_timeout.setValue(self.config.get("multi_tap_timeout_ms", 650))
        self.slider_timeout.valueChanged.connect(self._on_timeout_changed)
        timeout_row.addWidget(self.timeout_label)
        timeout_row.addWidget(self.slider_timeout, stretch=1)
        t_layout.addLayout(timeout_row)

        self.cb_suppress = QCheckBox("Suppress original media key event when triggered (prevent rewind/skip)")
        self.cb_suppress.setChecked(self.config.get("suppress_original_key", True))
        self.cb_suppress.toggled.connect(lambda v: self.config.set("suppress_original_key", v))
        t_layout.addWidget(self.cb_suppress)

        layout.addWidget(trigger_card)

        # 4. Feedback & Feedback settings
        fb_card = QFrame()
        fb_card.setProperty("class", "card")
        fb_layout = QVBoxLayout(fb_card)
        fb_layout.setSpacing(10)

        fb_title = QLabel("🔔 Audio & Visual Feedback")
        fb_title.setStyleSheet("font-weight: 700; color: #f1f5f9;")
        fb_layout.addWidget(fb_title)

        fb_row = QHBoxLayout()
        self.cb_chime = QCheckBox("Audio Chime in Headphones on Like")
        self.cb_chime.setChecked(self.config.get("audio_chime", True))
        self.cb_chime.toggled.connect(lambda v: self.config.set("audio_chime", v))
        
        btn_test_chime = QPushButton("Test Chime 🔊")
        btn_test_chime.setProperty("class", "secondary")
        btn_test_chime.clicked.connect(lambda: self.feedback.play_chime("liked"))
        fb_row.addWidget(self.cb_chime)
        fb_row.addWidget(btn_test_chime)
        fb_layout.addLayout(fb_row)

        self.cb_notif = QCheckBox("Show Windows Desktop Notification on Like")
        self.cb_notif.setChecked(self.config.get("desktop_notifications", True))
        self.cb_notif.toggled.connect(lambda v: self.config.set("desktop_notifications", v))
        fb_layout.addWidget(self.cb_notif)

        layout.addWidget(fb_card)

        # 5. Startup & Plugin Integration
        sys_card = QFrame()
        sys_card.setProperty("class", "card")
        sys_layout = QHBoxLayout(sys_card)
        sys_layout.setSpacing(12)

        self.cb_startup = QCheckBox("Run on Windows Startup")
        self.cb_startup.setChecked(self.autostart.is_enabled())
        self.cb_startup.toggled.connect(self._on_startup_toggled)
        sys_layout.addWidget(self.cb_startup)

        sys_layout.addStretch()

        self.btn_plugin = QPushButton("Install Nuclear Companion Plugin")
        self.btn_plugin.setProperty("class", "secondary")
        self.btn_plugin.clicked.connect(self._on_install_plugin_clicked)
        sys_layout.addWidget(self.btn_plugin)
        layout.addWidget(sys_card)

        # 6. Live Headphone Button Event Log
        log_card = QFrame()
        log_card.setProperty("class", "card")
        l_layout = QVBoxLayout(log_card)
        l_layout.setSpacing(6)

        l_head = QHBoxLayout()
        l_title = QLabel("⚡ Live Headphone Button Monitor")
        l_title.setStyleSheet("font-weight: 700; color: #94a3b8; font-size: 11px;")
        self.lbl_tap_indicator = QLabel("")
        self.lbl_tap_indicator.setStyleSheet("color: #a855f7; font-weight: 700; font-size: 11px;")
        l_head.addWidget(l_title)
        l_head.addStretch()
        l_head.addWidget(self.lbl_tap_indicator)
        l_layout.addLayout(l_head)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(110)
        self.log_text.append("[System] Headphone listener active. Press your headphone button to test...")
        l_layout.addWidget(self.log_text)

        layout.addWidget(log_card)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self.app_icon, self)
        self.tray.setToolTip("NuclearHeart - Headphone Like Translator")
        self.feedback.set_tray_icon(self.tray)

        tray_menu = QMenu()
        tray_menu.setStyleSheet("background-color: #1a1a26; color: #f1f5f9; border: 1px solid #33334d;")

        act_open = QAction("Open Control Panel", self)
        act_open.triggered.connect(self.show_and_activate)
        tray_menu.addAction(act_open)

        self.act_tray_like = QAction("❤️ Like Current Track", self)
        self.act_tray_like.triggered.connect(self.trigger_like_action)
        tray_menu.addAction(self.act_tray_like)

        tray_menu.addSeparator()

        act_chime = QAction("Audio Chime", self, checkable=True)
        act_chime.setChecked(self.config.get("audio_chime", True))
        act_chime.toggled.connect(lambda v: self.config.set("audio_chime", v))
        tray_menu.addAction(act_chime)

        act_startup = QAction("Run on Windows Startup", self, checkable=True)
        act_startup.setChecked(self.autostart.is_enabled())
        act_startup.toggled.connect(self._on_startup_toggled)
        tray_menu.addAction(act_startup)

        tray_menu.addSeparator()

        act_exit = QAction("Exit NuclearHeart", self)
        act_exit.triggered.connect(self.exit_app)
        tray_menu.addAction(act_exit)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_and_activate()

    def show_and_activate(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        # Minimize to tray instead of quitting
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "NuclearHeart Running",
            "NuclearHeart is running in your system tray. Click headphone button to Like songs anytime!",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

    def exit_app(self):
        if self.listener:
            self.listener.stop()
        self.bridge.stop_websocket_server()
        self.tray.hide()
        QApplication.quit()

    def _on_mode_changed(self, index):
        mode = self.combo_mode.itemData(index)
        self.config.set("trigger_mode", mode)
        self.log_text.append(f"[Config] Trigger mode updated: {self.combo_mode.currentText()}")

    def _on_timeout_changed(self, val):
        self.timeout_label.setText(f"Multi-tap Timeout: {val} ms")
        self.config.set("multi_tap_timeout_ms", val)

    def _on_startup_toggled(self, checked):
        success = self.autostart.set_enabled(checked)
        self.cb_startup.setChecked(self.autostart.is_enabled())
        if success:
            self.log_text.append(f"[Autostart] Windows startup {'enabled' if checked else 'disabled'}")

    def _on_install_plugin_clicked(self):
        success, msg = self.bridge.install_companion_plugin()
        if success:
            QMessageBox.information(
                self, "Plugin Installed",
                "Nuclear Companion Plugin installed successfully!\n\n"
                "If Nuclear Player is currently running, restart it once so Nuclear loads the plugin into memory."
            )
            self.btn_plugin.setText("Plugin Installed ✓")
            self.btn_plugin.setStyleSheet("color: #10b981; border-color: #10b981;")
            self.log_text.append("[Plugin] Installed companion plugin into Nuclear profile")
        else:
            QMessageBox.warning(self, "Installation Failed", f"Failed to install plugin: {msg}")

    def _poll_status(self):
        is_running = self.bridge.is_nuclear_running()
        is_ws_connected = bool(self.bridge.connected_clients)

        if is_ws_connected:
            self.status_badge.setText("● Nuclear Connected (Live Plugin)")
            self.status_badge.setStyleSheet("font-weight: 700; color: #10b981; padding: 4px 10px; border-radius: 6px; background: rgba(16, 185, 129, 0.15);")
        elif is_running:
            self.status_badge.setText("● Nuclear Active (File Sync)")
            self.status_badge.setStyleSheet("font-weight: 700; color: #38bdf8; padding: 4px 10px; border-radius: 6px; background: rgba(56, 189, 248, 0.15);")
        else:
            self.status_badge.setText("● Nuclear Offline")
            self.status_badge.setStyleSheet("font-weight: 700; color: #ef4444; padding: 4px 10px; border-radius: 6px; background: rgba(239, 68, 68, 0.15);")

        track = self.bridge.get_current_track_from_file()
        if track:
            self._update_track_ui(track)

        if self.bridge.is_companion_plugin_installed():
            self.btn_plugin.setText("Companion Plugin Active ✓")
            self.btn_plugin.setStyleSheet("color: #10b981; border-color: #10b981;")

    def _on_connection_changed(self, connected):
        self._poll_status()

    def _on_track_changed(self, track):
        self._update_track_ui(track)

    def _update_track_ui(self, track):
        title = track.get("title", "Unknown Track")
        artist = track.get("artist", "Unknown Artist")
        is_fav = track.get("isFavorite", False)

        self.song_title_label.setText(title)
        self.song_artist_label.setText(artist)

        if is_fav:
            self.fav_status_label.setText("❤️ In Nuclear Favorites")
            self.fav_status_label.setStyleSheet("color: #ec4899; font-weight: 700;")
            self.btn_manual_like.setText("❤️ Favorited")
            self.btn_manual_like.setEnabled(False)
            self.btn_manual_like.setStyleSheet("background: #2e1065; color: #c084fc;")
        else:
            self.fav_status_label.setText("🤍 Not in Favorites")
            self.fav_status_label.setStyleSheet("color: #94a3b8;")
            self.btn_manual_like.setText("❤️ Like Song")
            self.btn_manual_like.setEnabled(True)
            self.btn_manual_like.setStyleSheet("")

        self.tray.setToolTip(f"NuclearHeart: {title} - {artist}")

    def _on_key_event(self, event):
        key_name = event["key_name"]
        count = event["tap_count"]
        triggered = event["triggered"]
        action_desc = event.get("action_desc", "")
        
        now_str = datetime.now().strftime("%H:%M:%S")
        if triggered:
            msg = f"[{now_str}] 🎧 {action_desc or f'{key_name} -> ❤️ TRIGGERED LIKE!'}"
            self.lbl_tap_indicator.setText("❤️ LIKE TRIGGERED!")
            self.lbl_tap_indicator.setStyleSheet("color: #ec4899; font-weight: 800; font-size: 11px;")
        elif action_desc:
            msg = f"[{now_str}] 🎧 {action_desc}"
            self.lbl_tap_indicator.setText(f"Tap #{count}")
            self.lbl_tap_indicator.setStyleSheet("color: #a855f7; font-weight: 600; font-size: 11px;")
        else:
            msg = f"[{now_str}] 🎧 Detected {key_name} (Tap #{count})"
            self.lbl_tap_indicator.setText(f"Tap #{count}")
            self.lbl_tap_indicator.setStyleSheet("color: #a855f7; font-weight: 600; font-size: 11px;")

        self.log_text.append(msg)

    def _on_like_result(self, result):
        status = result.get("status")
        title = result.get("title", "")
        artist = result.get("artist", "")
        
        now_str = datetime.now().strftime("%H:%M:%S")
        if status == "liked":
            self.log_text.append(f"[{now_str}] ❤️ Successfully liked: {title} - {artist}")
            self.fav_status_label.setText("❤️ In Nuclear Favorites")
            self.fav_status_label.setStyleSheet("color: #ec4899; font-weight: 700;")
            self.btn_manual_like.setText("❤️ Favorited")
            self.btn_manual_like.setEnabled(False)
            self.feedback.play_chime("liked")
            self.feedback.show_notification("❤️ Track Liked in Nuclear", f"{title}\n{artist}")

        elif status == "already_favorite":
            self.log_text.append(f"[{now_str}] ℹ️ Already in favorites: {title}")
            self.feedback.play_chime("already_favorite")
            self.feedback.show_notification("ℹ️ Already in Favorites", f"{title} is already favorited!")

    def trigger_like_action(self):
        success, status, track_info = self.bridge.trigger_like()
        now_str = datetime.now().strftime("%H:%M:%S")

        if track_info:
            title = track_info.get("title", "")
            artist = track_info.get("artist", "")
        else:
            title = "No Track"
            artist = ""

        if status == "command_sent_to_plugin":
            self.log_text.append(f"[{now_str}] 📡 Like command dispatched to Nuclear plugin...")
            # Feedback will arrive in _on_like_result callback from plugin!

        elif status == "liked":
            self.log_text.append(f"[{now_str}] ❤️ Added to Nuclear favorites: {title}")
            self.feedback.play_chime("liked")
            self.feedback.show_notification("❤️ Track Liked in Nuclear", f"{title}\n{artist}")
            self._poll_status()

        elif status == "already_favorite":
            self.log_text.append(f"[{now_str}] ℹ️ Track is already in favorites: {title}")
            self.feedback.play_chime("already_favorite")
            self.feedback.show_notification("ℹ️ Already in Favorites", f"{title} is already favorited!")
            self._poll_status()

        elif status == "no_track_playing":
            self.log_text.append(f"[{now_str}] ⚠️ No track currently playing in Nuclear.")
            self.feedback.play_chime("error")
            self.feedback.show_notification("NuclearHeart", "No track currently playing in Nuclear.")
