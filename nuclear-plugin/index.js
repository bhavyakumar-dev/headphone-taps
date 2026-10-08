// Nuclear Headphone Bridge Companion Plugin
// Bridges Nuclear Player with the NuclearHeart background startup app

let storedApi = null;
let ws = null;
let reconnectTimer = null;
let isConnecting = false;

const WS_PORT = 39281;
const WS_URL = `ws://127.0.0.1:${WS_PORT}`;

function showInAppToast(title, artist) {
  try {
    const existing = document.getElementById("nh-headphone-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.id = "nh-headphone-toast";
    toast.style.position = "fixed";
    toast.style.bottom = "84px";
    toast.style.right = "24px";
    toast.style.backgroundColor = "rgba(18, 18, 24, 0.96)";
    toast.style.color = "#ffffff";
    toast.style.border = "1px solid #9333ea";
    toast.style.borderRadius = "12px";
    toast.style.padding = "12px 18px";
    toast.style.fontFamily = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    toast.style.fontSize = "13px";
    toast.style.fontWeight = "600";
    toast.style.zIndex = "999999";
    toast.style.boxShadow = "0 10px 25px -5px rgba(147, 51, 234, 0.45)";
    toast.style.display = "flex";
    toast.style.alignItems = "center";
    toast.style.gap = "12px";
    toast.style.pointerEvents = "none";
    toast.style.transition = "all 0.25s cubic-bezier(0.16, 1, 0.3, 1)";
    toast.style.transform = "translateY(10px) scale(0.95)";
    toast.style.opacity = "0";

    toast.innerHTML = `
      <div style="width: 32px; height: 32px; border-radius: 8px; background: rgba(147, 51, 234, 0.2); display: flex; align-items: center; justify-content: center; font-size: 18px; color: #c084fc;">
        ❤️
      </div>
      <div>
        <div style="color: #f3e8ff; font-weight: 700;">Added to Favorites via Headphone!</div>
        <div style="font-size: 11px; color: #a1a1aa; font-weight: 400; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          ${title || "Unknown Title"} • ${artist || "Unknown Artist"}
        </div>
      </div>
    `;

    document.body.appendChild(toast);

    requestAnimationFrame(() => {
      toast.style.opacity = "1";
      toast.style.transform = "translateY(0) scale(1)";
    });

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(8px) scale(0.95)";
      setTimeout(() => toast.remove(), 260);
    }, 2800);
  } catch (err) {
    console.error("[HeadphoneBridge] Toast error:", err);
  }
}

function connectWebSocket(api) {
  if (isConnecting || (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING))) {
    return;
  }

  isConnecting = true;
  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      isConnecting = false;
      console.log("[HeadphoneBridge] Connected to NuclearHeart app at", WS_URL);
      sendCurrentTrack(api);
    };

    ws.onmessage = async (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.action === "like" || msg.action === "toggle_favorite") {
          await handleLikeAction(api);
        } else if (msg.action === "previous") {
          await handlePreviousAction(api);
        } else if (msg.action === "get_status") {
          await sendCurrentTrack(api);
        }
      } catch (err) {
        console.error("[HeadphoneBridge] Failed to process incoming message:", err);
      }
    };

    ws.onclose = () => {
      isConnecting = false;
      ws = null;
      scheduleReconnect(api);
    };

    ws.onerror = () => {
      isConnecting = false;
      if (ws) ws.close();
    };
  } catch (e) {
    isConnecting = false;
    scheduleReconnect(api);
  }
}

function scheduleReconnect(api) {
  if (!reconnectTimer && storedApi) {
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      if (storedApi) connectWebSocket(storedApi);
    }, 3000);
  }
}

async function handleLikeAction(api) {
  try {
    const queueItem = await api.Queue.getCurrentItem();
    if (!queueItem || !queueItem.track) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ status: "error", message: "No track currently in queue" }));
      }
      return;
    }

    const track = queueItem.track;
    const title = track.title || track.name || "Unknown Track";
    const artist = Array.isArray(track.artists)
      ? track.artists.map((a) => (typeof a === "string" ? a : a?.name)).filter(Boolean).join(", ")
      : track.artist || "Unknown Artist";

    let isFav = false;
    try {
      isFav = await api.Favorites.isTrackFavorite(track.source);
    } catch (_) {
      isFav = false;
    }

    if (!isFav) {
      await api.Favorites.addTrack(track);
      showInAppToast(title, artist);

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          status: "liked",
          title: title,
          artist: artist,
          isFavorite: true,
          track: track
        }));
      }
    } else {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          status: "already_favorite",
          title: title,
          artist: artist,
          isFavorite: true,
          track: track
        }));
      }
    }
  } catch (err) {
    console.error("[HeadphoneBridge] Like error:", err);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ status: "error", message: err.toString() }));
    }
  }
}

async function handlePreviousAction(api) {
  try {
    if (api.Playback && typeof api.Playback.previous === "function") {
      await api.Playback.previous();
    } else if (api.Playback && typeof api.Playback.seekTo === "function") {
      await api.Playback.seekTo(0);
    }
  } catch (err) {
    console.error("[HeadphoneBridge] Previous action error:", err);
  }
}

async function sendCurrentTrack(api) {
  try {
    const queueItem = await api.Queue.getCurrentItem();
    if (queueItem && queueItem.track && ws && ws.readyState === WebSocket.OPEN) {
      const track = queueItem.track;
      const title = track.title || track.name || "Unknown Track";
      const artist = Array.isArray(track.artists)
        ? track.artists.map((a) => (typeof a === "string" ? a : a?.name)).filter(Boolean).join(", ")
        : track.artist || "Unknown Artist";

      let isFav = false;
      try {
        isFav = await api.Favorites.isTrackFavorite(track.source);
      } catch (_) {}

      ws.send(JSON.stringify({
        event: "current_track",
        track: {
          title: title,
          artist: artist,
          isFavorite: isFav,
          durationMs: track.durationMs || 0,
          source: track.source,
          artwork: track.artwork
        }
      }));
    }
  } catch (err) {
    console.error("[HeadphoneBridge] sendCurrentTrack error:", err);
  }
}

module.exports = {
  async onLoad(api) {
    console.log("[HeadphoneBridge] Loaded");
  },

  async onEnable(api) {
    storedApi = api;
    console.log("[HeadphoneBridge] Enabled");
    connectWebSocket(api);

    try {
      if (api.Events && typeof api.Events.on === "function") {
        api.Events.on("playback.trackChange", () => sendCurrentTrack(api));
        api.Events.on("queue.change", () => sendCurrentTrack(api));
      }
    } catch (_) {}

    // Polling interval to keep track status updated
    setInterval(() => {
      if (storedApi && ws && ws.readyState === WebSocket.OPEN) {
        sendCurrentTrack(storedApi);
      }
    }, 4000);
  },

  async onDisable() {
    storedApi = null;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
    console.log("[HeadphoneBridge] Disabled");
  }
};
