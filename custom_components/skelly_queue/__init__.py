from __future__ import annotations
import asyncio, logging, re
from os import path, makedirs, stat, remove
from typing import Deque, List
from collections import deque

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from .const import *
from .skelly_ble import SkellyBle

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up from UI entry."""
    data = entry.data
    address = data[CONF_ADDRESS]
    play_char = data[CONF_PLAY_CHAR]
    cmd_char = data.get(CONF_CMD_CHAR)
    media_dir = data.get(CONF_MEDIA_DIR, "/media/skelly")
    allow_remote = data.get(CONF_ALLOW_REMOTE, True)
    cache_dir = data.get(CONF_CACHE_DIR, "/media/skelly/cache")
    max_cache_mb = max(50, int(data.get(CONF_MAX_CACHE_MB, 500)))

    for d in (media_dir, cache_dir):
        try:
            makedirs(d, exist_ok=True)
        except Exception as ex:
            _LOGGER.warning("Could not create dir %s: %s", d, ex)

    ble = SkellyBle(hass, address, play_char, cmd_char)
    queue: Deque[str] = deque()
    is_playing = False
    now_playing: str | None = None
    play_lock = asyncio.Lock()
    session = async_get_clientsession(hass)

    def _sanitize_name(name: str) -> str:
        base = name.split("?")[0].split("/")[-1] or "track"
        return SAFE_NAME_RE.sub("_", base)[:120]

    def _media_path(local_name: str) -> str:
        return path.join(media_dir, local_name)

    async def _send_play_command(filename: str) -> bool:
        payload = f"PLAY:{filename}".encode("utf-8")
        return await ble.write_play(payload)

    async def _send_cmd(cmd: str) -> bool:
        if cmd_char is None: return False
        return await ble.write_cmd(cmd.encode("utf-8"))

    async def _evict_cache_if_needed():
        try:
            import os
            entries = []
            total = 0
            for fname in os.listdir(cache_dir):
                fpath = path.join(cache_dir, fname)
                try:
                    st = stat(fpath)
                    total += st.st_size
                    entries.append((st.st_mtime, st.st_size, fpath))
                except Exception:
                    continue
            limit = max_cache_mb * 1024 * 1024
            if total <= limit: return
            entries.sort()
            for _, size, fpath in entries:
                try:
                    remove(fpath)
                    total -= size
                except Exception:
                    pass
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
                    queue.popleft()
                    continue
                now_playing = filename
                hass.states.async_set(f"{DOMAIN}.now_playing", filename)  # simple state mirror
                ok = await _send_play_command(filename)
                if not ok:
                    break
                await asyncio.sleep(10)  # TODO: replace with notify end
                queue.popleft()
                hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))
            now_playing = None
            hass.states.async_set(f"{DOMAIN}.now_playing", "")
        finally:
            async with play_lock:
                is_playing = False

    # expose queue stats as helpers for sensors/buttons platform files
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "ble": ble,
        "queue": queue,
        "flags": {
            "is_playing": lambda: is_playing,
            "now_playing": lambda: now_playing
        },
        "controls": {
            "play_loop": _play_loop,
            "send_cmd": _send_cmd,
            "enqueue_local": lambda fn: queue.append(fn),
            "enqueue_url": _download_to_cache,
            "media_path": _media_path,
        },
        "config": {
            "media_dir": media_dir,
            "allow_remote": allow_remote,
            "cache_dir": cache_dir,
        }
    }

    # register services (same names)
    async def svc_enqueue(call):
        fn = call.data.get("filename")
        if not fn: return
        queue.append(fn)
        hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))
        if not is_playing: hass.async_create_task(_play_loop())

    async def svc_enqueue_url(call):
        url = call.data.get("url")
        if not url: return
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
        items = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
        count = 0
        for item in items:
            try:
                if URL_RE.match(item):
                    rel = await _download_to_cache(item)
                else:
                    continue
                queue.append(rel); count += 1
            except Exception:
                continue
        hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))
        if count and not is_playing: hass.async_create_task(_play_loop())

    async def svc_play(_): 
        if queue and not is_playing: hass.async_create_task(_play_loop())

    async def svc_skip(_):
        await _send_cmd("NEXT")
        if queue:
            queue.popleft()
            hass.states.async_set(f"{DOMAIN}.queue_length", len(queue))

    async def svc_clear(_):
        queue.clear()
        hass.states.async_set(f"{DOMAIN}.queue_length", 0)

    async def svc_stop(_):
        await _send_cmd("STOP")
        queue.clear()
        hass.states.async_set(f"{DOMAIN}.queue_length", 0)

    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE, svc_enqueue)
    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE_URL, svc_enqueue_url)
    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE_M3U, svc_enqueue_m3u)
    hass.services.async_register(DOMAIN, SERVICE_PLAY, svc_play)
    hass.services.async_register(DOMAIN, SERVICE_SKIP, svc_skip)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, svc_clear)
    hass.services.async_register(DOMAIN, SERVICE_STOP, svc_stop)

    # set initial helper states
    hass.states.async_set(f"{DOMAIN}.queue_length", 0)
    hass.states.async_set(f"{DOMAIN}.now_playing", "")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _shutdown(_evt):
        await ble.disconnect()
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown)

    _LOGGER.info("Skelly Queue (UI) ready for %s", address)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok

