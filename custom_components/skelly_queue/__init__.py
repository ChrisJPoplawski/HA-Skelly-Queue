from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

DOMAIN = "skelly_queue"
DATA_KEY = f"{DOMAIN}_data"
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialize Skelly Queue."""
    hass.data.setdefault(DOMAIN, {})

    # Import inside function so HA can install requirements first.
    from .storage import QueueStore
    from .smb_browser import SmbBrowser

    store = QueueStore(hass)
    await store.async_load()

    hass.data[DOMAIN][DATA_KEY] = {
        "store": store,
        "smb": SmbBrowser(hass, entry),
    }

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _LOGGER.info("Skelly Queue initialized")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

