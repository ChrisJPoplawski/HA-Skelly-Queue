# 🦴 Skelly Queue (Home Assistant Integration)

**Automate your haunted show, queue your favorite spooky sounds, and control your Bluetooth-connected “Skelly” with ease — right from Home Assistant.**

Skelly Queue was *vibe-coded* in collaboration with the Home Assistant community, blending practical automation with a touch of Halloween magic.  
It lets you queue, schedule, and automate music or voice lines for your animatronic skeleton — whether you’re using a direct BLE connection or an ESP32 Bluetooth Proxy.

> 💬 “If you think you can improve it — please do! Pull requests, ideas, and spooky creativity are always welcome.”

---

## ✨ Features
- 🎶 **Queue audio files or playlists** — from local storage or remote URLs  
- 📂 **Built-in web file picker** in Home Assistant’s sidebar  
- 🔄 **BLE keep-alive** to prevent disconnects (works with or without proxies)  
- 🧠 **Preset system** for saving show sequences  
- ⚙️ **Simple setup wizard** with automatic UUID detection  
- 💾 **Cache management** with size limits  
- 🧰 **Full Home Assistant service support** for automations & scripts  

---

## ⚙️ Installation
### Via HACS
1. In HACS → **Integrations**, add this repository URL:  
   `https://github.com/ChrisJPoplawski/HA-Skelly-Queue`
2. Search for **Skelly Queue** and install.  
3. Restart Home Assistant.  

### Manual Install
1. Copy the folder `custom_components/skelly_queue` into your Home Assistant `/config/custom_components/` directory.  
2. Restart Home Assistant.  
3. Go to **Settings → Devices & Services → Add Integration → Skelly Queue**.  

---

## 🎛️ Configuration
All options are available through the UI:
- **Keep-alive toggle:** Enable or disable BLE heartbeat  
- **Media directory:** Where your audio files live  
- **Cache directory & limit:** For remote downloads and playlist entries  
- **Remote URLs:** Allow streaming or external links  

No YAML required — it’s all click-and-go.

---

## 🧩 Example Automations
Play all tracks in a folder:
```yaml
service: skelly_queue.enqueue_dir
data:
  subpath: "NightShow"
  shuffle: true
```

Start playback:
```yaml
service: skelly_queue.play
```

---

## 🙏 Acknowledgements
Special thanks to **[tinkertim’s BLE Skelly repo](https://github.com/tinkertims/tinkertims.github.io)** for pioneering the original skeleton-control framework that made this possible.

> *Vibe-coded in collaboration with ChatGPT (Astra) and the Home Assistant community — built with a lot of coffee and Halloween spirit.*

---

## ⚖️ License
MIT License © 2025 Chris Poplawski  
Free to fork, improve, remix, and share — just give credit where it’s due.
