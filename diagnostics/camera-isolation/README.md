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
før isolering 8. oktober. Første kalde oppstart er observert i ti minutter:
frontkameraet virker, mens bakkameraet leverte null bilder.
**Neste oppstart er klargjort med bare bakkameraets test aktivert.**
Se [måleresultat og oppsett for neste forsøk](RESULTS-2026-10-08.md).

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

Under grunnforsøket er vanlig robotvideo, AI, kartoppdateringer og webkontroll
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

Observer minst ti minutter etter omstart. Det siste kjente bakre kamerautfallet
kom etter omtrent 59 sekunder med bilder. Gjenta oppstart og observasjon før
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

## Gjenoppretting

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
