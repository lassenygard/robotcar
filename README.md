# Robotcar — to Raspberry Pi-er

Robotcar har et innlogget kontrollpanel med to kameravisninger, rask manuell
styring, kartvisning og navigasjonskontroller. Motorstyring kjører isolert på
Pi 4 sammen med en separat LiDAR-leser; kameraer, Hailo-8 og kartlegging kjører på Pi 5.

**Status 2026-10-08:** RPLiDAR fungerer med vanlig seriell lesing etter at
USB-kabelen ble flyttet til Pi 4. Omtrent 7 skanninger/s sendes til Pi 5.
Et kart fra bilens stillestående plassering er lagret og lastet inn igjen;
LiDAR og kameratrekk har tidligere bekreftet posisjonen i dette kartet.
Frontkameraet har levert ca. 20 fps etter oppstarten 8. oktober.
Bakkameraet leverte senere 1172 bilder, omtrent 59 sekunder, før det stoppet.
**Fra 8. oktober kl. 16:58 er Pi 5 i midlertidig kamera-isolering:**
107 valgfrie oppstartsenheter er sperret, inkludert vanlig robotvideo,
AI, kartarbeider og webkontroll. SSH og nettverk er beholdt. To minimale
kameratester ble startet ved første strømrunde. Fronten leverte 12 149 bilder
over 607 sekunder; bakkameraet leverte null. Ved neste oppstart, med bare
bakkameraets test aktivert, feilet identifikasjonen av begge sensorer allerede
før testen startet (`SDA stuck at low`). Brukeren opplyste at strømavbrekket
varte noen sekunder. Etter ryddig avslåing og ett minutt uten strøm ble begge
sensorene gjenkjent igjen, men bakre test alene leverte fortsatt null bilder
og feilet med tidsavbrudd. Årsaken er fortsatt uavklart; kamerakabel/kontakt
og en kontrollert sammenligning med fungerende utstyr er foreslått neste steg.
Se [oppsett og gjenoppretting](diagnostics/camera-isolation/README.md) og
[den konkrete tjenestelisten](diagnostics/camera-isolation/INVENTORY.md).
[Resultat og neste forsøk](diagnostics/camera-isolation/RESULTS-2026-10-08.md).
Fangstprosessene er isolert og overvåket; feilhåndteringen er prøvd med simulerte bilder.
Innlogging, video, LiDAR og posisjon ble tidligere kontrollert gjennom
HTTPS-domenet fra LAN; full innlogget ytelse fra mobilnett gjenstår.

Begge Pi-er kjører nå på vanlig strømforsyning uten registrert lav spenning
i denne oppstarten. **Motorene er sperret fordi bilen er tilkoblet kabler.**
Den tidligere batteritimeren er deaktivert. Full leilighetskartlegging,
rotasjon for gjenkjenning, go-to og vaktrunder gjenstår å prøve fysisk etter
kalibrering og frakobling av kablene. Kode og dokumentasjon er publisert på
[arbeidsgrenen i GitHub](https://github.com/lassenygard/robotcar/tree/codex/dual-pi-robotcar).

## Bruk

- Lokalt kontrollpanel: `http://192.168.4.44:8080`.
- Ekstern adresse: `https://robotcar.nygardene.no` — krever at Pi 5 er på nett.
- Innlogging ligger i `/home/pi/.ssh/robotcar-web-login.conf` på arbeidsmaskinen.
- Kartet `stue-stasjonar-20261007` viser det som er målt fra den nåværende
  plasseringen; det er ikke et ferdig kart over hele leiligheten.
- Under kabeltilkobling er motortjenesten sperret uavhengig av knappene nedenfor.
- Trykk **Aktiver motorer**, og hold en pil eller W/A/S/D. Slipp for å stoppe.
- Mellomrom og den røde **STOPP**-knappen stopper kjøring og navigasjon.
- Maksimal sammenhengende bevegelse er **2,5 sekunder**, også ved gjentatte
  kommandoer. Deretter må bilen stå stille minst ett sekund og aktiveres på nytt.
- Manglende kjørekommandoer stopper motorene etter maksimalt 0,4 sekunder.
- Kameraene viser foran/bak; AI analyserer alltid frontkameraet, uavhengig av
  hvilken visning operatøren velger.
- Kartmål og vaktpunkter velges ved å klikke i kartet. Ukjent gulv og områder
  for nær hindringer blir ikke godkjent som rute.
- Mål og vaktruter følger kartet de ble valgt i. Kartbytte fjerner gamle mål;
  vaktruter lagret før kartidentitet ble innført må velges og lagres på nytt.

Ingen automatisk tur starter ved oppstart eller etter nettverksbrudd.

## Fordeling

| Enhet | Oppgaver | Tjenester |
|---|---|---|
| Pi 4, `192.168.4.43` | USB-LiDAR og skanneoverføring; separat GPIO-prosess med tidsgrense/stopp | `robotcar@lidar`, `@lidarfeed`, `robotcar-motor` (sperret) |
| Pi 5, `192.168.4.44` | To CSI-kameraer, Hailo-8, mottak av LiDAR, kartmatching og webkontroll | `robotcar@camera`, `@vision`, `@lidar`, `@mapworker`, `@webapp` |
| Eksisterende edge, `192.168.4.58` | HTTPS og videresending av video/WebSocket til Pi 5 | nginx, certbot |

Kontrollkommandoer går over en egen WebSocket og en autentisert TCP-forbindelse
til motor-Pi-en. JPEG-bilder kodes én gang og siste bilde deles mellom seerne;
gamle bilder legges ikke i en applikasjonskø. Kartbehandling og AI kjører i egne
prosesser og kan ikke blokkere motorenes stopptråd.
LiDAR-overføringen krever det interne tokenet og henter bare siste skanning.
Målingens alder inkluderer hele nettverksrundturen; gjentatte, gamle eller
ugyldige svar blir ikke godkjent som nye målinger. Ved forbindelsesbrudd
blir posisjonen ukjent.

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
  visuelle landemerker. Skriving synkroniseres før det gamle kartet erstattes.
  Siste aktive kart kan hentes etter omstart, men gammel posisjon blir aldri
  godkjent som en ny måling. Skadet kart krever at operatøren velger et annet
  kart eller starter et nytt; filen beholdes for gjenoppretting.
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
