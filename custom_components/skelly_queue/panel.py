from __future__ import annotations
import os
from aiohttp import web
from homeassistant.components.http import HomeAssistantView

class SkellyPanelView(HomeAssistantView):
    """HTML panel for the Skelly Queue (no auth required; no sensitive data)."""
    url = "/api/skelly_queue/panel"
    name = "skelly_queue:panel"
    requires_auth = False   # ⟵ was True

    def __init__(self, hass, data):
        self.hass = hass
        self.data = data

    async def get(self, request):
        # (unchanged) — HTML string that loads the UI and calls /api/skelly_queue/* via fetch()
        # ...
        return web.Response(text=html, content_type="text/html")


class SkellyApiView(HomeAssistantView):
    """Authenticated JSON API endpoints used by the panel JS."""
    url = "/api/skelly_queue/{op}"
    name = "skelly_queue:api"
    requires_auth = True    # ⟵ stay authenticated

    # (rest unchanged)

