from __future__ import annotations
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, SERVICE_PLAY, SERVICE_SKIP, SERVICE_STOP, SERVICE_CLEAR

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback):
    add([
        SkellyActionButton(hass, entry, "Play", SERVICE_PLAY, "mdi:play"),
        SkellyActionButton(hass, entry, "Skip", SERVICE_SKIP, "mdi:skip-next"),
        SkellyActionButton(hass, entry, "Stop", SERVICE_STOP, "mdi:stop"),
        SkellyActionButton(hass, entry, "Clear", SERVICE_CLEAR, "mdi:playlist-remove"),
    ])

class SkellyActionButton(ButtonEntity):
    def __init__(self, hass, entry, name, svc, icon):
        self._hass = hass
        self._svc = svc
        self._attr_name = f"Skelly {name}"
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{name.lower()}"

    async def async_press(self) -> None:
        await self._hass.services.async_call(DOMAIN, self._svc, {}, blocking=False)

