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
    """Public HTML panel. All actions go to /api/skelly_queue/* endpoints."""
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
  <!-- Local Library -->
  <section class="card">
    <h3>Local library</h3>
    <div class="bar">
      <input id="path" placeholder="subfolder (relative to media_dir) e.g. night_show"/>
      <button id="browse" class="primary">Browse</button>
      <button id="up">⬆️ Up</button>
      <button id="enqueue-all">Enqueue Folder</button>
      <label><input type="checkbox" id="recursive" checked/> recursive</label>
      <label><input type="checkbox" id="shuffle"/> shuffle</label>
    </div>
    <div class="list" id="list"></div>
    <p><small>Media root: <code id="root"></code></small></p>
  </section>

  <!-- Remote SMB Library -->
  <section class="card">
    <h3>Remote SMB library</h3>
    <div class="bar">
      <input id="r_base" placeholder="smb://user:pass@host/share[/path]" />
      <button id="r_browse" class="primary">Browse</button>
      <button id="r_up">⬆️ Up</button>
      <button id="r_enqueue-all">Enqueue Folder</button>
      <label><input type="checkbox" id="r_recursive" checked/> recursive</label>
      <label><input type="checkbox" id="r_shuffle"/> shuffle</label>
    </div>
    <div class="list" id="r_list"></div>
  </section>

  <!-- Controls -->
  <aside class="card">
    <h3>Controls</h3>
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
  </aside>
</div>

<section class="card" style="margin:12px">
  <div class="bar" style="align-items:center">
    <strong>Live logs</strong>
    <div class="toggle"><input type="checkbox" id="pause-logs"/><label for="pause-logs">Pause</label></div>
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
let paused = false;
let logTimer = null;

// ---------- Local library ----------
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

// ---------- Remote SMB library ----------
let r_cwd = '';   // smb://.../share/path (current folder)
function ensureTrailingSlash(s){ return s.endsWith('/') ? s : s+'/'; }

async function r_list(url){
  const data = await api('/smb_list?url='+encodeURIComponent(url));
  r_cwd = data.url; document.getElementById('r_base').value = r_cwd;
  const el=document.getElementById('r_list'); el.innerHTML='';
  // Up
  try{
    const u = new URL(r_cwd);
    const parts = u.pathname.split('/').filter(Boolean);
    if(parts.length>1){
      const up = new URL(r_cwd);
      up.pathname = '/'+parts.slice(0,-1).join('/')+'/';
      const row=document.createElement('div'); row.className='item';
      row.innerHTML='<div>..</div><div><button>Open</button></div>';
      row.querySelector('button').onclick=()=>r_list(up.toString());
      el.appendChild(row);
    }
  }catch(e){}
  // Dirs
  for(const d of data.dirs){
    const row=document.createElement('div'); row.className='item';
    row.innerHTML='<div>📁 '+d+'</div><div><button>Open</button><button>Enqueue</button></div>';
    const [open,enq]=row.querySelectorAll('button');
    open.onclick=()=>r_list(ensureTrailingSlash(r_cwd)+d+'/');
    enq.onclick=()=>r_enqueueDir(ensureTrailingSlash(r_cwd)+d+'/');
    el.appendChild(row);
  }
  // Files
  for(const f of data.files){
    const row=document.createElement('div'); row.className='item';
    row.innerHTML='<div>🎵 '+f+'</div><div><button>Add</button></div>';
    row.querySelector('button').onclick=()=>r_enqueue(ensureTrailingSlash(r_cwd)+f);
    el.appendChild(row);
  }
}
async function r_enqueue(url){
  try{ await api('/enqueue_url',{method:'POST',body:JSON.stringify({url})}); toast('Queued remote file'); refreshState(); }
  catch(e){ toast(e.message,false); }
}
async function r_enqueueDir(url){
  const recursive=document.getElementById('r_recursive').checked;
  const shuffle=document.getElementById('r_shuffle').checked;
  try{ await api('/smb_enqueue_dir',{method:'POST',body:JSON.stringify({url,recursive,shuffle})}); toast('Queued remote folder'); refreshState(); }
  catch(e){ toast(e.message,false); }
}
document.getElementById('r_browse').onclick=()=>{
  const base=document.getElementById('r_base').value.trim();
  if(!base){ toast('Enter smb://… URL',false); return; }
  r_list(base);
};
document.getElementById('r_up').onclick=()=>{
  try{
    const u = new URL(r_cwd || document.getElementById('r_base').value.trim());
    const parts = u.pathname.split('/').filter(Boolean);
    if(parts.length>1){
      u.pathname = '/'+parts.slice(0,-1).join('/')+'/';
      r_list(u.toString());
    }
  }catch(e){}
};
document.getElementById('r_enqueue-all').onclick=()=>r_enqueueDir(r_cwd || document.getElementById('r_base').value.trim());

// ---------- URL enqueue ----------
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

// ---------- Playback ----------
for(const [id,svc] of [['play','play'],['skip','skip'],['stop','stop'],['clear','clear']]){
  document.getElementById(id).onclick=()=>api('/'+svc,{method:'POST'})
    .then(()=>{toast(svc+' ok'); refreshState();})
    .catch(e=>toast(e.message,false));
}

// ---------- BLE ----------
document.getElementById('status').onclick=()=>api('/status').then(s=>toast('BLE '+(s.connected?'connected':'disconnected'))).catch(e=>toast(e.message,false));
document.getElementById('connect').onclick=()=>api('/connect',{method:'POST'}).then(()=>toast('Connecting…')).catch(e=>toast(e.message,false));
document.getElementById('disconnect').onclick=()=>api('/disconnect',{method:'POST'}).then(()=>toast('Disconnected')).catch(e=>toast(e.message,false));
document.getElementById('pair').onclick=()=>api('/pair',{method:'POST'}).then(()=>toast('Pair attempt sent')).catch(e=>toast(e.message,false));

// ---------- Logs ----------
async function refreshLogs(){
  try{
    const r = await fetch('/api/skelly_queue/logs?format=text', {credentials:'same-origin'});
    const t = await r.text();
    const el=document.getElementById('logs'); el.textContent = t; el.scrollTop = el.scrollHeight;
  }catch(e){}
}
document.getElementById('refresh-logs').onclick=refreshLogs;

document.getElementById('pause-logs').onchange = (e)=>{
  paused = !!e.target.checked;
  if(paused && logTimer){ clearInterval(logTimer); logTimer = null; }
  if(!paused && !logTimer){ logTimer = setInterval(refreshLogs, 2000); }
};
document.getElementById('export-logs').onclick=()=>{ window.open('/api/skelly_queue/logs?download=1','_blank'); };

// init
list('');
refreshState();
refreshLogs();
logTimer = setInterval(refreshLogs, 2000);
</script>
</body></html>
"""
        html = html_start + TOAST + html_script
        return web.Response(text=html, content_type="text/html")


class SkellyApiView(HomeAssistantView):
    """JSON API used by the panel JS (public so iframe can call)."""
    url = "/api/skelly_queue/{op}"
    name = "skelly_queue:api"
    requires_auth = False

    def __init__(self, hass, data):
        self.hass = hass
        self.data = data

    # ---------- Helpers ----------
    def _ble(self):
        return self.data.get("ble")

    # ---------- GET ----------
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
            if not target.startswith(base):
                target = base; rel = ""
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
                text = "".join(lines)
            except Exception as ex:
                text = f"(log read error) {ex}"

            if request.query.get("format") == "text" and not request.query.get("download"):
                return web.Response(text=text, content_type="text/plain")
            if request.query.get("download"):
                headers = {"Content-Disposition": 'attachment; filename="skelly-logs.txt"'}
                return web.Response(text=text, content_type="text/plain", headers=headers)
            return self.json({"text": text})

        if op == "smb_list":
            # List a remote SMB directory
            from urllib.parse import urlparse, unquote
            try:
                from smb.SMBConnection import SMBConnection
            except Exception as ex:
                return web.Response(status=500, text=f"pysmb not available: {ex}")

            url = request.query.get("url", "")
            if not url.lower().startswith("smb://"):
                return web.Response(status=400, text="url must be smb://")

            u = urlparse(url)
            username = unquote(u.username or "")
            password = unquote(u.password or "")
            server = u.hostname
            share_and_path = [p for p in u.path.split("/") if p]
            if not server or not share_and_path:
                return web.Response(status=400, text="smb url must include host/share")

            share = share_and_path[0]
            sub = "/".join(share_and_path[1:])
            if sub and not sub.endswith("/"):
                sub += "/"

            conn = SMBConnection(username, password, "ha-skelly", server, use_ntlm_v2=True, is_direct_tcp=True)
            try:
                if not conn.connect(server, 445):
                    return web.Response(status=502, text="SMB connect failed")
                # Ensure we are listing a directory
                qpath = "/" + (sub or "")
                entries = conn.listPath(share, qpath)
                dirs, files = [], []
                for e in entries:
                    name = e.filename
                    if name in (".", ".."):
                        continue
                    if e.isDirectory:
                        dirs.append(name)
                    else:
                        files.append(name)
                dirs.sort(); files.sort()
                # Recompose clean url for client
                base = f"smb://{username}:{password}@{server}/{share}/" if username or password else f"smb://{server}/{share}/"
                full_url = base + (sub or "")
                return self.json({"url": full_url, "dirs": dirs, "files": files})
            except Exception as ex:
                return web.Response(status=500, text=str(ex))
            finally:
                try: conn.close()
                except Exception: pass

        return web.Response(status=404)

    # ---------- POST ----------
    async def post(self, request, op):
        body = await request.json() if request.can_read_body else {}

        if op == "enqueue":
            await self.hass.services.async_call("skelly_queue", "enqueue",
                {"filename": body.get("filename")}, blocking=True)
            return self.json({"ok":1})

        if op == "enqueue_dir":
            await self.hass.services.async_call("skelly_queue", "enqueue_dir",
                body, blocking=True)
            return self.json({"ok":1})

        if op == "enqueue_url":
            await self.hass.services.async_call("skelly_queue", "enqueue_url",
                {"url": body.get("url")}, blocking=True)
            return self.json({"ok":1})

        if op in ("play","skip","stop","clear"):
            await self.hass.services.async_call("skelly_queue", op, {}, blocking=True)
            return self.json({"ok":1})

        if op == "smb_enqueue_dir":
            # Recursively walk an SMB folder and enqueue each file via URL
            from urllib.parse import urlparse, unquote
            try:
                from smb.SMBConnection import SMBConnection
            except Exception as ex:
                return web.Response(status=500, text=f"pysmb not available: {ex}")

            url = body.get("url","")
            recursive = bool(body.get("recursive", True))
            shuffle = bool(body.get("shuffle", False))
            if not url.lower().startswith("smb://"):
                return web.Response(status=400, text="url must be smb://")

            u = urlparse(url)
            username = unquote(u.username or "")
            password = unquote(u.password or "")
            server = u.hostname
            parts = [p for p in u.path.split("/") if p]
            if not server or len(parts) < 1:
                return web.Response(status=400, text="smb url must include host/share")
            share = parts[0]
            start = "/".join(parts[1:])

            conn = SMBConnection(username, password, "ha-skelly", server, use_ntlm_v2=True, is_direct_tcp=True)
            added = 0
            try:
                if not conn.connect(server, 445):
                    return web.Response(status=502, text="SMB connect failed")

                def iter_dir(subpath):
                    qpath = "/" + (subpath or "")
                    try:
                        entries = conn.listPath(share, qpath)
                    except Exception:
                        return
                    dirs, files = [], []
                    for e in entries:
                        name = e.filename
                        if name in (".",".."): continue
                        if e.isDirectory: dirs.append(name)
                        else: files.append(name)
                    for f in sorted(files):
                        full_url = f"smb://{username}:{password}@{server}/{share}/" + (subpath + "/" if subpath else "") + f
                        yield full_url
                    if recursive:
                        for d in sorted(dirs):
                            new_sub = d if not subpath else f"{subpath}/{d}"
                            for item in iter_dir(new_sub):
                                yield item

                files_iter = list(iter_dir(start))
                if shuffle:
                    import random; random.shuffle(files_iter)
                for furl in files_iter:
                    await self.hass.services.async_call("skelly_queue", "enqueue_url",
                        {"url": furl}, blocking=True)
                    added += 1
                return self.json({"ok":1, "files": added})
            except Exception as ex:
                return web.Response(status=500, text=str(ex))
            finally:
                try: conn.close()
                except Exception: pass

        # BLE controls
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

