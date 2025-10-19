from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN

def _safe_state(hass: HomeAssistant, entity_id: str, default):
    st: State | None = hass.states.get(entity_id)
    return st.state if st else default

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback):
    add([
        SkellyNowPlayingSensor(hass, entry),
        SkellyQueueLengthSensor(hass, entry),
    ])

class SkellyNowPlayingSensor(SensorEntity):
    _attr_name = "Skelly Now Playing"
    _attr_icon = "mdi:music-note"

    def __init__(self, hass, entry):
        self._hass = hass
        self._attr_unique_id = f"{entry.entry_id}_now_playing"

    @property
    def native_value(self):
        return _safe_state(self._hass, f"{DOMAIN}.now_playing", "")

class SkellyQueueLengthSensor(SensorEntity):
    _attr_name = "Skelly Queue Length"
    _attr_icon = "mdi:playlist-music"

    def __init__(self, hass, entry):
        self._hass = hass
        self._attr_unique_id = f"{entry.entry_id}_queue_length"

    @property
    def native_value(self):
        val = _safe_state(self._hass, f"{DOMAIN}.queue_length", "0")
        try:
            return int(val)
        except Exception:
            return 0

