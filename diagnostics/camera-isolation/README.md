# Isolering av kamerafeil på Pi 5

Dette er et midlertidig, reverserbart forsøk på kamera-Pi-en `192.168.4.44`.
Det endrer ikke kameraenes drivere, firmware, kabler eller strømforsyning.
Motorer skal ikke kjøres. Pi 4 og motorenes eksisterende sperre beholdes.

## Hva som stoppes

`control.py prepare` lagrer en full oversikt over system- og brukertjenester,
opprinnelig startstatus og oppstartsmåte i
`/var/lib/robotcar-camera-isolation/original.json` (bare tilgjengelig for root).
Den konkrete listen over testkandidater finnes i feltet `units` og i
[den lagrede tjenestelisten](INVENTORY.md): 107 enheter, hvorav 65 var aktive
før isolering 8. oktober. Kabelforsøkene er beskrevet i
[rapporten fra 8. oktober](RESULTS-2026-10-08.md).
**9. oktober er minimaltestene avsluttet etter stabil drift med ett kamera
per Pi.** IMX708 er nå frontkamera på Pi 5, IMX219 bakkamera på Pi 4.
Fasen `robot-runtime` tillater de seks robot-/Hailo-enhetene og beholder
de øvrige 101 sperrene. Normal video/AI/web kjører igjen.
Se [oppdatert resultat](RESULTS-2026-10-09.md).

Kandidatene omfatter følgende, når de er installert:

| Gruppe | Innhold |
| --- | --- |
| A | Robotens webserver, LiDAR-mottaker, kartarbeider, objektdeteksjon og Hailo; brukerens PipeWire, PulseAudio, WirePlumber, medieportaler og GVFS |
| B | Skrivebord/LightDM, VNC og Raspberry Pi Connect; Bluetooth, skriver- og fildeling, Avahi, ModemManager, brukerhjelpere, oppdateringer, cron, diskvedlikehold og Google Drive-sikkerhetskopiering |
| Fast av | Den vanlige `robotcar@camera.service`, så testprogrammet har kameraene alene |

Tilhørende sockets, timere og filovervåkere sperres også, sammen med relevante
tjenester som kan startes på forespørsel. A og B er foreløpige funksjonsgrupper,
ikke like store halvdeler. Når grunnforsøket virker, kan vi dele den konkrete
listen videre med `custom`, og holde nært avhengige tjenester sammen.

SSH, NetworkManager, Wi-Fi, D-Bus, innlogging, kjernens enhetsstyring,
loggføring, klokkesynkronisering, filsystem og sikkerhetstjenester beholdes.
Vi bruker ekstra startvilkår som sperre; eksisterende enhetsfiler og
oppstartslenker beholdes. En sperret tjeneste kan derfor fortsatt stå som
`enabled`, men starter ikke så lenge sperrefilen finnes.

Under fasen `baseline` er vanlig robotvideo, AI, kartoppdateringer og webkontroll
på Pi 5 stoppet. LiDAR på Pi 4 fortsetter. SSH er tilgjengelig på port 2222.

## Installasjon og første forsøk

Installer `capture.py`, `record.py` og `control.py` som root-eide filer i
`/opt/robotcar-camera-test/`, og enhetsfilen i `/etc/systemd/system/`.
Kontroller enhetsfilen med `systemd-analyze verify` før bruk.

Kjør på kamera-Pi-en:

```sh
sudo python3 /opt/robotcar-camera-test/control.py prepare
sudo systemd-run --unit=robotcar-camera-isolation-apply --collect \
  /usr/bin/python3 /opt/robotcar-camera-test/control.py baseline
sudo python3 /opt/robotcar-camera-test/control.py status
```

Den uavhengige systemjobben gjør at stenging av skrivebordet ikke avbryter
omleggingen. Brukeren starter deretter Pi-en på nytt. Et forsøk i samme
oppstart kan fortsatt være påvirket av en sensor som allerede har låst seg.

Testen bruker ett separat Picamera2-program per kamera, 640 × 480 RGB,
20 bilder/s og samme sensormoduser som robotprogrammet. Den verken lagrer
kamerabilder, komprimerer JPEG, bruker nettverket eller styrer motorer.
Bare faktisk mottatte bilder telles. Ved bildestopp avsluttes prosessen av
en 15-sekunders vakt, uten automatisk omstart som kan skjule feilen.

Løpende tellere ligger i `/run/robotcar-camera-test/`. Etter ti minutter
lagres en observasjon i `/var/lib/robotcar-camera-test/`. Ved avslutning
lagres også siste bildestatistikk og årsak til prosessavslutning der.
`status` kontrollerer oppstarts-ID, bildenes alder og faktisk prosesstatus;
en gammel ti-minuttersrapport betyr ikke at kameraet fortsatt virker.

## Sammenligning og halvering

Observer lenger enn tidligere feilvindu etter omstart. IMX219 feilet ved ett
forsøk etter 609 sekunder; ti minutter er derfor ikke tilstrekkelig. Gjenta oppstart og observasjon før
en gruppe friskmeldes, siden feilen tidligere har vært periodisk.

```sh
# Tillat A ved neste omstart; B og vanlig kameraprogram forblir sperret.
sudo python3 /opt/robotcar-camera-test/control.py A
# Eller tillat B ved neste omstart, med A sperret.
sudo python3 /opt/robotcar-camera-test/control.py B
```

Brukeren starter Pi-en på nytt mellom hver variant. Ingen andre variabler
(strøm, kabler, kamerainnstillinger eller programversjoner) endres under
sammenligningen. For en mindre delmengde lages en JSON-fil med identifikatorer
fra `original.json`, for eksempel `["system:hailort.service"]`:

```sh
sudo python3 /opt/robotcar-camera-test/control.py custom --allow-file /path/to/subset.json
```

En tillatt tjeneste får sin opprinnelige oppstartsatferd tilbake; den blir
ikke automatisk aktiv hvis den opprinnelig var deaktivert eller mangler
en aktiverende avhengighet. Kontroller at gruppen faktisk er aktiv i forsøket.
Test begge komplementære grupper, gjenta grunnforsøket og legg mistenkte
tjenester tilbake for å bekrefte sammenhengen. Samspill mellom tjenester kan
gi feil bare når begge grupper er aktive og krever egne kombinasjonsforsøk.

**Begrensning:** Den minimale testen produserer ingen JPEG-bilder til det
vanlige AI-/websystemet. At disse tjenestene er aktive uten bilder, tester
oppstart og bakgrunnsaktivitet, ikke full arbeidsbelastning. Etter en stabil
minimal test må vi derfor også teste vanlig kameraprogram alene (med begge
testtjenester av), og deretter legge tilbake arbeidsbelastninger trinnvis.
Vi må ikke friskmelde AI eller selve kameraprogrammet ut fra tomgangstester.
Hvis grunnforsøket feiler, gjenstår blant annet drivere, strøm og maskinvare;
det beviser ikke alene at kamera eller kabel er defekt.

## Langtest av IMX219 på Pi 4

Når IMX219 er koblet til Pi 4, kan samme bildebaserte vakt brukes uten å
stanse LiDAR-tjenestene. Installer `capture.py`, `record.py` og
`robotcar-camera-pi4-long-test.service` på samme måte som testfilene ovenfor.
Start testen manuelt:

```sh
sudo systemctl start robotcar-camera-pi4-long-test.service
sudo cat /run/robotcar-camera-test/front.json
```

Tjenesten er med hensikt ikke aktivert for automatisk oppstart og starter
ikke automatisk på nytt etter en feil. Den tar 640 × 480 RGB ved 20 bilder/s,
lagrer ingen bilder og bruker verken nettverk, LiDAR eller motorstyring.
Systemd-vakten avslutter prosessen dersom nye bilder uteblir. Ti-minutters-
og stopprapporter lagres på samme steder som på Pi 5.

## Gjenoppretting

Når vanlig robotdrift skal tilbake med øvrige bakgrunnstjenester fortsatt
sperret, installer/verifiser ønsket runtime og kamerakonfigurasjon først:

```sh
sudo python3 /opt/robotcar-camera-test/control.py runtime
```

Dette stopper/deaktiverer de gamle Pi 5-kameratestene og åpner bare sperrene
for kamera, AI, LiDAR-mottak, kartarbeider, web og Hailo. Langtesten på Pi 4
stoppes separat før `robotcar@camera` startes der. Full gjenoppretting av
den tidligere skrivebords-/bakgrunnsdriften gjøres fortsatt med:

```sh
sudo python3 /opt/robotcar-camera-test/control.py restore
```

Dette stopper og deaktiverer testkameraene, fjerner bare dette forsøksoppsettets
egne startvilkår, og starter tidligere aktive tjenester igjen. Opprinnelige
oppstartslenker har hele tiden vært beholdt. En omstart gjenoppretter også
normal kjøring av oppstartsspesifikke engangstjenester. Hvis et generert
startvilkår er endret manuelt, avbryter verktøyet fremfor å slette endringen.

Hvis en omlegging avbrytes, kjør `status` og deretter enten samme variant
igjen eller `restore`. Ikke slett `original.json`; den er grunnlaget for
korrekt gjenoppretting.
