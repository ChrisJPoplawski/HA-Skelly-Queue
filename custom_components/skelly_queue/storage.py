from __future__ import annotations
from homeassistant.helpers.storage import Store

STORE_KEY = "skelly_queue_store"
STORE_VERSION = 2

DEFAULT_STATE = {
    "queue": [],
    "last_played": None,
}

class QueueStore:
    def __init__(self, hass):
        self.hass = hass
        self.store = Store(hass, STORE_VERSION, STORE_KEY)
        self.data = DEFAULT_STATE.copy()

    async def async_load(self):
        stored = await self.store.async_load()
        if stored:
            merged = DEFAULT_STATE.copy()
            merged.update(stored)
            self.data = merged

    async def async_save(self):
        await self.store.async_save(self.data)

    def get_queue(self):
        return list(self.data["queue"])

    async def add(self, item: dict):
        self.data["queue"].append(item)
        await self.async_save()

    async def remove_at(self, idx: int):
        if 0 <= idx < len(self.data["queue"]):
            del self.data["queue"][idx]
            await self.async_save()

    async def clear(self):
        self.data["queue"].clear()
        await self.async_save()

    async def set_last_played(self, item):
        self.data["last_played"] = item
        await self.async_save()
