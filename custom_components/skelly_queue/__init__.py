from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse, unquote

import aiohttp
import smbclient
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

# Local modules
from .panel import SkellyPanelView, SkellyApiView
from .skelly_ble import SkellyBLE

DOMAIN = "skelly_queue"

# ---------- defaults ----------
DEFAULT_MEDIA_DIR = "/media/skelly"
DEFAULT_CACHE_DIR = "/media/skelly/.cache"
DEFAULT_LOG_PATH = "/config/home-assistant.log"

# ---------- datamodel ----------
@dataclass
class SkellyData:
    hass: HomeAssistant
    address: Optional[str] = None
    play_uuid: Optional[str] = None
    cmd_uuid: Optional[str] = None
    media_dir: str = DEFAULT_MEDIA_DIR
    cache_dir: str = DEFAULT_CACHE_DIR
    log_path: str = DEFAULT_LOG_PATH
    ble: Optional[SkellyBLE] = None
    queue: List[str] = field(default_factory=list)
    now_playing: Optional[str] = None
    presets: dict = field(default_factory=dict)

    def as_panel_dict(self) -> dict:
        return {
            "address": self.address,
            "config": {"media_dir": self.media_dir, "cache_dir": self.cache_dir},
            "ble": self.ble,
            "presets": self.presets,
            "log_path": self.log_path,
        }

# -----------------------------------------------------------------------------
# Download helpers (HTTP/HTTPS + SMB2/3 via smbclient)
# -----------------------------------------------------------------------------
async def download_to_cache(hass: HomeAssistant, url: str, cache_dir: str) -> str:
    """
    Download http/https/smb URL into cache_dir and return the local file path.

    - http/https: streamed via aiohttp
    - smb://user:pass@host/share/path/file: streamed via smbclient (SMB2/3)
    """
    os.makedirs(cache_dir, exist_ok=True)
    u = urlparse(url)

    if u.scheme in ("http", "https"):
        filename = os.path.basename(u.path) or "track"
        local = os.path.join(cache_dir, filename)
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url) as resp:
                resp.raise_for_status()
                # write in chunks
                def _write_stream():
                    with open(local, "wb") as f:
                        pass  # truncate
                await hass.async_add_executor_job(_write_stream)

                with open(local, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)
        return local

    if u.scheme == "smb":
        host = u.hostname
        parts = [p for p in u.path.split("/") if p]
        if not host or len(parts) < 2:
            raise ValueError("smb url must be smb://user:pass@host/share/path/file")

        share = parts[0]
        sub = "/".join(parts[1:-1])
        filename = parts[-1]
        username = unquote(u.username or "")
        password = unquote(u.password or "")
        port = 445

        # register session and copy file
        smbclient.reset_connection_cache()
        smbclient.register_session(
            server=host,
            username=username or None,
            password=password or None,
            port=port,
        )
        remote = rf"\\{host}\{share}" + (rf"\{sub}" if sub else "") + rf"\{filename}"
        local = os.path.join(cache_dir, filename)

        def _copy():
            with smbclient.open_file(remote, mode="rb") as rf, open(local, "wb") as lf:
                while True:
                    data = rf.read(131072)
                    if not data:
                        break
                    lf.write(data)

        await hass.async_add_executor_job(_copy)
        return local

    raise ValueError(f"Unsupported scheme for enqueue_url: {u.scheme}")


# -----------------------------------------------------------------------------
# Core HA entry points
# -----------------------------------------------------------------------------
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Pull config/options (if present)
    address = (entry.data.get("address") or entry.options.get("address")) if entry else None
    play_uuid = (entry.data.get("play_uuid") or entry.options.get("play_uuid")) if entry else None
    cmd_uuid = (entry.data.get("cmd_uuid") or entry.options.get("cmd_uuid")) if entry else None
    media_dir = (entry.data.get("media_dir") or entry.options.get("media_dir") or DEFAULT_MEDIA_DIR)
    cache_dir = (entry.data.get("cache_dir") or entry.options.get("cache_dir") or DEFAULT_CACHE_DIR)
    log_path = (entry.data.get("log_path") or entry.options.get("log_path") or DEFAULT_LOG_PATH)

    data = SkellyData(
        hass=hass,
        address=address,
        play_uuid=play_uuid,
        cmd_uuid=cmd_uuid,
        media_dir=media_dir,
        cache_dir=cache_dir,
        log_path=log_path,
    )

    # BLE (optional)
    ble: Optional[SkellyBLE] = None
    if address:
        ble = SkellyBLE(hass, address, play_uuid=play_uuid, cmd_uuid=cmd_uuid)
        data.ble = ble

    # Register panel + API
    hass.http.register_view(SkellyPanelView(hass, data.as_panel_dict()))
    hass.http.register_view(SkellyApiView(hass, data.as_panel_dict()))
    async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title="Skelly Queue",
        sidebar_icon="mdi:playlist-music",
        config={"url": "/api/skelly_queue/panel"},
        update=True,
        require_admin=False,
    )

    # basic states used by panel
    _set_state(hass, "skelly_queue.queue_length", 0)
    _set_state(hass, "skelly_queue.now_playing", "")

    # Service handlers
    async def _svc_enqueue(call: ServiceCall):
        rel = (call.data.get("filename") or "").strip().strip("/")
        if not rel:
            raise ValueError("filename is required")
        src = os.path.join(data.media_dir, rel)
        if not os.path.isfile(src):
            raise FileNotFoundError(f"Not found: {src}")
        data.queue.append(src)
        _update_len(hass, data)

    async def _scan_local(subpath: str, recursive: bool) -> List[str]:
        base = os.path.abspath(data.media_dir)
        start = os.path.abspath(os.path.join(base, subpath.strip().strip("/")))
        if not start.startswith(base):
            start = base
        found: List[str] = []

        def _walk():
            if not os.path.isdir(start):
                return
            if recursive:
                for root, _dirs, files in os.walk(start):
                    for f in files:
                        found.append(os.path.join(root, f))
            else:
                for f in os.listdir(start):
                    full = os.path.join(start, f)
                    if os.path.isfile(full):
                        found.append(full)

        await hass.async_add_executor_job(_walk)
        return found

    async def _svc_enqueue_dir(call: ServiceCall):
        sub = (call.data.get("subpath") or "").strip()
        recursive = bool(call.data.get("recursive", True))
        shuffle = bool(call.data.get("shuffle", False))
        files = await _scan_local(sub, recursive)
        if shuffle:
            import random
            random.shuffle(files)
        data.queue.extend(files)
        _update_len(hass, data)

    async def _svc_enqueue_url(call: ServiceCall):
        url = (call.data.get("url") or "").strip()
        if not url:
            raise ValueError("url is required")
        # handle m3u/m3u8 by URL (http/https), otherwise download SMB/http
        if url.lower().endswith(".m3u") or url.lower().endswith(".m3u8"):
            # naive playlist fetch (http/https)
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
            lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
            for item in lines:
                data.queue.append(item)  # store raw; your player/worker should resolve later
        else:
            # Download remote to cache, then queue local file
            local = await download_to_cache(hass, url, data.cache_dir)
            data.queue.append(local)
        _update_len(hass, data)

    async def _svc_play(call: ServiceCall):
        if not data.queue:
            _set_state(hass, "skelly_queue.now_playing", "")
            return
        track = data.queue.pop(0)
        _update_len(hass, data)
        data.now_playing = os.path.basename(track)
        _set_state(hass, "skelly_queue.now_playing", data.now_playing)

        # send to Skelly via BLE (best-effort)
        if data.ble:
            try:
                await data.ble.play_file(track)
            except Exception:
                # Leave a breadcrumb in the HA log; the panel's log viewer will show it.
                pass

    async def _svc_skip(call: ServiceCall):
        await _svc_play(call)

    async def _svc_stop(call: ServiceCall):
        data.now_playing = None
        _set_state(hass, "skelly_queue.now_playing", "")

    async def _svc_clear(call: ServiceCall):
        data.queue.clear()
        _update_len(hass, data)
        data.now_playing = None
        _set_state(hass, "skelly_queue.now_playing", "")

    hass.services.async_register(DOMAIN, "enqueue", _svc_enqueue)
    hass.services.async_register(DOMAIN, "enqueue_dir", _svc_enqueue_dir)
    hass.services.async_register(DOMAIN, "enqueue_url", _svc_enqueue_url)
    hass.services.async_register(DOMAIN, "play", _svc_play)
    hass.services.async_register(DOMAIN, "skip", _svc_skip)
    hass.services.async_register(DOMAIN, "stop", _svc_stop)
    hass.services.async_register(DOMAIN, "clear", _svc_clear)

    # graceful shutdown
    async def _on_stop(_event):
        if data.ble:
            try:
                await data.ble.disconnect()
            except Exception:
                pass

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_stop)

    # stash on hass for access from panel.py if ever needed
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["data"] = data
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Nothing persistent to unload beyond views/panel, which HA cleans up on reload.
    return True


# -----------------------------------------------------------------------------
# small helpers for states
# -----------------------------------------------------------------------------
def _update_len(hass: HomeAssistant, data: SkellyData) -> None:
    _set_state(hass, "skelly_queue.queue_length", len(data.queue))


def _set_state(hass: HomeAssistant, entity_id: str, value) -> None:
    # Lightweight state updates without a full entity platform for the simple UI
    attrs = {}
    hass.states.async_set(entity_id, value, attrs)

