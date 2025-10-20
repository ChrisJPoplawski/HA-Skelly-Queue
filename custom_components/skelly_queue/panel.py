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
.row{display:grid;grid-template-columns:1fr 1fr;gap:8px;width:100%}
input,select,textarea{background:#111114;border:1px solid #2b2b32;color:#e7e7ea;border-radius:10px;padding:6px 8px;width:100%}
button.primary{background:#4f46e5}
small{opacity:.7}
pre{white-space:pre-wrap;word-break:break-word;}
.toggle{display:inline-flex;align-items:center;gap:6px}
label.small{font-size:12px;opacity:.85}
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
      <label class="small"><input type="checkbox" id="recursive" checked/> recursive</label>
      <label class="small"><input type="checkbox" id="shuffle"/> shuffle</label>
    </div>
    <div class="list" id="list"></div>
    <p><small>Media root: <code id="root"></code></small></p>
  </section>

  <!-- Remote SMB Library (component inputs) -->
  <section class="card">
    <h3>Remote SMB library</h3>
    <div class="row">
      <input id="r_host" placeholder="Host (e.g. 192.168.1.50 or nas.local)"/>
      <input id="r_share" placeholder="Share (e.g. Media)"/>
      <input id="r_path" placeholder="Path in share (e.g. Audio/Skelly)"/>
      <input id="r_port" placeholder="Port (default 445)"/>
      <input id="r_user" placeholder="Username (optional)"/>
      <input id="r_pass" placeholder="Password (optional)" type="password"/>
    </div>
    <div class="bar" style="margin-top:8px">
      <button id="r_browse" class="primary">Browse</button>
      <button id="r_up">⬆️ Up</button>
      <button id="r_enqueue-all">Enqueue Folder</button>
      <label class="small"><input type="checkbox" id="r_recursive" checked/> recursive</label>
      <label class="small"><input type="checkbox" id="r_shuffle"/> shuffle</label>
    </div>
    <div class="list" id="r_list"></div>
    <p><small id="r_status"></small></p>
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
const f = id => document.getElementById(id);
let r_cwd = '';   // current folder composed from fields

function ensureSlashEnd(s){ return !s ? "" : (s.endsWith('/') ? s : s + '/'); }
function composePath(){
  let p = (f('r_path').value || '').trim().replace(/^\\/+/, '').replace(/\\/+$/, '');
  return p;
}
function buildUrlForFile(filename){
  const host = (f('r_host').value||'').trim();
  const share = (f('r_share').value||'').trim();
  const path = composePath();
  const user = (f('r_user').value||'').trim();
  const pass = (f('r_pass').value||'').trim();
  const auth = user ? (pass ? `${encodeURIComponent(user)}:${encodeURIComponent(pass)}@` : `${encodeURIComponent(user)}@`) : '';
  const base = `smb://${auth}${host}/${share}/`;
  const sub = path ? ensureSlashEnd(path) : '';
  return base + sub + filename;
}
function components(){  // JSON we send to backend (no URL in query)
  const port = parseInt((f('r_port').value||'').trim()||'445',10);
  return {
    host: (f('r_host').value||'').trim(),
    share: (f('r_share').value||'').trim(),
    path: composePath(),
    username: (f('r_user').value||'').trim(),
    password: (f('r_pass').value||'').trim(),
    port: isNaN(port)?445:port
  };
}
async function r_list_from_fields(){
  const body = components();
  if(!body.host || !body.share){ toast('Host and Share are required', false); return; }
  const data = await api('/smb_list', {method:'POST', body: JSON.stringify(body)});
  // display current folder (without password)
  const disp = `smb://${body.username?encodeURIComponent(body.username)+'@':''}${body.host}/${body.share}/${body.path?ensureSlashEnd(body.path):''}`;
  f('r_status').textContent = disp;
  r_cwd = disp;
  const el=f('r_list'); el.innerHTML='';
  // Up
  const parts = (body.path||'').split('/').filter(Boolean);
  if(parts.length>0){
    const upParts = parts.slice(0,-1).join('/');
    f('r_path').value = upParts;
    const row=document.createElement('div'); row.className='item';
    row.innerHTML='<div>..</div><div><button>Open</button></div>';
    row.querySelector('button').onclick=()=>{
      f('r_path').value = upParts;
      r_list_from_fields();
    };
    el.appendChild(row);
  }
  // Dirs
  for(const d of data.dirs){
    const row=document.createElement('div'); row.className='item';
    row.innerHTML='<div>📁 '+d+'</div><div><button>Open</button><button>Enqueue</button></div>';
    const [open,enq]=row.querySelectorAll('button');
    open.onclick=()=>{ f('r_path').value = ensureSlashEnd(composePath()) + d; r_list_from_fields(); };
    enq.onclick=()=>r_enqueueDir_from_fields(ensureSlashEnd(composePath()) + d);
    el.appendChild(row);
  }
  // Files
  for(const name of data.files){
    const row=document.createElement('div'); row.className='item';
    row.innerHTML='<div>🎵 '+name+'</div><div><button>Add</button></div>';
    row.querySelector('button').onclick=()=>r_enqueue_file(name);
    el.appendChild(row);
  }
}
async function r_enqueue_file(filename){
  try{
    const url = buildUrlForFile(filename); // enqueue_url expects smb://…
    await api('/enqueue_url',{method:'POST',body:JSON.stringify({url})});
    toast('Queued remote file'); refreshState();
  }catch(e){ toast(e.message,false); }
}
async function r_enqueueDir_from_fields(subpath){
  const body = components();
  body.subpath = (subpath||'').replace(/^\\/+/, '');
  body.recursive = f('r_recursive').checked;
  body.shuffle = f('r_shuffle').checked;
  try{
    await api('/smb_enqueue_dir',{method:'POST',body:JSON.stringify(body)});
    toast('Queued remote folder'); refreshState();
  }catch(e){ toast(e.message,false); }
}
f('r_browse').onclick = r_list_from_fields;
f('r_up').onclick = ()=>{
  const parts = (composePath()||'').split('/').filter(Boolean);
  if(parts.length>0){ f('r_path').value = parts.slice(0,-1).join('/'); r_list_from_fields(); }
};
f('r_enqueue-all').onclick = ()=>r_enqueueDir_from_fields(composePath());

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
list('');
refreshState();
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
    """JSON API used by the panel JS (public so iframe can call)."""
    url = "/api/skelly_queue/{op}"
    name = "skelly_queue:api"
    requires_auth = False

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
            if not target.startswith(base):
                target = base; rel = ""
            try:
                names = await _executor(self.hass, os.listdir, target)
            except Exception:
                names = []
            dirs, files = [], []
            for name in names:
                if name.startswith("."): 
                    continue
                p = os.path.join(target, name)
                try:
                    isdir = await _executor(self.hass, os.path.isdir, p)
                except Exception:
                    isdir = False
                (dirs if isdir else files).append(name)
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
            only = (request.query.get("only") or "skelly").lower()

            addr = (self.data.get("address") or "").replace(":", "_")
            mac_raw = self.data.get("address") or ""
            patterns = [
                "custom_components.skelly_queue",
                "skelly_queue",
                "skelly_ble",
                "Skelly Queue",
            ]
            if addr: patterns.append(addr)
            if mac_raw: patterns.append(mac_raw)

            def _read_tail_filtered():
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()[-1200:]
                    if only == "skelly":
                        inc = []
                        for ln in lines:
                            L = ln.lower()
                            if any(p.lower() in L for p in patterns):
                                inc.append(ln)
                        return "".join(inc) if inc else "(no Skelly Queue log lines in tail)"
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

        return web.Response(status=404)

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

        if op == "smb_list":
            # Components-based list (no password in URL)
            try:
                from smb.SMBConnection import SMBConnection
            except Exception as ex:
                return web.Response(status=500, text=f"pysmb not available: {ex}")

            host = (body.get("host") or "").strip()
            share = (body.get("share") or "").strip()
            sub = (body.get("path") or "").strip().strip("/")
            username = body.get("username") or ""
            password = body.get("password") or ""
            port = int(body.get("port") or 445)

            if not host or not share:
                return web.Response(status=400, text="host and share required")

            def _list_dir():
                conn = SMBConnection(username, password, "ha-skelly", host, use_ntlm_v2=True, is_direct_tcp=True)
                try:
                    if not conn.connect(host, port):
                        raise RuntimeError("SMB connect failed")
                    qpath = "/" + (sub + "/" if sub else "")
                    entries = conn.listPath(share, qpath)
                    dirs, files = [], []
                    for e in entries:
                        name = e.filename
                        if name in (".", ".."):
                            continue
                        (dirs if e.isDirectory else files).append(name)
                    dirs.sort(); files.sort()
                    display_url = f"smb://{(username+'@') if username else ''}{host}/{share}/" + (sub + "/" if sub else "")
                    return {"url": display_url, "dirs": dirs, "files": files}
                finally:
                    try: conn.close()
                    except Exception: pass

            try:
                result = await _executor(self.hass, _list_dir)
                return self.json(result)
            except Exception as ex:
                return web.Response(status=500, text=str(ex))

        if op == "smb_enqueue_dir":
            # Enqueue folder by components OR by legacy url
            try:
                from smb.SMBConnection import SMBConnection
            except Exception as ex:
                return web.Response(status=500, text=f"pysmb not available: {ex}")

            url = body.get("url")
            recursive = bool(body.get("recursive", True))
            shuffle = bool(body.get("shuffle", False))

            if url and url.lower().startswith("smb://"):
                # legacy path already supported in previous versions
                from urllib.parse import urlparse, unquote
                u = urlparse(url)
                username = unquote(u.username or "")
                password = unquote(u.password or "")
                host = u.hostname
                parts = [p for p in u.path.split("/") if p]
                if not host or len(parts) < 1:
                    return web.Response(status=400, text="smb url must include host/share")
                share = parts[0]
                sub = "/".join(parts[1:])
                port = 445
            else:
                host = (body.get("host") or "").strip()
                share = (body.get("share") or "").strip()
                sub = (body.get("subpath") or body.get("path") or "").strip().strip("/")
                username = body.get("username") or ""
                password = body.get("password") or ""
                port = int(body.get("port") or 445)
                if not host or not share:
                    return web.Response(status=400, text="host and share required")

            def _walk_remote():
                conn = SMBConnection(username, password, "ha-skelly", host, use_ntlm_v2=True, is_direct_tcp=True)
                try:
                    if not conn.connect(host, port):
                        raise RuntimeError("SMB connect failed")

                    def iter_dir(subpath):
                        qpath = "/" + (subpath + "/" if subpath else "")
                        try:
                            entries = conn.listPath(share, qpath)
                        except Exception:
                            return
                        dirs, files = [], []
                        for e in entries:
                            name = e.filename
                            if name in (".",".."): continue
                            (dirs if e.isDirectory else files).append(name)
                        for f in sorted(files):
                            auth = f"{username}:{password}@" if username or password else ""
                            base = f"smb://{auth}{host}/{share}/"
                            yield base + (subpath + "/" if subpath else "") + f
                        if recursive:
                            for d in sorted(dirs):
                                new_sub = d if not subpath else f"{subpath}/{d}"
                                for item in iter_dir(new_sub):
                                    yield item
                    items = list(iter_dir(sub))
                    if shuffle:
                        import random; random.shuffle(items)
                    return items
                finally:
                    try: conn.close()
                    except Exception: pass

            try:
                files_iter = await _executor(self.hass, _walk_remote)
                added = 0
                for furl in files_iter or []:
                    await self.hass.services.async_call("skelly_queue", "enqueue_url", {"url": furl}, blocking=True)
                    added += 1
                return self.json({"ok":1, "files": added})
            except Exception as ex:
                return web.Response(status=500, text=str(ex))

        # BLE in background
        ble = self._ble()
        if op == "connect":
            if ble: self.hass.loop.create_task(ble._ensure_client())
            return self.json({"ok":1})
        if op == "disconnect":
            if ble: self.hass.loop.create_task(ble.disconnect())
            return self.json({"ok":1})
        if op == "pair":
            if ble:
                async def _pair():
                    try:
                        if ble._client:
                            await ble._client.pair()
                        else:
                            await ble._ensure_client()
                            if ble._client:
                                await ble._client.pair()
                    except Exception:
                        pass
                self.hass.loop.create_task(_pair())
            return self.json({"ok":1})

        return web.Response(status=404)

