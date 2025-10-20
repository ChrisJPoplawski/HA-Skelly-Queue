from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

DOMAIN = "skelly_queue"
DATA_KEY = f"{DOMAIN}_data"
_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BUTTON,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialize Skelly Queue."""
    hass.data.setdefault(DOMAIN, {})

    # Import inside function so HA installs requirements first.
    from .storage import QueueStore
    from .smb_browser import SmbBrowser

    store = QueueStore(hass)
    await store.async_load()

    hass.data[DOMAIN][DATA_KEY] = {
        "store": store,
        "smb": SmbBrowser(hass, entry),
    }

    # Optional panel/API
    try:
        from .http import SkellyHttpView, register_panel
        SkellyHttpView.register(hass)
        register_panel(hass)
    except Exception as e:
        _LOGGER.debug("Panel/API not registered (optional): %s", e)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _LOGGER.info("Skelly Queue v%s initialized", "0.4.19")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(DATA_KEY, None)
    return ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

