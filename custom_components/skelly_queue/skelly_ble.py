import asyncio
import logging
from typing import Optional
from bleak.backends.device import BLEDevice
from homeassistant.components.bluetooth import async_ble_device_from_address
from bleak_retry_connector import establish_connection
from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)

class SkellyBle:
    def __init__(self, hass, address: str, play_char: str, cmd_char: Optional[str] = None):
        self.hass = hass
        self.address = address
        self.play_char = play_char
        self.cmd_char = cmd_char
        self._client: Optional[BleakClient] = None
        self._lock = asyncio.Lock()

    async def _get_ble_device(self) -> Optional[BLEDevice]:
        dev = async_ble_device_from_address(self.hass, self.address, connectable=True)
        if dev:
            return dev
        for _ in range(10):
            await asyncio.sleep(0.5)
            dev = async_ble_device_from_address(self.hass, self.address, connectable=True)
            if dev:
                return dev
        _LOGGER.warning("Skelly BLE device not found: %s", self.address)
        return None

    async def _ensure_client(self) -> Optional[BleakClient]:
        if self._client and self._client.is_connected:
            return self._client
        dev = await self._get_ble_device()
        if not dev:
            return None
        self._client = await establish_connection(
            client_class=BleakClient, device=dev, name="skelly-queue", max_attempts=3
        )
        return self._client

    async def write_play(self, payload: bytes) -> bool:
        async with self._lock:
            client = await self._ensure_client()
            if not client:
                return False
            await client.write_gatt_char(self.play_char, payload, response=True)
            return True

    async def write_cmd(self, payload: bytes) -> bool:
        if not self.cmd_char:
            return False
        async with self._lock:
            client = await self._ensure_client()
            if not client:
                return False
            await client.write_gatt_char(self.cmd_char, payload, response=True)
            return True

    async def disconnect(self):
        async with self._lock:
            if self._client and self._client.is_connected:
                await self._client.disconnect()
            self._client = None

