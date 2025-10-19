# Skelly Queue (Home Assistant Custom Integration)

A tiny Home Assistant integration that adds a **music/voice queue** for your Skelly while using **Home Assistant’s own Bluetooth** (shared Bleak backend). No add-on, no extra init systems—just services to enqueue and control playback.

- Queue audio files from your local media folder (`/media/skelly`) **or** from remote URLs / M3U playlists (downloaded to a cache).
- Services: `enqueue`, `enqueue_url`, `enqueue_m3u`, `play`, `skip`, `stop`, `clear`.
- Compatible with tinkertims’ Web Bluetooth controller (this does **not** replace it).

## Installation

### Via HACS (Custom Repository)
1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add your repo URL (after you publish it): `https://github.com/<your-account>/ha-skelly-queue`, Category **Integration**.
3. Search for **Skelly Queue (Simple)** and install.
4. **Restart Home Assistant**.

### Manual
- Copy `custom_components/skelly_queue` into `/config/custom_components/skelly_queue/` and **restart**.

## Configuration

Add this to your `configuration.yaml`:
```yaml
skelly_queue:
  address: "AA:BB:CC:DD:EE:FF"                # Skelly BLE MAC
  play_char: "0000abcd-0000-1000-8000-00805f9b34fb"  # Replace with real UUID
  cmd_char:  "0000abce-0000-1000-8000-00805f9b34fb"  # (optional) STOP/NEXT
  media_dir: "/media/skelly"
  allow_remote_urls: true
  cache_dir: "/media/skelly/cache"
  max_cache_mb: 500
```

Create the media folder and upload audio:
- **Settings → Media** → create folder `skelly`, upload `*.mp3` / `*.wav`.

## Services

- `skelly_queue.enqueue`
  ```yaml
  filename: "boo_01.mp3"
  ```
- `skelly_queue.enqueue_url`
  ```yaml
  url: "https://example.com/sounds/boo_01.mp3"
  ```
- `skelly_queue.enqueue_m3u`
  ```yaml
  url: "https://example.com/halloween_playlist.m3u8"
  ```
- `skelly_queue.play` — start/resume queue
- `skelly_queue.skip` — skip current (sends `NEXT` if `cmd_char` set) and pop
- `skelly_queue.stop` — stop and clear (sends `STOP` if `cmd_char` set)
- `skelly_queue.clear` — clear queue

## Example Dashboard Buttons

```yaml
type: horizontal-stack
cards:
  - type: button
    name: Play
    tap_action: { action: call-service, service: skelly_queue.play }
  - type: button
    name: Skip
    tap_action: { action: call-service, service: skelly_queue.skip }
  - type: button
    name: Stop
    tap_action: { action: call-service, service: skelly_queue.stop }
  - type: button
    name: Clear
    tap_action: { action: call-service, service: skelly_queue.clear }
```

## Notes
- Make sure **Bluetooth** is working in HA and your Skelly is reachable.
- If your device sends a **notify** when a track ends, you can replace the naive 10s sleep with a proper GATT notify handler for precise transitions.
- **Payload format**: by default we send `b"PLAY:<filename>"`. If your Skelly needs a different format, edit `_send_play_command()` in `__init__.py`.
- **Remote URLs** are cached to `cache_dir` and evicted when exceeding `max_cache_mb` (oldest-first).
