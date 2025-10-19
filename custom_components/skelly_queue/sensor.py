from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    add([
        SkellyNowPlayingSensor(hass, entry),
        SkellyQueueLengthSensor(hass, entry),
    ])

class SkellyNowPlayingSensor(SensorEntity):
    _attr_name = "Skelly Now Playing"
    _attr_icon = "mdi:music-note"
    def __init__(self, hass, entry):
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_now_playing"
    @property
    def native_value(self):
        return self._hass.states.get(f"{DOMAIN}.now_playing").state

class SkellyQueueLengthSensor(SensorEntity):
    _attr_name = "Skelly Queue Length"
    _attr_icon = "mdi:playlist-music"
    def __init__(self, hass, entry):
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_queue_length"
    @property
    def native_value(self):
        return int(self._hass.states.get(f"{DOMAIN}.queue_length").state)

