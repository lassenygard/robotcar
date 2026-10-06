# Installasjon og kalibrering

## Forutsetninger

Maskinene kjører Raspberry Pi OS Bookworm, Python 3.11 og Linux 6.12.
Bruk systemets Python og Picamera2/libcamera/Hailo-pakker. Ikke erstatt NumPy
eller kamera-/Hailo-bibliotekene med tilfeldige pip-versjoner: de inneholder
native koblinger til den installerte driveren.

Pi 4 trenger `python3-gpiozero`, `python3-rpi.gpio`, `python3-serial` og
`python3-aiohttp`. Pi 5 trenger
`python3-picamera2`, `python3-opencv`, `python3-numpy`, `python3-scipy`,
`python3-serial`, `python3-aiohttp` og den fungerende HailoRT-installasjonen.
Det målte Hailo-8-oppsettet bruker firmware/runtime 4.20.0.

## Privat konfigurasjon

`deploy/robotcar.env.example` dokumenterer feltene. Kopier til
`/etc/robotcar/robotcar.env`, eid av root, modus 600. Samme tilfeldige
`ROBOTCAR_TOKEN` skal brukes på begge Pi-er. Bruk minst 24 tilfeldige tegn.
Den er ikke et SSH-passord og skal ikke sendes til nettleseren.

`WEB_PASSWORD_HASH` er `salt_hex:hash_hex`, der hash er
PBKDF2-HMAC-SHA256 med 200 000 iterasjoner. Det aktive webpassordet finnes bare
på den lokale arbeidsmaskinen; serveren lagrer hash. Ikke legg passord eller
det private miljøoppsettet i GitHub.

Pi 5 bruker modellen
`/var/lib/robotcar/models/yolov5m_wo_spp_60p.hef` og tilhørende COCO-etiketter.
Den eksisterende modellen er gjenbrukt, ikke lastet ned på nytt:

```
SHA256 c07e0e68c93d377cac2f1e60bdde28fb01ae7d27c93e2d0dfe9afb5f33e3bdf8
```

## Installer

Kjør `sudo bash deploy/install.sh motor` på Pi 4 og
`sudo bash deploy/install.sh sensors` på Pi 5 etter at den private
konfigurasjonen er opprettet. Skriptet kopierer kun runtime og servicefiler,
og overskriver ikke private miljøfiler, modeller eller kart.

LiDAR-ens USB-kabel skal nå stå i Pi 4. Sett disse feltene i den private
konfigurasjonen på Pi 4 før installasjon:

```ini
LIDAR_FEED_ENABLED=1
LIDAR_FEED_BIND=192.168.4.43
LIDAR_FEED_PORT=8801
LIDAR_OFFSET_DEG=-105
```

Pi 4 skal ikke ha `LIDAR_REMOTE_URL`. På Pi 5 settes
`LIDAR_REMOTE_URL=http://192.168.4.43:8801` og `LIDAR_FEED_ENABLED=0`.
Samme interne token brukes på begge. Motorinstallasjonen starter også
`robotcar@lidar` og `robotcar@lidarfeed` når feed-flagget er 1.
Kartbehandlingen forblir på Pi 5; Pi 4 gjør bare innlesing og videresending.

Etter strømbruddet 2026-10-06 inneholdt den gamle Pi 5-installasjonen tomme filer
og nullbytes. Oppdateringer legges derfor nå i en ny mappe under
`/opt/robotcar/releases`. Alle filer kontrolleres med SHA-256 og skrives til
lagringsmediet før `current` peker til den nye versjonen i én atomisk operasjon.
Tjenestene kjører fra `/opt/robotcar/current`; tidligere versjoner beholdes.
Dette reduserer risikoen for en halvskrevet oppdatering, men erstatter ikke
stabil strømforsyning eller beskyttelse mot feil i selve lagringsmediet.

```bash
systemctl status robotcar-motor                 # Pi 4
systemctl status 'robotcar@*'                   # Pi 5
journalctl -u robotcar-motor -n 30 --no-pager
journalctl -u robotcar@lidar -n 30 --no-pager
# Kontroller installerte filer uten å starte maskinvaren:
python3 /opt/robotcar/current/deploy/release.py verify /opt/robotcar/current
cd /opt/robotcar/current
python3 -m unittest discover -s tests -v
```

## GPIO og mekanikk

**Gjeldende driftsform:** motorene er sperret mens bilen står i strømkabler.
`/etc/robotcar/motors-inhibited` hindrer at `robotcar-motor.service` starter,
også ved omstart eller ny installasjon. Pi 4 har i tillegg en tilsvarende
systemd-drop-in fra overgangen til vanlig strøm. Sperren skal stå til brukeren
bekrefter at bilen er løs fra kablene og klar for nye fysiske prøver.

Utgangene er BCM-numre fra de tidligere skriptene:

| Gammelt navn | Fram | Bak | Enable |
|---|---:|---:|---:|
| front_left | 24 | 27 | 5 |
| front_right | 6 | 22 | 17 |
| rear_left | 23 | 16 | 12 |
| rear_right | 18 | 13 | 25 |

Testene viste at disse sidenavnene ikke stemte med bilens faktiske framretning.
Det aktive oppsettet har `MOTOR_SWAP_SIDES=1` og negativ polaritet på de to
utgangene med det gamle navnet `*_right`. Fronten er kameraet som ser de svarte
kjøkkenskapene. Sidelengs/mecanum-kommandoer finnes ikke i det nye grensesnittet.

Begge kameraretninger er undersøkt. Front er imx219, kamera 0; bak er
imx708_wide, kamera 1, rotert 180 grader i programvaren. Sensorene bruker hele
synsfeltet via 1640×1232 og 2304×1296 før nedskalering til 640×480.

## Før autonom kjøring

1. Kontroller LiDAR-strøm, USB-/UART-kabel og tilkoblingen til skannerhodet.
   Adapteren alene bekrefter ikke at selve sensoren har strøm.
2. Bekreft faktiske skanninger, oppdateringsfrekvens og avstander mot målte
   avstander i rommet. Offset −105 grader er arvet fra gammel kode og ennå
   ikke verifisert. Kontroller også fortegn og eventuell fast selvskygge fra
   batteri/chassis. Ikke filtrer bort ukjente, nære hindringer for å få kjøring.
3. Gjenta korte frem/bak-/rotasjonstester med person ved bilen. Kalibrer eventuell
   sideforskjell og sikkerhetsradius. Bekreft at en hindring stopper bevegelse.
4. Bygg et lite kart under oppsyn, lagre det, stopp tjenesten og last kartet
   på nytt. Kontroller gjenlokalisering flere steder og begge rotasjonsretninger.
5. Først etter brukerens bekreftelse på at vedkommende er hjemme og fysisk
   validering: sett `MOTION_CALIBRATED=1` og `AUTONOMY_ENABLED=1` på Pi 5,
   og `AUTONOMY_ENABLED=1` på Pi 4. Start tjenestene på nytt.

Disse flaggene skal ikke automatisk endres av nettleseren. Motorenes 2,5-sekunders
grense blir stående; navigasjon bruker korte pulser med reell pause imellom.
Enkelte maskinvarefeil, f.eks. en helt låst prosessor eller defekt motordriver,
kan ikke avverges av en programvarestopp. Et eget fysisk nødstoppsystem er ikke
montert eller verifisert av denne endringen.

## LiDAR-diagnose som allerede er gjort

Porten er CP2102, USB-ID `10c4:ea60`, stabil sti
`/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`.
På batteri ga seriell lesing, installert Adafruit RPLidar 0.0.1, nyere
Adafruit-kilde og [SLAMTECs SDK](https://github.com/Slamtec/rplidar_sdk)
ingen stabile svar. 115200, 256000 og 460800 baud, DTR begge veier, reset,
USB-omstart og redusert kamera/AI-last ble forsøkt uten brukbare skanninger.

På vanlig strømforsyning ble Pi 5 målt til ca. 5,00 V og `throttled=0x0`.
Seriell lesing var fortsatt ustabil. Direkte USB-lesing uten cp210x-driveren
ga normal helsestatus og 12 105 gyldige returer over 98 komplette omdreininger.
Etter flytting av samme USB-kabel til Pi 4 fungerte vanlig 115200-baud-lesing:
normal helsestatus, 11 880 returer og 97 komplette omdreininger på 15 sekunder.
Produksjonsleseren kjører derfor på Pi 4 med vanlig SCAN og obligatorisk
helsekontroll. Den direkte USB-prøven er ikke en avhengighet i driften.

Pi 5 viste gjentatt `cp210x ... failed set request 0x12 status: -110`.
Forespørsel 0x12 er tømming av UART-buffer ved lukking av porten. Dette er
ikke i seg selv bevis på at alle USB-innstillinger eller adapteren er ødelagt.
Tilsvarende feil er ikke observert på Pi 4 etter flyttingen. Den nøyaktige
årsaken i Pi 5-forbindelsen er ikke fastslått.

`scripts/probe_lidar.py` tester bare serieporten og LiDAR-ens egen rotasjon;
det importerer ikke hjulstyringen. Stopp `robotcar@lidar` før bruk og start
tjenesten igjen etterpå. Eksempel fra repoets rot:

```bash
python3 scripts/probe_lidar.py --command health --seconds 3
python3 scripts/probe_lidar.py --command scan --seconds 15
```

`--command force-scan` er kun diagnostikk. En skannedeskriptor eller pakker
med null avstand regnes ikke som brukbare omdreininger. Eventuelle råopptak
med `--save-raw` skal lagres privat utenfor repoet.

## Batteritid og vanlig strøm

Ingen batterimåler for Bosch-batteriet er funnet. Pi 5 sin EXT5V-verdi er
5 V-forsyningen, og BATT_V gjelder RTC; ingen av dem gir batteriets ladetilstand.
Den tidligere femtimersfristen ble deaktivert på begge Pi-er før overgang
til vanlig strøm. Begge skal derfor forbli på nå.

`sudo bash deploy/schedule-shutdown.sh '<felles UTC-frist>'` kan sette en ny
engangsfrist på begge maskiner ved senere batteridrift. Bruk samme frist på
begge. Timeren er vedvarende: omstart etter fristen gir avslåing hvis timeren
fortsatt er aktiv. På vanlig strøm deaktiveres den med
`sudo systemctl disable --now robotcar-battery-shutdown.timer`.

På batteriforsyningen ble ca. 4,72–4,80 V og undervoltingsvarsler målt, også
etter lading. Batteriets spenningsomformer og kabler må utbedres/kontrolleres
under last før dette kan brukes som stabil mobil strømforsyning.
