import asyncio
import logging
import re
from os import path, makedirs, stat, remove
from typing import Deque, List
from collections import deque

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import *
from .skelly_ble import SkellyBle

_LOGGER = logging.getLogger(__name__)

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Required(CONF_PLAY_CHAR): cv.string,
        vol.Optional(CONF_CMD_CHAR): cv.string,
        vol.Optional(CONF_MEDIA_DIR, default="/media/skelly"): cv.string,
        vol.Optional(CONF_ALLOW_REMOTE, default=False): cv.boolean,
        vol.Optional(CONF_CACHE_DIR, default="/media/skelly/cache"): cv.string,
        vol.Optional(CONF_MAX_CACHE_MB, default=500): vol.Coerce(int),
    })
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: dict):
    conf = config.get(DOMAIN)
    if not conf:
        _LOGGER.error("No skelly_queue configuration found")
        return False

    address = conf[CONF_ADDRESS]
    play_char = conf[CONF_PLAY_CHAR]
    cmd_char = conf.get(CONF_CMD_CHAR)
    media_dir = conf[CONF_MEDIA_DIR]
    allow_remote = conf[CONF_ALLOW_REMOTE]
    cache_dir = conf[CONF_CACHE_DIR]
    max_cache_mb = max(50, int(conf[CONF_MAX_CACHE_MB]))  # floor @ 50MB

    # dirs
    for d in (media_dir, cache_dir):
        try:
            makedirs(d, exist_ok=True)
        except Exception as ex:
            _LOGGER.warning("Could not create dir %s: %s", d, ex)

    ble = SkellyBle(hass, address, play_char, cmd_char)
    queue: Deque[str] = deque()  # filenames relative to media_dir
    is_playing = False
    play_lock = asyncio.Lock()
    session = async_get_clientsession(hass)

    def _sanitize_name(name: str) -> str:
        base = name.split("?")[0].split("/")[-1] or "track"
        base = SAFE_NAME_RE.sub("_", base)
        return base[:120]

    def _media_path(local_name: str) -> str:
        return path.join(media_dir, local_name)

    async def _send_play_command(filename: str) -> bool:
        # Adjust payload to your device format as needed.
        payload = f"PLAY:{filename}".encode("utf-8")
        ok = await ble.write_play(payload)
        _LOGGER.debug("Sent play for %s -> %s", filename, ok)
        return ok

    async def _send_cmd(cmd: str) -> bool:
        if cmd_char is None:
            return False
        payload = cmd.encode("utf-8")   # e.g., "STOP" or "NEXT"
        ok = await ble.write_cmd(payload)
        _LOGGER.debug("Sent cmd %s -> %s", cmd, ok)
        return ok

    async def _evict_cache_if_needed():
        """Size-based eviction (oldest first) for cache_dir."""
        try:
            import os, time
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
            if total <= limit:
                return
            entries.sort()  # oldest first
            for mtime, size, fpath in entries:
                try:
                    remove(fpath)
                    total -= size
                except Exception:
                    pass
                if total <= limit:
                    break
        except Exception as ex:
            _LOGGER.debug("Cache eviction failed: %s", ex)

    async def _download_to_cache(url: str) -> str:
        """Download URL into cache_dir and return the local filename (relative to media_dir)."""
        if not allow_remote:
            raise ValueError("Remote URLs are disabled. Set allow_remote_urls: true")
        safe = _sanitize_name(url)
        local_rel = path.join("cache", safe)
        dest = _media_path(local_rel)
        try:
            async with session.get(url, timeout=60) as resp:
                resp.raise_for_status()
                makedirs(path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
            _LOGGER.info("Downloaded %s -> %s", url, dest)
            await _evict_cache_if_needed()
            return local_rel
        except Exception as ex:
            _LOGGER.error("Failed to download %s: %s", url, ex)
            raise

    async def _parse_m3u(text: str, base_url: str) -> List[str]:
        import urllib.parse as up
        urls: List[str] = []
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if URL_RE.match(s):
                urls.append(s)
            else:
                urls.append(up.urljoin(base_url, s))
        return urls

    async def _play_loop():
        nonlocal is_playing
        async with play_lock:
            if is_playing:
                return
            is_playing = True
        try:
            while queue:
                filename = queue[0]
                full = _media_path(filename)
                if not path.isfile(full):
                    _LOGGER.warning("Missing file: %s (skipping)", full)
                    queue.popleft()
                    continue

                ok = await _send_play_command(filename)
                if not ok:
                    _LOGGER.error("BLE play failed; aborting loop")
                    break

                # TODO: replace with device notify for precise end-of-track
                await asyncio.sleep(10)
                queue.popleft()
            _LOGGER.debug("Queue finished or stopped")
        finally:
            async with play_lock:
                is_playing = False

    # ---- Services ----

    async def svc_enqueue(call: ServiceCall):
        filename = call.data.get("filename")
        if not filename:
            return
        queue.append(filename)
        _LOGGER.info("Enqueued (local): %s", filename)
        if not is_playing:
            hass.async_create_task(_play_loop())

    async def svc_enqueue_url(call: ServiceCall):
        url = call.data.get("url")
        if not url:
            return
        if not URL_RE.match(url):
            _LOGGER.error("Not an http(s) URL: %s", url)
            return
        try:
            local_rel = await _download_to_cache(url)
            queue.append(local_rel)
            _LOGGER.info("Enqueued (remote): %s -> %s", url, local_rel)
            if not is_playing:
                hass.async_create_task(_play_loop())
        except Exception:
            pass

    async def svc_enqueue_m3u(call: ServiceCall):
        url = call.data.get("url")
        if not url or not URL_RE.match(url):
            _LOGGER.error("Invalid M3U URL: %s", url)
            return
        try:
            async with session.get(url, timeout=60) as resp:
                resp.raise_for_status()
                text = await resp.text()
            items = await _parse_m3u(text, url)
            enqueued = 0
            for item in items:
                try:
                    local_rel = await _download_to_cache(item)
                    queue.append(local_rel)
                    enqueued += 1
                except Exception:
                    continue
            _LOGGER.info("M3U enqueued %d items from %s", enqueued, url)
            if enqueued and not is_playing:
                hass.async_create_task(_play_loop())
        except Exception as ex:
            _LOGGER.error("Failed to process M3U %s: %s", url, ex)

    async def svc_play(call: ServiceCall):
        if queue and not is_playing:
            hass.async_create_task(_play_loop())

    async def svc_skip(call: ServiceCall):
        await _send_cmd("NEXT")
        if queue:
            queue.popleft()

    async def svc_clear(call: ServiceCall):
        queue.clear()
        _LOGGER.info("Queue cleared")

    async def svc_stop(call: ServiceCall):
        await _send_cmd("STOP")
        queue.clear()

    # register
    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE, svc_enqueue,
        schema=vol.Schema({vol.Required("filename"): cv.string}))
    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE_URL, svc_enqueue_url,
        schema=vol.Schema({vol.Required("url"): cv.string}))
    hass.services.async_register(DOMAIN, SERVICE_ENQUEUE_M3U, svc_enqueue_m3u,
        schema=vol.Schema({vol.Required("url"): cv.string}))
    hass.services.async_register(DOMAIN, SERVICE_PLAY, svc_play)
    hass.services.async_register(DOMAIN, SERVICE_SKIP, svc_skip)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, svc_clear)
    hass.services.async_register(DOMAIN, SERVICE_STOP, svc_stop)

    async def _shutdown(_evt):
        await ble.disconnect()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown)
    _LOGGER.info(
        "Skelly Queue ready (device: %s, media: %s, cache: %s, remote: %s, limit: %d MB)",
        address, media_dir, cache_dir, allow_remote, max_cache_mb
    )
    return True
