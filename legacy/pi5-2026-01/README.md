# Robot Control System v2.0

## Dual Raspberry Pi Architecture

Dette prosjektet bruker en to-Pi arkitektur for optimal ytelse:

```
┌─────────────────────────────────────────────────────────────┐
│                      RPi5 (MASTER)                          │
│  • Webserver (Flask + Socket.IO)                           │
│  • Dual kameraer (foran/bak)                               │
│  • LIDAR-kartlegging                                       │
│  • AI objektdeteksjon (Hailo-8)                            │
│  • Navigasjonslogikk                                       │
└─────────────────────────┬───────────────────────────────────┘
                          │ WiFi (TCP port 5001)
                          │ JSON-kommandoer
┌─────────────────────────┴───────────────────────────────────┐
│                      RPi3 (SLAVE)                           │
│  • Motor Controller Service                                │
│  • GPIO-styring av 4x Mecanum-hjul                        │
│  • Lav-latens motorstyring                                │
└─────────────────────────────────────────────────────────────┘
```

## Hurtigstart

### 1. Sett opp RPi3 (Motor Controller)

```bash
# Kopier RPi3-mappen til Raspberry Pi 3
scp -r RPi3/* pi@<rpi3-ip>:~/motor_controller/

# SSH inn på RPi3
ssh pi@<rpi3-ip>

# Installer avhengigheter
cd ~/motor_controller
pip install -r requirements.txt

# Start motor service
python motor_service.py
```

### 2. Konfigurer RPi5

Rediger `config.py` og sett RPi3 sin IP-adresse:

```python
RPI3_HOST = '192.168.1.101'  # ← Din RPi3 IP
RPI3_PORT = 5001
```

### 3. Start RPi5 (Master)

```bash
cd "Functioning robotcar"
python main.py
```

### 4. Åpne kontrollpanelet

Gå til `http://<rpi5-ip>:5000` i nettleseren.

---

## Funksjoner

### Kontrollpanel (Web UI)
- **Manuell styring**: WASD + piltaster
- **Hastighetskontroll**: 0-100%
- **Dual kamera**: Bytt mellom foran/bak
- **RPi3-status**: Se om motorstyringen er tilkoblet

### LIDAR-visualisering
- 360° sanntids skannevisning
- Fargekoding (rød/oransje/grønn)
- Justerbar safe distance og LIDAR offset

### Autonom navigasjon
| Modus | Beskrivelse |
|-------|-------------|
| **Explore** | Enkel hindringsunngåelse |
| **Wall Follow** | Følger vegger med høyre side |
| **Map Room** | Systematisk kartlegging |

### AI Objektdeteksjon
- YOLOv5 via Hailo-8 akselerator
- Sanntids deteksjon av 80+ objektklasser

---

## Filstruktur

```
Functioning robotcar/
├── main.py                 # Hovedskript RPi5
├── config.py               # Konfigurasjon (RPi3 IP, etc.)
├── utils.py                # Hailo AI-inferens
├── yolov5m_wo_spp_60p.hef # YOLOv5 modell
├── coco.txt               # Objektklasser
│
├── src/
│   ├── motor/
│   │   ├── motor_controller.py  # Motor manager (remote/local)
│   │   └── motor_client.py      # TCP klient til RPi3
│   ├── visionmapping/
│   │   ├── vision_combined.py   # AI objektdeteksjon
│   │   └── lidar_mapping.py     # LIDAR + GridMap
│   └── web/
│       ├── server.py            # Flask webserver
│       ├── templates/index.html # Kontrollpanel UI
│       └── static/
│           ├── css/style.css    # Industrial design
│           └── js/controls.js   # Frontend logikk
│
└── RPi3/                   # ← Kopier til Raspberry Pi 3
    ├── motor_service.py    # TCP-server for motorkommandoer
    ├── motor_controller.py # GPIO motorstyring
    ├── config.py           # RPi3 konfigurasjon
    ├── requirements.txt    # Python avhengigheter
    ├── test_client.py      # Test-verktøy
    └── motorcontroller.service  # Systemd service
```

---

## Kommunikasjonsprotokoll (RPi5 ↔ RPi3)

RPi3 lytter på TCP port 5001 og mottar JSON-kommandoer:

```json
{"command": "move_forward", "speed": 0.5}
{"command": "rotate_clockwise", "speed": 0.3}
{"command": "stop"}
{"command": "status"}
{"command": "ping"}
```

Svar:
```json
{"status": "ok", "movement": "forward", "speed": 0.5}
{"status": "error", "message": "Unknown command"}
```

---

## GPIO Pin-konfigurasjon (RPi3)

| Motor | Forward | Backward | Enable |
|-------|---------|----------|--------|
| Front Left | 24 | 27 | 5 |
| Front Right | 6 | 22 | 17 |
| Rear Left | 23 | 16 | 12 |
| Rear Right | 18 | 13 | 25 |

---

## Kjøre ved oppstart

### RPi3 - Motor Service

```bash
# Kopier service-fil
sudo cp ~/motor_controller/motorcontroller.service /etc/systemd/system/

# Aktiver og start
sudo systemctl enable motorcontroller
sudo systemctl start motorcontroller

# Sjekk status
sudo systemctl status motorcontroller
```

### RPi5 - Webserver

Lag en lignende systemd service eller legg til i `/etc/rc.local`.

---

## Feilsøking

### RPi3 mottar ikke kommandoer

1. Sjekk at motor_service.py kjører:
   ```bash
   sudo systemctl status motorcontroller
   ```

2. Sjekk nettverkstilkobling:
   ```bash
   ping <rpi3-ip>
   ```

3. Test med test_client.py:
   ```bash
   python RPi3/test_client.py <rpi3-ip>
   ```

### LIDAR fungerer ikke

1. Sjekk USB-tilkobling:
   ```bash
   ls /dev/ttyUSB*
   ```

2. Sjekk tillatelser:
   ```bash
   sudo chmod 666 /dev/ttyUSB0
   ```

### Kamera viser ikke bilde

1. Sjekk at kamera er aktivert:
   ```bash
   vcgencmd get_camera
   ```

2. Test med libcamera:
   ```bash
   libcamera-hello
   ```

---

## Avhengigheter

### RPi5 (requirements.txt)
```
flask
flask-socketio
opencv-python
numpy
pillow
picamera2
adafruit-rplidar
supervision
loguru
hailo_platform
```

### RPi3 (RPi3/requirements.txt)
```
gpiozero
RPi.GPIO
```

---

## Neste steg / Ideer

1. **Encodere**: Legg til hjulenkodere for odometri
2. **SLAM**: Implementer Simple SLAM
3. **Målnavigasjon**: Klikk på kart for destinasjon
4. **Stemmekommandoer**: Integrer talegjenkjenning
5. **Batteri-monitor**: Vis batteristatus i UI
