from __future__ import annotations

import asyncio
import json
import os
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

DOMAIN = "skelly_queue"


class SkellyPanelView(HomeAssistantView):
    """Serve the Skelly Queue web UI."""

    url = "/api/skelly_queue/panel"
    name = "api:skelly_queue_panel"

    def __init__(self, hass: HomeAssistant, panel_data: dict) -> None:
        self.hass = hass
        self.panel_data = panel_data

    async def get(self, request: web.Request) -> web.Response:
        """Return simple HTML UI."""
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Skelly Queue</title>
  <style>
    body {{ background:#0b0d10; color:#e5e7eb; font-family:sans-serif; }}
    input,button {{ margin:3px; }}
    pre {{ background:#111; padding:6px; overflow:auto; height:160px; }}
    .col {{ display:inline-block; vertical-align:top; margin:8px; }}
  </style>
</head>
<body>
  <h2>💀 Skelly Queue</h2>

  <div class="col">
    <h3>Local library</h3>
    <input id="subpath" size="30" placeholder="relative to /media/skelly" />
    <button onclick="browse()">Browse</button>
    <button onclick="enqueueDir()">Enqueue Folder</button><br/>
    <label><input type="checkbox" id="recursive" checked/>recursive</label>
    <label><input type="checkbox" id="shuffle"/>shuffle</label>
    <div id="local"></div>
  </div>

  <div class="col">
    <h3>Remote SMB library</h3>
    <input id="smb_host" placeholder="192.168.1.10" size="12"/>
    <input id="smb_share" placeholder="Share" size="8"/>
    <input id="smb_user" placeholder="User" size="8"/>
    <input id="smb_pass" placeholder="Pass" type="password" size="8"/>
    <button onclick="smbList()">List</button>
    <button onclick="smbEnqueue()">Enqueue</button>
    <div id="smb"></div>
  </div>

  <div class="col">
    <h3>Controls</h3>
    <button onclick="api('/play')">▶ Play</button>
    <button onclick="api('/skip')">⏭ Skip</button>
    <button onclick="api('/stop')">⏹ Stop</button>
    <button onclick="api('/clear')">🗑 Clear</button>
  </div>

  <h3>Live logs</h3>
  <button onclick="refresh()">Refresh</button>
  <button onclick="pause=!pause">Pause</button>
  <button onclick="exportLog()">Export</button>
  <pre id="log"></pre>

<script>
let pause=false;
async function api(path, body) {{
  const r = await fetch('/api/skelly_queue'+path, {{
    method:'POST',
    credentials:'same-origin',
    headers:{{'Content-Type':'application/json'}},
    body: body ? JSON.stringify(body):'{{}}'
  }});
  if(!r.ok) alert(await r.text());
}}
async function browse(){{
  const sp=document.getElementById('subpath').value;
  const r=await fetch('/api/skelly_queue/list?subpath='+encodeURIComponent(sp));
  document.getElementById('local').textContent=await r.text();
}}
async function enqueueDir(){{
  await api('/enqueue_dir',{{
    subpath:document.getElementById('subpath').value,
    recursive:document.getElementById('recursive').checked,
    shuffle:document.getElementById('shuffle').checked
  }});
}}
async function smbList(){{
  const p=new URLSearchParams({{
    host:document.getElementById('smb_host').value,
    share:document.getElementById('smb_share').value,
    user:document.getElementById('smb_user').value,
    pass:document.getElementById('smb_pass').value
  }});
  const r=await fetch('/api/skelly_queue/smb_list?'+p);
  document.getElementById('smb').textContent=await r.text();
}}
async function smbEnqueue(){{
  await api('/smb_enqueue_dir',{{
    host:document.getElementById('smb_host').value,
    share:document.getElementById('smb_share').value,
    user:document.getElementById('smb_user').value,
    pass:document.getElementById('smb_pass').value
  }});
}}
async function refresh(){{
  if(pause) return;
  const r=await fetch('/api/skelly_queue/logs');
  document.getElementById('log').textContent=await r.text();
  setTimeout(refresh,4000);
}}
refresh();
</script>
</body></html>"""
        return web.Response(text=html, content_type="text/html")


class SkellyApiView(HomeAssistantView):
    """Handle API actions for Skelly Queue."""

    url = "/api/skelly_queue/{path:.*}"
    name = "api:skelly_queue"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, panel_data: dict) -> None:
        self.hass = hass
        self.data = panel_data
        self.log_path = panel_data.get("log_path", "/config/home-assistant.log")

    # ----------------------- HTTP GETs -----------------------
    async def get(self, request: web.Request, path: str) -> web.Response:
        try:
            if path == "list":
                return await self._list_local(request)
            if path == "smb_list":
                return await self._smb_list(request)
            if path == "logs":
                return await self._logs(request)
            return web.Response(status=404, text=f"Unknown path {path}")
        except Exception as ex:
            return web.Response(status=500, text=str(ex))

    async def _list_local(self, request: web.Request) -> web.Response:
        sub = request.query.get("subpath", "")
        base = self.data["config"]["media_dir"]
        start = os.path.join(base, sub.strip("/"))
        if not os.path.isdir(start):
            return web.Response(text=f"{start} not found")
        names = os.listdir(start)
        return web.Response(text="\n".join(names))

    async def _smb_list(self, request: web.Request) -> web.Response:
        # Lazy import
        try:
            import smbclient  # type: ignore
        except Exception as ex:
            return web.Response(status=500, text=f"smbclient not available yet: {ex}")

        host = request.query.get("host")
        share = request.query.get("share")
        user = request.query.get("user") or None
        pw = request.query.get("pass") or None
        if not (host and share):
            return web.Response(status=400, text="host and share required")

        smbclient.reset_connection_cache()
        smbclient.register_session(server=host, username=user, password=pw, port=445)

        remote = rf"\\{host}\{share}"
        try:
            entries = smbclient.listdir(remote)
        except Exception as ex:
            return web.Response(status=500, text=f"SMB error: {ex}")

        return web.Response(text="\n".join(entries))

    async def _logs(self, request: web.Request) -> web.Response:
        path = self.log_path
        if not os.path.isfile(path):
            return web.Response(text="No log file")
        # stream last 200 lines
        def tail(fp, n=200):
            with open(fp, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                block = 1024
                data = b""
                while size > 0 and data.count(b"\n") <= n:
                    step = min(block, size)
                    size -= step
                    f.seek(size)
                    data = f.read(step) + data
                return b"\n".join(data.splitlines()[-n:]).decode("utf-8", "ignore")
        text = tail(path)
        return web.Response(text=text)

    # ----------------------- HTTP POSTs -----------------------
    async def post(self, request: web.Request, path: str) -> web.Response:
        body = await request.text()
        data = json.loads(body or "{}")

        try:
            if path in ("enqueue_dir", "smb_enqueue_dir", "enqueue_url", "play", "skip", "stop", "clear"):
                # Use HA service layer so state updates flow normally
                await self.hass.services.async_call(DOMAIN, path, data)
                return web.Response(text="OK")
            return web.Response(status=404, text=f"Unknown POST {path}")
        except Exception as ex:
            return web.Response(status=500, text=str(ex))

