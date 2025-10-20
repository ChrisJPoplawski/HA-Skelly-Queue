from __future__ import annotations
import logging
from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

def _get_smbclient():
    # Provided by the 'smbprotocol' package; lazy so HA installs deps first
    import smbclient
    return smbclient

CONF_SMB_HOST = "smb_host"
CONF_SMB_SHARE = "smb_share"
CONF_SMB_USER = "smb_user"
CONF_SMB_PASS = "smb_pass"
CONF_SMB_PATH = "smb_path"

class SmbBrowser:
    def __init__(self, hass, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry

    def _cfg(self):
        d = {**self.entry.data, **self.entry.options}
        return (
            d.get(CONF_SMB_HOST, ""),
            d.get(CONF_SMB_SHARE, ""),
            d.get(CONF_SMB_USER, ""),
            d.get(CONF_SMB_PASS, ""),
            d.get(CONF_SMB_PATH, "/") or "/",
        )

    async def listdir(self, path: str | None = None):
        smbclient = await self.hass.async_add_executor_job(_get_smbclient)
        host, share, user, pwd, base = self._cfg()
        browse = path or base

        def _work():
            smbclient.register_session(host, username=user or None, password=pwd or None, encrypt=True)
            try:
                items = []
                root = f"\\\\{host}\\{share}{browse}".replace("/", "\\")
                for name in smbclient.listdir(root):
                    full = (browse.rstrip("/") + "/" + name) if browse != "/" else "/" + name
                    is_dir = smbclient.path.isdir(f"\\\\{host}\\{share}{full}".replace("/", "\\"))
                    items.append({"name": name, "path": full, "is_dir": is_dir})
                return sorted(items, key=lambda x: (not x["is_dir"], x["name"].lower()))
            finally:
                smbclient.delete_session(host)

        return await self.hass.async_add_executor_job(_work)

