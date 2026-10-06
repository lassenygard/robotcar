# RPi3 Motor Controller Service

Denne mappen inneholder koden som kjøres på RPi3 for motorstyring.

## Oppsett

### 1. Kopier filene til RPi3
```bash
scp -r RPi3/* pi@<rpi3-ip>:~/motor_controller/
```

### 2. Installer avhengigheter på RPi3
```bash
ssh pi@<rpi3-ip>
cd ~/motor_controller
pip install -r requirements.txt
```

### 3. Konfigurer IP-adresse
Rediger `config.py` og sett riktig IP/port hvis nødvendig.

### 4. Start tjenesten
```bash
python motor_service.py
```

### 5. (Valgfritt) Kjør ved oppstart
```bash
sudo cp motorcontroller.service /etc/systemd/system/
sudo systemctl enable motorcontroller
sudo systemctl start motorcontroller
```

## Kommunikasjonsprotokoll

RPi3 lytter på TCP port 5001 og mottar JSON-kommandoer:

```json
{"command": "move_forward", "speed": 0.5}
{"command": "stop"}
{"command": "set_speed", "speed": 0.7}
{"command": "status"}
```

Svar:
```json
{"status": "ok", "movement": "forward", "speed": 0.5}
{"status": "error", "message": "Unknown command"}
```

## GPIO Pin-konfigurasjon

| Motor | Forward | Backward | Enable |
|-------|---------|----------|--------|
| Front Left | 24 | 27 | 5 |
| Front Right | 6 | 22 | 17 |
| Rear Left | 23 | 16 | 12 |
| Rear Right | 18 | 13 | 25 |

## Feilsøking

### Sjekk at tjenesten kjører:
```bash
sudo systemctl status motorcontroller
```

### Se logger:
```bash
journalctl -u motorcontroller -f
```

### Test manuelt:
```bash
python -c "from motor_controller import MecanumWheels; w = MecanumWheels(); w.move_forward(); import time; time.sleep(1); w.stop()"
```
