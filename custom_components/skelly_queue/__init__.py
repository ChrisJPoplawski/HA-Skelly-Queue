from __future__ import annotations
import asyncio, logging, re, os, random
from os import path, makedirs, stat, remove
from typing import Deque, List
from collections import deque

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.components.frontend import async_register_built_in_panel, async_remove_panel

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import async_ble_device_from_address

from .const import *
from .skelly_ble import SkellyBle
from .panel import SkellyPanelView, SkellyApiView

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
PLAYABLE_EXT = (".mp3", ".wav", ".ogg", ".m4a", ".flac")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    data = entry.data
    address = data[CONF_ADDRESS]
    play_char = data.get(CONF_PLAY_CHAR, "")
    cmd_char = data.get(CONF_CMD_CHAR, "")
    media_dir = data.get(CONF_MEDIA_DIR, "/media/skelly")
    allow_remote = data.get(CONF_ALLOW_REMOTE, True)
    cache_dir = data.get(CONF_CACHE_DIR, "/media/skelly/cache")
    max_cache_mb = max(50, int(data.get(CONF_MAX_CACHE_MB, 500)))
    keepalive_enabled = bool(data.get(CONF_KEEPALIVE_ENABLED, True))
    keepalive_sec = max(1, int(data.get(CONF_KEEPALIVE_SEC, 5)))
    pair_on_connect = bool(data.get(CONF_PAIR_ON_CONNECT, True))
    pin_code_hint = (data.get(CONF_PIN_CODE) or "1234").strip()

    for d in (media_dir, cache_dir):
        try: makedirs(d, exist_ok=True)
        except Exception as ex: _LOGGER.warning("Could not create dir %s: %s", d, ex)

    # Auto-detect UUIDs if missing
    if not play_char:
        try:
            dev = async_ble_device_from_address(hass, address, connectable=True)
            if dev:
                client: BleakClient = await establish_connection(BleakClient, dev, name="skelly-detect", max_attempts=3)
                await client.get_services()
                cands = []
                for svc in client.services:
                    for ch in svc.characteristics:
                        props = {p.lower() for p in ch.properties}
                        if "write" in props or "write without response" in props:
                            cu = str(ch.uuid)
                            score = (len(cu) > 8, "without" in " ".join(props))
                            cands.append((score, cu))
                cands.sort(reverse=True)
                if cands: play_char = cands[0][1]
                if len(cands) > 1 and not cmd_char: cmd_char = cands[1][1]
                try: await client.disconnect()
                except Exception: pass
                new = dict(entry.data); new[CONF_PLAY_CHAR] = play_char or ""; new[CONF_CMD_CHAR] = cmd_char or ""
                hass.config_entries.async_update_entry(entry, data=new)
                _LOGGER.info("Startup auto-detect set play_char=%s cmd_char=%s", play_char, cmd_char)
            else:
                _LOGGER.warning("Startup auto-detect: Skelly not discovered yet")
        except Exception as ex:
            _LOGGER.warning("Startup auto-detect failed: %s", ex)

    ble = SkellyBle(hass, address, play_char, cmd_char or None, pair_on_connect=pair_on_connect)
    queue: Deque[str] = deque()
    is_playing = False
    now_playing: str | None = None
    play_lock = asyncio.Lock()
    session = async_get_clientsession(hass)

    # Presets storage
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.storage")
    presets = await store.async_load() or {}
    if not isinstance(presets, dict): presets = {}

    def _sanitize_name(name: str) -> str:
        base = name.split("?")[0].split("/")[-1] or "track"
        return SAFE_NAME_RE.sub("_", base)[:120]

    def _media_path(local_name: str) -> str:
        return path.join(media_dir, local_name)

    async def _send_play_command(filename: str) -> bool:
        payload = f"PLAY:{filename}".encode("utf-8")
        return await ble.write_play(payload)

    async def _send_cmd(cmd: str) -> bool:
        if not cmd_char: return False
        return await ble.write_cmd(cmd.encode("utf-8"))

    async def _evict_cache_if_needed():
        try:
            entries = []; total = 0
            for fname in os.listdir(cache_dir):
                fpath = path.join(cache_dir, fname)
                try:
                    st = stat(fpath); total += st.st_size; entries.append((st.st_mtime, st.st_size, fpath))
                except Exception:
                    continue
            limit = max_cache_mb * 1024 * 1024
            if total <= limit: return
            entries.sort()
            for _, size, fpath in entries:
                try: remove(fpath); total -= size
                except Exception: pass
                if total <= limit: break
        except Exception as ex:
            _LOGGER.debug("Cache eviction failed: %s", ex)

    async def _download_to_cache(url: str) -> str:
        if not allow_remote:
            raise ValueError("Remote URLs are disabled.")
        safe = _sanitize_name(url)
        local_rel = path.join("cache", safe)
        dest = _media_path(local_rel)
        async with session.get(url, timeout=60) as resp:
            resp.raise_for_status()
            makedirs(path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(8192):
                    f.write(chunk)
        await _evict_cache_if_needed()
        return local_rel

    async def _play_loop():
        nonlocal is_playing, now_playing
        async with play_lock:
            if is_playing: return
            is_playing = True
        try:
            while queue:
                filename = queue[0]
                full = _media_path(filename)
                if not path.isfile(full):
                    queue.popleft(); continue
                now_playing = filename
                hass.states.async_set(f"{DOMAIN}.now_playing", filename)
                ok = await _send_play_command(filename)
                if not ok: break
                await asyncio.sleep(10)
                queue.popleft()
                hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))
            now_playing = None
            hass.states.async_set(f"{DOMAIN}.now_playing", "")
        finally:
            async with play_lock:
                is_playing = False

    # ---- Keep-alive (optional) ----
    keepalive_task: asyncio.Task | None = None
    async def _keepalive_loop():
        if not cmd_char:
            _LOGGER.debug("Keep-alive skipped: no cmd_char configured.")
            return
        while True:
            try:
                await asyncio.sleep(keepalive_sec)
                await ble.write_cmd(b"PING")
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    if keepalive_enabled:
        keepalive_task = hass.loop.create_task(_keepalive_loop())

    # ------- Services -------
    async def svc_enqueue(call):
        fn = call.data.get("filename")
        if not fn: return
        queue.append(fn)
        hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))
        if not is_playing: hass.async_create_task(_play_loop())

    async def svc_enqueue_bulk(call):
        items = call.data.get("items") or []
        for it in items:
            if isinstance(it, str): queue.append(it)
        hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))
        if items and not is_playing: hass.async_create_task(_play_loop())

    async def svc_enqueue_url(call):
        url = call.data.get("url")
        if not url: return
        if url.lower().endswith((".m3u",".m3u8")):
            await svc_enqueue_m3u(call); return
        rel = await _download_to_cache(url)
        queue.append(rel)
        hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))
        if not is_playing: hass.async_create_task(_play_loop())

    async def svc_enqueue_m3u(call):
        url = call.data.get("url")
        if not url: return
        async with session.get(url, timeout=60) as resp:
            resp.raise_for_status()
            text = await resp.text()
        items = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        count = 0
        for item in items:
            if not URL_RE.match(item): continue
            try:
                rel = await _download_to_cache(item); queue.append(rel); count += 1
            except Exception: continue
        hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))
        if count and not is_playing: hass.async_create_task(_play_loop())

    async def svc_enqueue_dir(call):
        sub = (call.data.get("subpath") or "").strip().strip("/")
        recursive = bool(call.data.get("recursive", True))
        shuffle = bool(call.data.get("shuffle", False))
        base = path.abspath(media_dir)
        target = path.abspath(path.join(media_dir, sub))
        if not target.startswith(base): target = base
        files: List[str] = []
        if recursive:
            for root, dirs, fns in os.walk(target):
                for name in sorted(fns):
                    if name.lower().endswith(PLAYABLE_EXT):
                        rel = path.relpath(path.join(root, name), media_dir)
                        files.append(rel)
        else:
            for name in sorted(os.listdir(target)):
                if name.lower().endswith(PLAYABLE_EXT):
                    rel = path.join(sub, name) if sub else name
                    files.append(rel)
        if shuffle: random.shuffle(files)
        for f in files: queue.append(f)
        hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))
        if files and not is_playing: hass.async_create_task(_play_loop())

    async def svc_play(_): 
        if queue and not is_playing: hass.async_create_task(_play_loop())

    async def svc_skip(_):
        await _send_cmd("NEXT")
        if queue:
            queue.popleft()
            hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))

    async def svc_clear(_):
        queue.clear(); hass.states.async_set(f"{DOMAIN}.queue_length", 0)

    async def svc_stop(_):
        await _send_cmd("STOP")
        queue.clear(); hass.states.async_set(f"{DOMAIN}.queue_length", 0)

    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE, svc_enqueue)
    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE_BULK, svc_enqueue_bulk)
    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE_URL, svc_enqueue_url)
    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE_M3U, svc_enqueue_m3u)
    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE_DIR, svc_enqueue_dir)
    hass.services.async_register(DOMAIN, SERVICE_PLAY, svc_play)
    hass.services.async_register(DOMAIN, SERVICE_SKIP, svc_skip)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, svc_clear)
    hass.services.async_register(DOMAIN, SERVICE_STOP, svc_stop)

    hass.states.async_set(f"{DOMAIN}.queue_length", 0)
    hass.states.async_set(f"{DOMAIN}.now_playing", "")

    # ------- Panel (fixed path) -------
    panel_data = {
        "config": {"media_dir": media_dir, "cache_dir": cache_dir},
        "queue": queue,
        "controls": {},
        "presets": presets,
        "store": store,
    }
    hass.http.register_view(SkellyPanelView(hass, panel_data))
    hass.http.register_view(SkellyApiView(hass, panel_data))

    panel_url_path = "skelly-queue"
    async_remove_panel(hass, panel_url_path)
    async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title="Skelly Queue",
        sidebar_icon="mdi:playlist-music",
        frontend_url_path=panel_url_path,
        config={"url": "/api/skelly_queue/panel"},
        require_admin=False,
        update=True,
    )

    _LOGGER.info(
        "Skelly Queue v0.4.4 ready (keep-alive %s @ %ss, pair_on_connect=%s; PIN hint=%s). Media: %s",
        "on" if keepalive_enabled else "off", keepalive_sec,
        "on" if pair_on_connect else "off", pin_code_hint, media_dir
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _shutdown(_evt):
        if keepalive_task:
            keepalive_task.cancel()
        await ble.disconnect()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok

