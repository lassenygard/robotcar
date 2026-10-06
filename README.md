# Robotcar — to Raspberry Pi-er

Robotcar har et innlogget kontrollpanel med to kameravisninger, rask manuell
styring, kartvisning og navigasjonskontroller. Motorstyring kjører isolert på
Pi 4; kameraer, Hailo-8, LiDAR og kartlegging kjører på Pi 5.

**Status 2026-10-06:** kameraer og korte motorkommandoer er testet på bilen.
LiDAR-adapteren finnes, men sensoren svarer ikke. Full kartlegging, lokalisering
og autonome turer er derfor **ikke fysisk godkjent**. De er implementert, testet
med syntetiske data og sperret fra å kjøre før sensorer og kalibrering er i orden.

## Bruk

- Lokalt kontrollpanel: `http://192.168.4.44:8080`.
- Innlogging ligger i `/home/pi/.ssh/robotcar-web-login.conf` på arbeidsmaskinen.
- Trykk **Aktiver motorer**, og hold en pil eller W/A/S/D. Slipp for å stoppe.
- Mellomrom og den røde **STOPP**-knappen stopper kjøring og navigasjon.
- Maksimal sammenhengende bevegelse er **2,5 sekunder**, også ved gjentatte
  kommandoer. Deretter må bilen stå stille minst ett sekund og aktiveres på nytt.
- Manglende kjørekommandoer stopper motorene etter maksimalt 0,4 sekunder.
- Kameraene viser foran/bak; AI analyserer alltid frontkameraet, uavhengig av
  hvilken visning operatøren velger.
- Kartmål og vaktpunkter velges ved å klikke i kartet. Ukjent gulv og områder
  for nær hindringer blir ikke godkjent som rute.

Ingen automatisk tur starter ved oppstart eller etter nettverksbrudd.

## Fordeling

| Enhet | Oppgaver | Tjenester |
|---|---|---|
| Pi 4, `192.168.4.43` | GPIO, motorpolariteter, tidsgrense og stopp ved nettverksbrudd | `robotcar-motor` |
| Pi 5, `192.168.4.44` | To CSI-kameraer, Hailo-8, RPLiDAR, kartmatching og webkontroll | `robotcar@camera`, `@vision`, `@lidar`, `@mapworker`, `@webapp` |

Kontrollkommandoer går over en egen WebSocket og en autentisert TCP-forbindelse
til motor-Pi-en. JPEG-bilder kodes én gang og siste bilde deles mellom seerne;
gamle bilder legges ikke i en applikasjonskø. Kartbehandling og AI kjører i egne
prosesser og kan ikke blokkere motorenes stopptråd.

Lokalt ble begge kameraene målt til omtrent **20 fps**, nettleserens rundtur til
**17–33 ms**, og Hailo-inferens til omtrent **30 ms**. Dette er lokalnett-målinger,
ikke en garanti for forsinkelsen over Internett. MJPEG ved 640×480 prioriterer
enkel, kort bufring; båndbredde og videoalder må måles på den endelige nettruten.

## Kart og gjenkjenning

- LiDAR gir målinger i meter/radianer, med x framover og y til venstre.
- Robust ICP mellom skanninger og korreksjon mot kartet gir posisjon uten å
  late som hjulhastighet er målt odometri.
- Et 30×30 m kart har celler på 5 cm og skiller ukjent, ledig og opptatt plass.
- Kart lagres atomisk som komprimerte NPZ-filer med posisjonsreferanser og
  visuelle landemerker. Siste aktive kart kan hentes etter omstart, men gammel
  posisjon blir aldri godkjent som en ny måling.
- ORB-bildetrekk med geometrisk kontroll finner kjente utsyn; Hailo gir
  objektklasser. Visuelle treff foreslår posisjoner som må bekreftes av LiDAR.
  Generelle objektklasser alene identifiserer ikke et bestemt møbel eller rom.
- Gjenlokalisering avviser tvetydige steder og retninger. Rotasjonsmodus samler
  flere utsyn med korte pulser når autonomi er godkjent.
- A* bruker hindringer utvidet med bilens sikkerhetsradius. Frontier-søk velger
  mål ved grensen til ukjent plass. Vakthold følger lagrede punkter med pause
  mellom rundene.

Dette er en konservativ, egen kartleggingsimplementasjon uten hjulenkodere og
uten grafoptimalisering for store sløyfer. Drift, hindringsavstander,
LiDAR-orientering og gjentatt gjenlokalisering må valideres i leiligheten.

## Installasjon og vedlikehold

Se [installasjonsveiledningen](docs/INSTALL.md),
[testprotokollen](docs/VALIDATION.md) og [nettverksoppsettet](docs/NETWORK.md).
Tidligere lokale skript er bevart i [legacy](legacy/README.md).

```bash
# På hver Pi, fra denne kildemappen:
sudo bash deploy/install.sh motor     # Pi 4
sudo bash deploy/install.sh sensors   # Pi 5

# Tester uten fysisk bevegelse:
python3 -m unittest discover -s tests -v
```

Privat konfigurasjon ligger i `/etc/robotcar/robotcar.env`; kart og modeller i
`/var/lib/robotcar`; ferske sensorverdier i `/run/robotcar`. Passord, nøkler,
kamerabilder og leilighetskart skal ikke sjekkes inn i det offentlige repoet.

## Referanser

- [Raspberry Pi AI-programvare](https://www.raspberrypi.com/documentation/computers/ai.html)
- [Picamera2](https://github.com/raspberrypi/picamera2)
- [SLAMTEC RPLiDAR-protokoll](https://bucket.download.slamtec.com/f010c72be308cdc618e91746d643278185ed02b2/LR001_SLAMTEC_rplidar_protocol_v2.2_en.pdf)
