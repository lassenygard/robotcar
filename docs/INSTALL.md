# Installasjon og kalibrering

## Forutsetninger

Maskinene kjører Raspberry Pi OS Bookworm, Python 3.11 og Linux 6.12.
Bruk systemets Python og Picamera2/libcamera/Hailo-pakker. Ikke erstatt NumPy
eller kamera-/Hailo-bibliotekene med tilfeldige pip-versjoner: de inneholder
native koblinger til den installerte driveren.

Pi 4 trenger `python3-gpiozero` og `python3-rpi.gpio`. Pi 5 trenger
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
GET_INFO er forsøkt ved 115200, 256000 og 460800 baud. Reset er forsøkt ved
115200/256000 og GET_HEALTH ved 115200. DTR er testet begge veier, og
USB-adapteren er tilbakestilt. Alle forsøk ga null
mottatte bytes. Ingen annen prosess eide porten ved diagnostikken. Det er ennå
ikke grunnlag for å kalle romskanning eller avstandsmåling fungerende.
En ekstra kontroll med begge kameraer og AI stanset, redusert strømforbruk og
tre sekunders motoroppstart ga også null bytes fra INFO/HEALTH ved 115200 baud.
