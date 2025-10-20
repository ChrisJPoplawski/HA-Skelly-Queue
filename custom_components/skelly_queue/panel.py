from __future__ import annotations
import os
from aiohttp import web
from homeassistant.components.http import HomeAssistantView

TOAST = """
<div id="toast" style="position:fixed;right:16px;bottom:16px;background:#1f2937;color:#e7e7ea;padding:10px 12px;border-radius:10px;display:none;z-index:9999"></div>
<script>
function toast(msg, ok=true){
  const t=document.getElementById('toast'); t.textContent=msg;
  t.style.background = ok ? '#065f46' : '#7f1d1d';
  t.style.display='block'; setTimeout(()=>t.style.display='none', 2200);
}
</script>
"""

class SkellyPanelView(HomeAssistantView):
    url = "/api/skelly_queue/panel"
    name = "skelly_queue:panel"
    requires_auth = False
    def __init__(self, hass, data):
        self.hass = hass
        self.data = data

    async def get(self, request):
        html_start = """<!doctype html><html><head><meta charset="utf-8"/>
<title>Skelly Queue</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
body{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#0b0b0c;color:#e7e7ea}
header{display:flex;gap:12px;align-items:center;padding:14px 16px;background:#151518;position:sticky;top:0}
h1{font-size:18px;margin:0}
.grid{display:grid;grid-template-columns:1fr 1fr 360px;gap:12px;padding:12px}
.card{background:#1b1b20;border-radius:16px;padding:12px;box-shadow:0 1px 0 rgba(255,255,255,.04) inset}
.list{max-height:54vh;overflow:auto}
.item{display:flex;justify-content:space-between;gap:6px;padding:8px;border-bottom:1px solid #26262b}
.item button{border:none;padding:6px 10px;border-radius:10px;background:#2b2b32;color:#e7e7ea;cursor:pointer}
.bar{display:flex;gap:8px;flex-wrap:wrap}
input,select,textarea{background:#111114;border:1px solid #2b2b32;color:#e7e7ea;border-radius:10px;padding:6px 8px;width:100%}
button.primary{background:#4f46e5}
small{opacity:.7}
pre{white-space:pre-wrap;word-break:break-word;}
.toggle{display:inline-flex;align-items:center;gap:6px}
</style></head>
<body>
<header><h1>💀 Skelly Queue</h1><small id="state"></small></header>

<div class="grid">
  <!-- (Local, SMB, Controls sections unchanged from v0.4.14) -->
</div>

<section class="card" style="margin:12px">
  <div class="bar" style="align-items:center">
    <strong>Live logs</strong>
    <div class="toggle"><input type="checkbox" id="pause-logs"/><label for="pause-logs">Pause</label></div>
    <div class="toggle"><input type="checkbox" id="only-skelly" checked/><label for="only-skelly">Only Skelly logs</label></div>
    <button id="refresh-logs">Refresh</button>
    <button id="export-logs">Export</button>
  </div>
  <pre id="logs" style="height:28vh;overflow:auto;background:#111114;border-radius:10px;padding:12px;border:1px solid #2b2b32"></pre>
</section>
"""
        html_script = """
<script>
async function api(path, opts){
  const r = await fetch('/api/skelly_queue'+path, {credentials:'same-origin', headers:{'Content-Type':'application/json'}, ...opts});
  if(!r.ok){ throw new Error(await r.text()); }
  return r.json();
}
function join(a,b){ if(!a) return b||''; if(!b) return a; return a.replace(/\\/+$/,'')+'/'+b.replace(/^\\/+/, ''); }
let cwd = ''; let ROOT = '';
let paused = false; let logTimer = null;

// (Local/SMB/Controls code unchanged from v0.4.14)

// ---------- Logs ----------
async function refreshLogs(){
  try{
    const only = document.getElementById('only-skelly').checked ? 'skelly' : 'all';
    const r = await fetch('/api/skelly_queue/logs?format=text&only='+only, {credentials:'same-origin'});
    const t = await r.text();
    const el=document.getElementById('logs'); el.textContent = t; el.scrollTop = el.scrollHeight;
  }catch(e){}
}
document.getElementById('refresh-logs').onclick=refreshLogs;
document.getElementById('only-skelly').onchange=refreshLogs;

document.getElementById('pause-logs').onchange = (e)=>{
  paused = !!e.target.checked;
  if(paused && logTimer){ clearInterval(logTimer); logTimer = null; }
  if(!paused && !logTimer){ logTimer = setInterval(refreshLogs, 2000); }
};
document.getElementById('export-logs').onclick=()=>{
  const only = document.getElementById('only-skelly').checked ? 'skelly' : 'all';
  window.open('/api/skelly_queue/logs?download=1&only='+only,'_blank');
};

// init
// (other initializers unchanged)
refreshLogs();
logTimer = setInterval(refreshLogs, 2000);
</script>
</body></html>
"""
        html = html_start + TOAST + html_script
        return web.Response(text=html, content_type="text/html")


async def _executor(hass, fn, *args, **kwargs):
    return await hass.async_add_executor_job(lambda: fn(*args, **kwargs))


class SkellyApiView(HomeAssistantView):
    url = "/api/skelly_queue/{op}"
    name = "skelly_queue:api"
    requires_auth = False

    def __init__(self, hass, data):
        self.hass = hass
        self.data = data

    def _ble(self):
        return self.data.get("ble")

    async def get(self, request, op):
        # (state, list, presets, status unchanged)

        if op == "logs":
            log_path = self.data.get("log_path") or "/config/home-assistant.log"
            only = (request.query.get("only") or "skelly").lower()

            # Build include patterns
            addr = (self.data.get("address") or "").replace(":", "_")
            mac_raw = self.data.get("address") or ""
            patterns = [
                "custom_components.skelly_queue",
                "skelly_queue",
                "skelly_ble",
                "Skelly Queue",
            ]
            if addr:
                patterns += [addr]   # bluez formats MAC as 52_70_08_...
            if mac_raw:
                patterns += [mac_raw]  # raw 52:70:...

            def _read_tail_filtered():
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()[-1200:]  # read a bit more when filtering
                    if only == "skelly":
                        inc = []
                        for ln in lines:
                            L = ln.lower()
                            if any(p.lower() in L for p in patterns):
                                inc.append(ln)
                        return "".join(inc) if inc else "(no Skelly Queue log lines in tail)"
                    # all logs
                    return "".join(lines[-400:])
                except Exception as ex:
                    return f"(log read error) {ex}"

            text = await _executor(self.hass, _read_tail_filtered)

            if request.query.get("format") == "text" and not request.query.get("download"):
                return web.Response(text=text, content_type="text/plain")
            if request.query.get("download"):
                headers = {"Content-Disposition": f'attachment; filename="skelly-logs-{only}.txt"'}
                return web.Response(text=text, content_type="text/plain", headers=headers)
            return self.json({"text": text})

        # (smb_list unchanged)
        return web.Response(status=404)

    async def post(self, request, op):
        # (enqueue, enqueue_dir, enqueue_url, play/skip/stop/clear unchanged)
        # (smb_enqueue_dir unchanged)
        # (BLE background connect/pair/disconnect unchanged)
        return web.Response(status=404)

