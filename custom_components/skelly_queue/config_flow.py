from __future__ import annotations
import voluptuous as vol
from typing import Any, Optional
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.components import bluetooth
import homeassistant.helpers.selector as sel

from .const import (
    DOMAIN, CONF_ADDRESS, CONF_PLAY_CHAR, CONF_CMD_CHAR,
    CONF_MEDIA_DIR, CONF_ALLOW_REMOTE, CONF_CACHE_DIR, CONF_MAX_CACHE_MB
)

def _choices_from_bt(hass: HomeAssistant) -> list[sel.SelectOptionDict]:
    opts: list[sel.SelectOptionDict] = []
    for dev in bluetooth.async_discovered_service_info(hass):
        if dev.address:
            name = dev.name or "Unknown"
            label = f"{name} ({dev.address})"
            opts.append(sel.SelectOptionDict(value=dev.address, label=label))
    # dedupe by value
    seen = set()
    uniq = []
    for o in opts:
        if o["value"] in seen: continue
        uniq.append(o); seen.add(o["value"])
    return uniq

class SkellyQueueFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _address: Optional[str] = None
    _play_char: Optional[str] = None
    _cmd_char: Optional[str] = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_device()

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            addr = user_input.get(CONF_ADDRESS) or user_input.get("discovered")
            self._address = addr
            # prevent duplicates
            for entry in self._async_current_entries():
                if entry.data.get(CONF_ADDRESS) == addr:
                    return self.async_abort(reason="already_configured")
            return await self.async_step_chars()

        options = _choices_from_bt(self.hass)
        schema = vol.Schema({
            vol.Optional("discovered"): sel.SelectSelector(
                sel.SelectSelectorConfig(options=options, mode=sel.SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_ADDRESS, default=""): str,
        })
        return self.async_show_form(step_id="device", data_schema=schema)

    async def async_step_chars(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._play_char = user_input[CONF_PLAY_CHAR]
            self._cmd_char = user_input.get(CONF_CMD_CHAR)
            data = {
                CONF_ADDRESS: self._address,
                CONF_PLAY_CHAR: self._play_char,
                CONF_CMD_CHAR: self._cmd_char,
                CONF_MEDIA_DIR: "/media/skelly",
                CONF_ALLOW_REMOTE: True,
                CONF_CACHE_DIR: "/media/skelly/cache",
                CONF_MAX_CACHE_MB: 500,
            }
            return self.async_create_entry(title=f"Skelly ({self._address})", data=data)

        schema = vol.Schema({
            vol.Required(CONF_PLAY_CHAR): str,
            vol.Optional(CONF_CMD_CHAR): str,
        })
        return self.async_show_form(step_id="chars", data_schema=schema)

    async def async_step_import(self, import_config: dict[str, Any]) -> FlowResult:
        """YAML import (optional)."""
        return await self.async_step_device(import_config)

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
        })
        return self.async_show_form(step_id="main", data_schema=schema)

async def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    return SkellyQueueOptionsFlow(config_entry)

