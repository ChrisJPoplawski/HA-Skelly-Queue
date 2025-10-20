from __future__ import annotations
import io, json, zipfile, datetime as dt, logging
from homeassistant.core import HomeAssistant
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.frontend import async_register_built_in_panel

DOMAIN = "skelly_queue"
DATA_KEY = f"{DOMAIN}_data"
_LOGGER = logging.getLogger(__name__)

class SkellyHttpView(HomeAssistantView):
    url = "/api/skelly_queue"
    name = "api:skelly_queue"
    requires_auth = True

    @classmethod
    def register(cls, hass: HomeAssistant):
        hass.http.register_view(cls())

    async def get(self, request):
        """GET /api/skelly_queue?op=browse&path=/  |  op=queue"""
        hass = request.app["hass"]
        op = request.query.get("op")
        data = hass.data[DOMAIN][DATA_KEY]

        if op == "browse":
            path = request.query.get("path", "/")
            items = await data["smb"].listdir(path)
            return self.json({"items": items})

        if op == "queue":
            return self.json({"queue": data["store"].get_queue()})

        return self.json({"error": "unsupported op"}, status_code=400)

    async def post(self, request):
        """POST /api/skelly_queue with JSON:
           { action: add|remove_at|clear|export_logs, ... }"""
        hass = request.app["hass"]
        body = await request.json()
        action = body.get("action")
        data = hass.data[DOMAIN][DATA_KEY]

        if action == "add":
            await data["store"].add(body.get("item") or {})
            return self.json({"ok": True})

        if action == "remove_at":
            await data["store"].remove_at(int(body.get("index", -1)))
            return self.json({"ok": True})

        if action == "clear":
            await data["store"].clear()
            return self.json({"ok": True})

        if action == "export_logs":
            mem = io.BytesIO()
            now = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(f"state/queue-{now}.json", json.dumps(data["store"].data, indent=2))
            mem.seek(0)
            return self.Response(
                body=mem.read(),
                status=200,
                headers={
                    "Content-Type": "application/zip",
                    "Content-Disposition": f'attachment; filename="skelly_logs_{now}.zip"'
                },
            )

        return self.json({"error": "unknown action"}, status_code=400)

def register_panel(hass: HomeAssistant):
    # Shows "Skelly Queue" in the sidebar (iframe → /local/skelly_queue/index.html).
    async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title="Skelly Queue",
        sidebar_icon="mdi:skull",
        frontend_url_path="skelly-queue",
        config={"url": "/local/skelly_queue/index.html"},
        require_admin=False,
    )

