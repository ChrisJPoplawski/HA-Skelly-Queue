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
    """Public HTML panel. All actions go to auth'd /api/skelly_queue endpoints."""
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
main{display:grid;grid-template-columns:1fr 360px;gap:12px;padding:12px}
.card{background:#1b1b20;border-radius:16px;padding:12px;box-shadow:0 1px 0 rgba(255,255,255,.04) inset}
.list{max-height:54vh;overflow:auto}
.item{display:flex;justify-content:space-between;gap:6px;padding:8px;border-bottom:1px solid #26262b}
.item button{border:none;padding:6px 10px;border-radius:10px;background:#2b2b32;color:#e7e7ea;cursor:pointer}
.bar{display:flex;gap:8px;flex-wrap:wrap}
input,select,textarea{background:#111114;border:1px solid #2b2b32;color:#e7e7ea;border-radius:10px;padding:6px 8px;width:100%}
button.primary{background:#4f46e5}
small{opacity:.7}
pre{white-space:pre-wrap;word-break:break-word;}
</style></head>
<body>
<header><h1>💀 Skelly Queue</h1><small id="state"></small></header>
<main>
  <section class="card">
    <div class="bar">
      <input id="path" placeholder="subfolder (relative to media_dir) e.g. night_show"/>
      <button id="browse" class="primary">Browse</button>
      <button id="up">⬆️ Up</button>
      <button id="enqueue-all">Enqueue Folder</button>
      <label><input type="checkbox" id="recursive" checked/> recursive</label>
      <label><input type="checkbox" id="shuffle"/> shuffle</label>
    </div>
    <div class="list" id="list"></div>
  </section>
  <aside class="card">
    <div class="bar">
      <button id="play" class="primary">▶ Play</button>
      <button id="skip">⏭ Skip</button>
      <button id="stop">⏹ Stop</button>
      <button id="clear">🗑 Clear</button>
    </div>
    <hr/>
    <div class="bar">
      <input id="url" placeholder="https://… or smb://user:pass@host/share/file.mp3 or .m3u8"/>
      <button id="enqueue-url">Enqueue URL</button>
    </div>
    <hr/>
    <div class="bar">
      <button id="status">🔌 Status</button>
      <button id="connect">🔄 Connect</button>
      <button id="disconnect">❌ Disconnect</button>
      <button id="pair">🔢 Pair</button>
    </div>
    <hr/>
    <div class="bar">
      <input id="preset-name" placeholder="Preset name"/>
      <button id="save-preset">Save preset</button>
      <select id="preset-load"></select>
      <button id="load-preset">Load preset</button>
    </div>
    <p><small>Media root: <code id="root"></code></small></p>
  </aside>
</main>

<section class="card" style="margin:12px">
  <div class="bar"><strong>Live logs</strong><button id="refresh-logs">Refresh</button></div>
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

async function refreshState(){
  try{
    const s = await api('/state');
    document.getElementById('state').textContent = `Now: ${s.now||'-'} • Queue: ${s.len}`;
  }catch(e){ document.getElementById('state').textContent = '—'; }
}

async function list(dir){
  const data = await api('/list?path='+encodeURIComponent(dir||''));
  ROOT = data.root; document.getElementById('root').textContent = ROOT;
  cwd = data.path||''; document.getElementById('path').value=cwd;
  const el=document.getElementById('list'); el.innerHTML='';
  if(cwd){
    const up=document.createElement('div'); up.className='item';
    up.innerHTML='<div>..</div><div><button>Open</button></div>';
    up.querySelector('button').onclick=()=>{ const p=cwd.replace(/\\/?[^\\/]+$/,''); list(p) };
    el.appendChild(up);
  }
  for(const d of data.dirs){
    const row=document.createElement('div'); row.className='item';
    row.innerHTML='<div>📁 '+d+'</div><div><button>Open</button><button>Enqueue</button></div>';
    const [open,enq]=row.querySelectorAll('button');
    open.onclick=()=>list(join(cwd,d));
    enq.onclick=()=>enqueueDir(join(cwd,d));
    el.appendChild(row);
  }
  for(const f of data.files){
    const row=document.createElement('div'); row.className='item';
    row.innerHTML='<div>🎵 '+f+'</div><div><button>Add</button></div>';
    row.querySelector('button').onclick=()=>enqueue(join(cwd,f));
    el.appendChild(row);
  }
  refreshState();
}

async function enqueue(rel){
  try{ await api('/enqueue',{method:'POST',body:JSON.stringify({filename:rel})}); toast('Added: '+rel); }
  catch(e){ toast(e.message,false); }
}
async function enqueueDir(rel){
  const recursive=document.getElementById('recursive').checked;
  const shuffle=document.getElementById('shuffle').checked;
  try{ await api('/enqueue_dir',{method:'POST',body:JSON.stringify({subpath:rel,recursive,shuffle})}); toast('Enqueued folder'); }
  catch(e){ toast(e.message,false); }
}

document.getElementById('browse').onclick=()=>list(document.getElementById('path').value.trim());
document.getElementById('up').onclick=()=>{if(!cwd) return; const p=cwd.replace(/\\/?[^\\/]+$/,''); list(p);}
document.getElementById('enqueue-all').onclick=()=>enqueueDir(cwd);
document.getElementById('enqueue-url').onclick=async()=>{
  const u=document.getElementById('url').value.trim(); if(!u) return;
  try{
    if(u.toLowerCase().endsWith('.m3u')||u.toLowerCase().endsWith('.m3u8')){
      await api('/enqueue_m3u',{method:'POST',body:JSON.stringify({url:u})});
    }else{
      await api('/enqueue_url',{method:'POST',body:JSON.stringify({url:u})});
    }
    toast('Queued URL'); document.getElementById('url').value='';
    refreshState();
  }catch(e){ toast(e.message,false); }
};

for(const [id,svc] of [['play','play'],['skip','skip'],['stop','stop'],['clear','clear']]){
  document.getElementById(id).onclick=()=>api('/'+svc,{method:'POST'})
    .then(()=>{toast(svc+' ok'); refreshState();})
    .catch(e=>toast(e.message,false));
}

document.getElementById('status').onclick=()=>api('/status').then(s=>toast('BLE '+(s.connected?'connected':'disconnected'))).catch(e=>toast(e.message,false));
document.getElementById('connect').onclick=()=>api('/connect',{method:'POST'}).then(()=>toast('Connecting…')).catch(e=>toast(e.message,false));
document.getElementById('disconnect').onclick=()=>api('/disconnect',{method:'POST'}).then(()=>toast('Disconnected')).catch(e=>toast(e.message,false));
document.getElementById('pair').onclick=()=>api('/pair',{method:'POST'}).then(()=>toast('Pair attempt sent')).catch(e=>toast(e.message,false));

async function refreshLogs(){
  try{
    const j = await api('/logs');
    const el=document.getElementById('logs'); el.textContent = j.text; el.scrollTop = el.scrollHeight;
  }catch(e){}
}
document.getElementById('refresh-logs').onclick=refreshLogs;
setInterval(refreshLogs, 2000);

list(''); refreshLogs();
</script>
</body></html>
"""
        html = html_start + TOAST + html_script
        return web.Response(text=html, content_type="text/html")


class SkellyApiView(HomeAssistantView):
    """Authenticated JSON API."""
    url = "/api/skelly_queue/{op}"
    name = "skelly_queue:api"
    requires_auth = True

    def __init__(self, hass, data):
        self.hass = hass
        self.data = data

    def _ble(self):
        return self.data.get("ble")

    async def get(self, request, op):
        if op == "state":
            now = self.hass.states.get("skelly_queue.now_playing")
            ln  = self.hass.states.get("skelly_queue.queue_length")
            return self.json({"now": (now.state if now else ""), "len": int(ln.state) if ln else 0})
        if op == "list":
            media_root = self.data["config"]["media_dir"]
            rel = request.query.get("path","").strip().strip("/")
            base = os.path.abspath(media_root)
            target = os.path.abspath(os.path.join(media_root, rel))
            if not target.startswith(base): target = base; rel = ""
            dirs, files = [], []
            try:
                for name in os.listdir(target):
                    if name.startswith("."): continue
                    p = os.path.join(target, name)
                    if os.path.isdir(p): dirs.append(name)
                    else: files.append(name)
            except Exception:
                pass
            dirs.sort(); files.sort()
            return self.json({"root": media_root, "path": rel, "dirs": dirs, "files": files})
        if op == "presets":
            return self.json(sorted(self.data["presets"].keys()))
        if op == "status":
            ble = self._ble()
            connected = bool(ble and ble._client and ble._client.is_connected)  # noqa
            return self.json({"connected": connected, "address": self.data.get("address")})
        if op == "logs":
            log_path = self.data.get("log_path") or "/config/home-assistant.log"
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-400:]
                return self.json({"text": "".join(lines)})
            except Exception as ex:
                return self.json({"text": f"(log read error) {ex}"})
        return web.Response(status=404)

    async def post(self, request, op):
        body = await request.json() if request.can_read_body else {}
        if op == "enqueue":
            await self.hass.services.async_call("skelly_queue", "enqueue", {"filename": body.get("filename")}, blocking=True); return self.json({"ok":1})
        if op == "enqueue_dir":
            await self.hass.services.async_call("skelly_queue", "enqueue_dir", body, blocking=True); return self.json({"ok":1})
        if op == "enqueue_url":
            await self.hass.services.async_call("skelly_queue", "enqueue_url", {"url": body.get("url")}, blocking=True); return self.json({"ok":1})
        if op in ("play","skip","stop","clear"):
            await self.hass.services.async_call("skelly_queue", op, {}, blocking=True); return self.json({"ok":1})
        ble = self._ble()
        if op == "connect":
            if ble: await ble._ensure_client()
            return self.json({"ok":1})
        if op == "disconnect":
            if ble: await ble.disconnect()
            return self.json({"ok":1})
        if op == "pair":
            if ble and ble._client:
                try: await ble._client.pair()
                except Exception: pass
            return self.json({"ok":1})
        return web.Response(status=404)

