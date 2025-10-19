from __future__ import annotations
from typing import Any, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import async_ble_device_from_address
import homeassistant.helpers.selector as sel

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from .const import (
    DOMAIN, CONF_ADDRESS, CONF_PLAY_CHAR, CONF_CMD_CHAR,
    CONF_MEDIA_DIR, CONF_ALLOW_REMOTE, CONF_CACHE_DIR, CONF_MAX_CACHE_MB,
    CONF_KEEPALIVE_ENABLED, CONF_KEEPALIVE_SEC,
    CONF_PAIR_ON_CONNECT, CONF_PIN_CODE,
)

def _choices_from_bt(hass: HomeAssistant) -> list[sel.SelectOptionDict]:
    opts: list[sel.SelectOptionDict] = []
    for info in bluetooth.async_discovered_service_info(hass):
        if info.address:
            label = f"{info.name or 'Unknown'} ({info.address})"
            opts.append(sel.SelectOptionDict(value=info.address, label=label))
    seen = set(); uniq = []
    for o in opts:
        if o["value"] in seen: continue
        uniq.append(o); seen.add(o["value"])
    return uniq

async def _detect_write_chars(hass: HomeAssistant, address: str) -> tuple[Optional[str], Optional[str]]:
    dev = async_ble_device_from_address(hass, address, connectable=True)
    if not dev:
        for _ in range(8):
            dev = async_ble_device_from_address(hass, address, connectable=True)
            if dev: break
    if not dev:
        return (None, None)

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
    play_char = cands[0][1] if cands else None
    cmd_char = cands[1][1] if len(cands) > 1 else None
    try: await client.disconnect()
    except Exception: pass
    return (play_char, cmd_char)

class SkellyQueueFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _address: Optional[str] = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_device()

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            addr = user_input.get(CONF_ADDRESS) or user_input.get("discovered")
            self._address = addr
            for e in self._async_current_entries():
                if e.data.get(CONF_ADDRESS) == addr:
                    return self.async_abort(reason="already_configured")
            return await self.async_step_chars()

        schema = vol.Schema({
            vol.Optional("discovered"): sel.SelectSelector(
                sel.SelectSelectorConfig(options=_choices_from_bt(self.hass), mode=sel.SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_ADDRESS, default=""): str,
        })
        return self.async_show_form(step_id="device", data_schema=schema)

    async def async_step_chars(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            auto = user_input.get("auto_detect", True)
            play = (user_input.get(CONF_PLAY_CHAR) or "").strip() or None
            cmd = (user_input.get(CONF_CMD_CHAR) or "").strip() or None

            if auto:
                try:
                    det_play, det_cmd = await _detect_write_chars(self.hass, self._address)
                    play = play or det_play
                    cmd = cmd or det_cmd
                except Exception:
                    errors["base"] = "detect_failed"

            data = {
                CONF_ADDRESS: self._address,
                CONF_PLAY_CHAR: play or "",
                CONF_CMD_CHAR: cmd or "",
                CONF_MEDIA_DIR: "/media/skelly",
                CONF_ALLOW_REMOTE: True,
                CONF_CACHE_DIR: "/media/skelly/cache",
                CONF_MAX_CACHE_MB: 500,
                CONF_KEEPALIVE_ENABLED: True,
                CONF_KEEPALIVE_SEC: 5,
                # Pairing defaults
                CONF_PAIR_ON_CONNECT: True,
                CONF_PIN_CODE: "1234",
            }

            if errors:
                schema = vol.Schema({
                    vol.Optional("auto_detect", default=True): bool,
                    vol.Optional(CONF_PLAY_CHAR, default=play or ""): str,
                    vol.Optional(CONF_CMD_CHAR, default=cmd or ""): str,
                })
                return self.async_show_form(step_id="chars", data_schema=schema, errors=errors)

            return self.async_create_entry(title=f"Skelly ({self._address})", data=data)

        schema = vol.Schema({
            vol.Optional("auto_detect", default=True): bool,
            vol.Optional(CONF_PLAY_CHAR, default=""): str,
            vol.Optional(CONF_CMD_CHAR, default=""): str,
        })
        return self.async_show_form(step_id="chars", data_schema=schema)

    async def async_step_import(self, import_config: dict[str, Any]) -> FlowResult:
        self._address = import_config.get(CONF_ADDRESS)
        return await self.async_step_chars()

# Options flow to tweak media, cache, remote, keepalive, and pairing
class SkellyQueueOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_main(user_input)

    async def async_step_main(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            data = dict(self.entry.data)
            data.update(user_input)
            self.hass.config_entries.async_update_entry(self.entry, data=data)
            return self.async_create_entry(title="", data={})
        d = self.entry.data
        schema = vol.Schema({
            vol.Optional(CONF_MEDIA_DIR, default=d.get(CONF_MEDIA_DIR, "/media/skelly")): str,
            vol.Optional(CONF_ALLOW_REMOTE, default=d.get(CONF_ALLOW_REMOTE, True)): bool,
            vol.Optional(CONF_CACHE_DIR, default=d.get(CONF_CACHE_DIR, "/media/skelly/cache")): str,
            vol.Optional(CONF_MAX_CACHE_MB, default=d.get(CONF_MAX_CACHE_MB, 500)): int,
            vol.Optional(CONF_KEEPALIVE_ENABLED, default=d.get(CONF_KEEPALIVE_ENABLED, True)): bool,
            vol.Optional(CONF_KEEPALIVE_SEC, default=d.get(CONF_KEEPALIVE_SEC, 5)): int,
            vol.Optional(CONF_PAIR_ON_CONNECT, default=d.get(CONF_PAIR_ON_CONNECT, True)): bool,
            vol.Optional(CONF_PIN_CODE, default=d.get(CONF_PIN_CODE, "1234")): str,
        })
        return self.async_show_form(step_id="main", data_schema=schema)

async def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    return SkellyQueueOptionsFlow(config_entry)

