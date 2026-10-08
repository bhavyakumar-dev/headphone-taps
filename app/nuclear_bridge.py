import os
import sys
import json
import time
import shutil
import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path

_user32 = None
if sys.platform == "win32":
    try:
        import ctypes
        import ctypes.wintypes as wintypes
        _user32 = ctypes.windll.user32
        _user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_ulonglong]
        _user32.keybd_event.restype = None
    except Exception:
        pass

class NuclearBridge:
    def __init__(self, config):
        self.config = config
        self.port = config.get("ws_port", 39281)
        self.profile_dir = self._find_nuclear_profile()
        self.connected_clients = set()
        self.server_thread = None
        self.loop = None
        self._stop_event = threading.Event()
        self._last_known_track = None
        
        # Callbacks
        self.on_track_changed_callback = None
        self.on_like_result_callback = None
        self.on_connection_status_callback = None

    def _find_nuclear_profile(self):
        custom = self.config.get("nuclear_profile_dir", "")
        if custom and os.path.isdir(custom):
            return Path(custom)
        
        appdata = os.environ.get("APPDATA", "")
        candidates = [
            Path(appdata) / "com.nuclearplayer",
            Path(appdata) / "nuclear"
        ]
        for c in candidates:
            if c.exists() and (c / "queue.json").exists():
                return c
        return candidates[0] if candidates else Path()

    def is_nuclear_running(self):
        try:
            import ctypes
            # Quick check if nuclear-music-player process exists
            import subprocess
            out = subprocess.check_output(
                'tasklist /fi "imagename eq nuclear-music-player.exe" /fo csv /nh',
                shell=True, text=True, stderr=subprocess.DEVNULL
            )
            return "nuclear-music-player.exe" in out.lower()
        except Exception:
            return False

    def get_current_track_from_file(self):
        queue_file = self.profile_dir / "queue.json"
        if not queue_file.exists():
            return None
        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            idx = data.get("queue.currentIndex", -1)
            items = data.get("queue.items", [])
            if 0 <= idx < len(items):
                item = items[idx]
                raw_track = item.get("track", {})
                return self._normalize_track(raw_track)
        except Exception as e:
            print(f"[NuclearBridge] Error reading queue.json: {e}")
        return None

    def _normalize_track(self, raw_track):
        if not raw_track:
            return None
        
        title = raw_track.get("title") or raw_track.get("name") or "Unknown Title"
        raw_artists = raw_track.get("artists", [])
        if isinstance(raw_artists, list) and raw_artists:
            artist_names = [a.get("name") if isinstance(a, dict) else str(a) for a in raw_artists]
            artist = ", ".join(filter(None, artist_names))
        else:
            artist = raw_track.get("artist") or "Unknown Artist"

        # Check artwork
        artwork_url = ""
        artwork_obj = raw_track.get("artwork", {})
        if isinstance(artwork_obj, dict):
            items = artwork_obj.get("items", [])
            if isinstance(items, list) and items:
                artwork_url = items[-1].get("url", "")
            elif "thumbnail" in artwork_obj:
                artwork_url = artwork_obj["thumbnail"]

        is_fav = self.is_track_favorite(raw_track)

        return {
            "title": title,
            "artist": artist,
            "artwork": artwork_url,
            "durationMs": raw_track.get("durationMs", 0),
            "source": raw_track.get("source", {}),
            "streamCandidates": raw_track.get("streamCandidates", []),
            "raw": raw_track,
            "isFavorite": is_fav
        }

    def is_track_favorite(self, track_or_raw):
        fav_file = self.profile_dir / "favorites.json"
        if not fav_file.exists():
            return False
        try:
            with open(fav_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            tracks = data.get("favorites.tracks", [])
            
            raw = track_or_raw.get("raw", track_or_raw)
            source = raw.get("source", {})
            source_id = source.get("id")
            source_provider = source.get("provider")
            
            title = (raw.get("title") or raw.get("name") or "").strip().lower()

            for item in tracks:
                ref = item.get("ref", {})
                ref_source = ref.get("source", {})
                if source_id and ref_source.get("id") == source_id:
                    return True
                
                ref_title = (ref.get("title") or ref.get("name") or "").strip().lower()
                if title and ref_title == title:
                    return True
        except Exception as e:
            print(f"[NuclearBridge] Error reading favorites.json: {e}")
        return False

    def add_favorite_direct(self, track_info):
        """Direct file-system fallback to add favorite to favorites.json"""
        fav_file = self.profile_dir / "favorites.json"
        if not fav_file.exists():
            return False, "favorites_file_not_found"

        try:
            with open(fav_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "favorites.tracks" not in data:
                data["favorites.tracks"] = []

            raw = track_info.get("raw", {})
            if self.is_track_favorite(raw):
                return False, "already_favorite"

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            new_item = {
                "addedAtIso": now_iso,
                "ref": {
                    "artists": raw.get("artists", []),
                    "artwork": raw.get("artwork", {}),
                    "durationMs": raw.get("durationMs", 0),
                    "source": raw.get("source", {}),
                    "streamCandidates": raw.get("streamCandidates", []),
                    "title": track_info.get("title", "Unknown Title")
                }
            }
            data["favorites.tracks"].append(new_item)

            temp_file = fav_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, fav_file)

            print(f"[NuclearBridge] Directly favorited '{track_info.get('title')}' in favorites.json")
            return True, "liked"
        except Exception as e:
            print(f"[NuclearBridge] Direct favorite failed: {e}")
            return False, str(e)

    async def _ws_handler(self, websocket):
        self.connected_clients.add(websocket)
        print(f"[NuclearBridge] Plugin client connected from {websocket.remote_address}")
        if self.on_connection_status_callback:
            self.on_connection_status_callback(True)

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    event_type = data.get("event")
                    status = data.get("status")

                    if event_type == "current_track":
                        raw_track = data.get("track", {})
                        norm = self._normalize_track(raw_track)
                        self._last_known_track = norm
                        if self.on_track_changed_callback:
                            self.on_track_changed_callback(norm)

                    elif status in ("liked", "already_favorite", "error"):
                        if self.on_like_result_callback:
                            self.on_like_result_callback(data)

                except json.JSONDecodeError:
                    pass
        except Exception as e:
            print(f"[NuclearBridge] Client error: {e}")
        finally:
            self.connected_clients.discard(websocket)
            print("[NuclearBridge] Plugin client disconnected")
            if not self.connected_clients and self.on_connection_status_callback:
                self.on_connection_status_callback(False)

    def start_websocket_server(self):
        if self.server_thread and self.server_thread.is_alive():
            return

        def _run_server():
            import websockets
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            async def main():
                async with websockets.serve(self._ws_handler, "127.0.0.1", self.port):
                    print(f"[NuclearBridge] WebSocket server listening on ws://127.0.0.1:{self.port}")
                    while not self._stop_event.is_set():
                        await asyncio.sleep(0.5)

            try:
                self.loop.run_until_complete(main())
            except Exception as e:
                print(f"[NuclearBridge] Server loop finished: {e}")

        self._stop_event.clear()
        self.server_thread = threading.Thread(target=_run_server, daemon=True)
        self.server_thread.start()

    def stop_websocket_server(self):
        self._stop_event.set()

    def trigger_like(self):
        """
        Triggers a Like action in Nuclear.
        First tries connected plugin via WebSocket for instant live UI update.
        Falls back to direct file manipulation if plugin is not connected.
        """
        track_info = self.get_current_track_from_file()
        if not track_info:
            return False, "no_track_playing", None

        # If plugin client is connected via WebSocket, send command for native UI toast & state
        if self.connected_clients and self.loop:
            msg = json.dumps({"action": "like"})
            for ws in list(self.connected_clients):
                asyncio.run_coroutine_threadsafe(ws.send(msg), self.loop)
            return True, "command_sent_to_plugin", track_info

        # Failsafe: Direct file update
        success, status = self.add_favorite_direct(track_info)
        track_info["isFavorite"] = True if status in ("liked", "already_favorite") else False
        return success, status, track_info

    def trigger_previous(self):
        """
        Triggers a Previous Track / Replay action in Nuclear.
        First tries connected plugin via WebSocket.
        Falls back to Windows synthetic VK_MEDIA_PREV_TRACK.
        """
        if self.connected_clients and self.loop:
            msg = json.dumps({"action": "previous"})
            for ws in list(self.connected_clients):
                asyncio.run_coroutine_threadsafe(ws.send(msg), self.loop)
            return True

        try:
            SYNTHETIC_EXTRA_INFO = 0xDEADC0DE
            if _user32:
                _user32.keybd_event(0xB1, 0, 0, SYNTHETIC_EXTRA_INFO)
                _user32.keybd_event(0xB1, 0, 2, SYNTHETIC_EXTRA_INFO)
                return True
            return False
        except Exception as e:
            print(f"[NuclearBridge] Error synthesizing previous key: {e}")
            return False

    def install_companion_plugin(self):
        """Installs the companion plugin into Nuclear's profile directory"""
        try:
            if not self.profile_dir.exists():
                self.profile_dir.mkdir(parents=True, exist_ok=True)

            plugins_dir = self.profile_dir / "plugins" / "nuclear-headphone-bridge" / "1.0.0"
            plugins_dir.mkdir(parents=True, exist_ok=True)

            base_dir = Path(__file__).resolve().parent.parent
            source_plugin_dir = base_dir / "nuclear-plugin"

            # Copy package.json and index.js
            shutil.copy2(source_plugin_dir / "package.json", plugins_dir / "package.json")
            shutil.copy2(source_plugin_dir / "index.js", plugins_dir / "index.js")

            # Update plugins.json
            plugins_json_path = self.profile_dir / "plugins.json"
            plugins_data = {}
            if plugins_json_path.exists():
                try:
                    with open(plugins_json_path, "r", encoding="utf-8") as f:
                        plugins_data = json.load(f)
                except Exception:
                    plugins_data = {}

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            plugins_data["plugins.nuclear-headphone-bridge"] = {
                "enabled": True,
                "id": "nuclear-headphone-bridge",
                "installationMethod": "local",
                "installedAt": now_iso,
                "lastUpdatedAt": now_iso,
                "path": str(plugins_dir),
                "version": "1.0.0",
                "warnings": []
            }

            with open(plugins_json_path, "w", encoding="utf-8") as f:
                json.dump(plugins_data, f, indent=2)

            print(f"[NuclearBridge] Companion plugin installed successfully at {plugins_dir}")
            return True, str(plugins_dir)
        except Exception as e:
            print(f"[NuclearBridge] Failed to install companion plugin: {e}")
            return False, str(e)

    def is_companion_plugin_installed(self):
        plugins_json_path = self.profile_dir / "plugins.json"
        if not plugins_json_path.exists():
            return False
        try:
            with open(plugins_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return "plugins.nuclear-headphone-bridge" in data and data["plugins.nuclear-headphone-bridge"].get("enabled", False)
        except Exception:
            return False
