from __future__ import annotations
import json, os, posixpath
from typing import Any
from aiohttp import web
from homeassistant.components.http import HomeAssistantView

class SkellyPanelView(HomeAssistantView):
    """Serves the simple file-picker UI and JSON endpoints."""
    url = "/skelly_queue"
    name = "skelly_queue:index"
    requires_auth = True

    def __init__(self, hass, data):
        self.hass = hass
        self.data = data  # dict with media_dir, queue, controls, presets

    async def get(self, request):
        # Single-page app (vanilla HTML+JS)
        html = """
<!doctype html><html><head><meta charset="utf-8"/>
<title>Skelly Queue</title>
<style>
body{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#0b0b0c;color:#e7e7ea}
header{display:flex;gap:12px;align-items:center;padding:14px 16px;background:#151518;position:sticky;top:0}
h1{font-size:18px;margin:0}
main{display:grid;grid-template-columns:1fr 340px;gap:12px;padding:12px}
.card{background:#1b1b20;border-radius:16px;padding:12px;box-shadow:0 1px 0 rgba(255,255,255,.04) inset}
.list{max-height:70vh;overflow:auto}
.item{display:flex;justify-content:space-between;gap:6px;padding:8px;border-bottom:1px solid #26262b}
.item button{border:none;padding:6px 10px;border-radius:10px;background:#2b2b32;color:#e7e7ea;cursor:pointer}
.bar{display:flex;gap:8px;flex-wrap:wrap}
input,select{background:#111114;border:1px solid #2b2b32;color:#e7e7ea;border-radius:10px;padding:6px 8px;width:100%}
button.primary{background:#4f46e5}
small{opacity:.7}
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
      <input id="url" placeholder="https://example.com/file.mp3 or playlist.m3u8"/>
      <button id="enqueue-url">Enqueue URL</button>
    </div>
    <hr/>
    <div class="bar">
      <input id="preset-name" placeholder="Preset name (e.g. Halloween Night)"/>
      <button id="save-preset">Save preset</button>
      <select id="preset-load"></select>
      <button id="load-preset">Load preset</button>
    </div>
    <p><small>Media root: <code id="root"></code></small></p>
  </aside>
</main>
<script>
async function api(path, opts){const r = await fetch('/skelly_queue/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...opts}); if(!r.ok) throw new Error(await r.text()); return r.json();}
function join(a,b){if(!a) return b||''; if(!b) return a; return a.replace(/\\/+$/,'')+'/'+b.replace(/^\\/+/, '');}
let cwd = ''; let ROOT = '';
async function refreshState(){const s = await api('/state'); document.getElementById('state').textContent = `Now: ${s.now||'-'} • Queue: ${s.len}`;}
async function list(dir){const data = await api('/list?path='+encodeURIComponent(dir||'')); ROOT = data.root; document.getElementById('root').textContent = ROOT; cwd = data.path||''; document.getElementById('path').value=cwd; const el=document.getElementById('list'); el.innerHTML='';
  if(cwd){const up=document.createElement('div'); up.className='item'; up.innerHTML='<div>..</div><div><button>Open</button></div>'; up.querySelector('button').onclick=()=>{const p=cwd.replace(/\\/?[^\\/]+$/,''); list(p)}; el.appendChild(up);}
  for(const d of data.dirs){const row=document.createElement('div'); row.className='item'; row.innerHTML='<div>📁 '+d+'</div><div><button>Open</button><button>Enqueue</button></div>'; const [open,enq]=row.querySelectorAll('button'); open.onclick=()=>list(join(cwd,d)); enq.onclick=()=>enqueueDir(join(cwd,d)); el.appendChild(row);}
  for(const f of data.files){const row=document.createElement('div'); row.className='item'; row.innerHTML='<div>🎵 '+f+'</div><div><button>Add</button></div>'; row.querySelector('button').onclick=()=>enqueue(join(cwd,f)); el.appendChild(row);}
  refreshState();
}
async function enqueue(rel){await api('/enqueue',{method:'POST',body:JSON.stringify({filename:rel})}); refreshState();}
async function enqueueDir(rel){const recursive=document.getElementById('recursive').checked; const shuffle=document.getElementById('shuffle').checked; await api('/enqueue_dir',{method:'POST',body:JSON.stringify({subpath:rel,recursive,shuffle})}); refreshState();}
document.getElementById('browse').onclick=()=>list(document.getElementById('path').value.trim());
document.getElementById('up').onclick=()=>{if(!cwd) return; const p=cwd.replace(/\\/?[^\\/]+$/,''); list(p);}
document.getElementById('enqueue-all').onclick=()=>enqueueDir(cwd);
document.getElementById('enqueue-url').onclick=async()=>{const u=document.getElementById('url').value.trim(); if(!u) return; await api('/enqueue_url',{method:'POST',body:JSON.stringify({url:u})}); document.getElementById('url').value=''; refreshState();};
for(const [id,svc] of [['play','play'],['skip','skip'],['stop','stop'],['clear','clear']]){
  document.getElementById(id).onclick=()=>api('/'+svc,{method:'POST'}).then(refreshState);
}
async function loadPresets(){const p = await api('/presets'); const sel = document.getElementById('preset-load'); sel.innerHTML=''; p.forEach(name=>{const o=document.createElement('option'); o.value=name;o.textContent=name;sel.appendChild(o);});}
document.getElementById('save-preset').onclick=async()=>{const name=document.getElementById('preset-name').value.trim(); if(!name) return; await api('/save_preset',{method:'POST',body:JSON.stringify({name})}); await loadPresets();};
document.getElementById('load-preset').onclick=async()=>{const name=document.getElementById('preset-load').value; if(!name) return; await api('/load_preset',{method:'POST',body:JSON.stringify({name})}); refreshState();};
list(''); loadPresets();
</script>
</body></html>
"""
        return web.Response(text=html, content_type="text/html")

class SkellyApiView(HomeAssistantView):
    url = "/skelly_queue/api/{op}"
    name = "skelly_queue:api"
    requires_auth = True

    def __init__(self, hass, data):
        self.hass = hass
        self.data = data  # same dict from __init__.py

    async def get(self, request, op):
        if op == "state":
            now = self.hass.states.get("skelly_queue.now_playing")
            ln  = self.hass.states.get("skelly_queue.queue_length")
            return self.json({"now": (now.state if now else ""), "len": int(ln.state) if ln else 0})
        if op == "list":
            media_root = self.data["config"]["media_dir"]
            rel = request.query.get("path","").strip().strip("/")
            root = media_root
            base = os.path.abspath(root)
            target = os.path.abspath(os.path.join(root, rel))
            if not target.startswith(base):  # path traversal guard
                target = base
                rel = ""
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
            return self.json({"root": root, "path": rel, "dirs": dirs, "files": files})
        if op == "presets":
            presets = sorted(self.data["presets"].keys())
            return self.json(presets)
        return web.Response(status=404)

    async def post(self, request, op):
        body = await request.json() if request.can_read_body else {}
        svc = self.hass.services.async_call
        if op == "enqueue":
            await svc("skelly_queue", "enqueue", {"filename": body.get("filename")}, blocking=True); return self.json({"ok":1})
        if op == "enqueue_dir":
            await svc("skelly_queue", "enqueue_dir", body, blocking=True); return self.json({"ok":1})
        if op == "enqueue_url":
            url = body.get("url"); 
            if url and url.lower().endswith((".m3u",".m3u8")):
                await svc("skelly_queue", "enqueue_m3u", {"url": url}, blocking=True)
            else:
                await svc("skelly_queue", "enqueue_url", {"url": url}, blocking=True)
            return self.json({"ok":1})
        if op in ("play","skip","stop","clear"):
            await svc("skelly_queue", op, {}, blocking=True); return self.json({"ok":1})
        if op == "save_preset":
            name = (body.get("name") or "").strip()
            if name: 
                q = list(self.data["queue"])  # snapshot current queue (relative paths)
                self.data["presets"][name] = q
                await self.data["store"].async_save(self.data["presets"])
            return self.json({"ok":1})
        if op == "load_preset":
            name = (body.get("name") or "").strip()
            items = self.data["presets"].get(name, [])
            await svc("skelly_queue", "enqueue_bulk", {"items": items}, blocking=True)
            return self.json({"ok":1})
        return web.Response(status=404)

