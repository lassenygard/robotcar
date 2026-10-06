# robotcar.nygardene.no

DNS er opprettet hos Domeneshop 2026-10-06:

```
robotcar.nygardene.no CNAME nygardene.duckdns.org
nygardene.duckdns.org A     84.48.104.79
```

Den eksisterende nginx-serveren på `192.168.4.58` har nå en egen virtuell vert
for robotcar, med et gyldig Let's Encrypt-sertifikat til 2027-01-04.
Certbot-timeren er aktiv, og eksisterende deploy-hook validerer og laster nginx
på nytt ved sertifikatfornyelse. Bare robotcar-navnet er fjernet fra listen
over gamle, deaktiverte vertsnavn; øvrige nettsteder er bevart.

Den installerte ruten er:

```
Nettleser -- HTTPS/WSS --> eksisterende edge/reverse proxy
                           -- privat LAN --> 192.168.4.44:8080
                                              -- token --> 192.168.4.43:5001
                                              <-- token -- 192.168.4.43:8801/scan
```

HTTP omdirigeres til HTTPS. WebSocket-oppgradering er satt opp, og proxybuffering
er av for video. Innlogging håndteres av robotappen; motortokenet blir aldri
sendt til nettleseren. Konfigurasjonen finnes i
`deploy/robotcar.nygardene.no.conf` og `deploy/robotcar.nginx.conf`.

`sudo sh deploy/install-edge.sh` installerer på edge-verten, tar sikkerhetskopi
av de berørte nginx-filene, skaffer/fornyer eget sertifikat via den eksisterende
ACME-kontoen og ruller konfigurasjonen tilbake ved feil. Sikkerhetskopien ved
første vellykkede installasjon er
`/var/backups/robotcar-edge/20261006T114212Z`.

Etter batteribyttet og gjenoppretting av programfilene på Pi 5 besto
innlogging, begge videostrømmer og WebSocket test gjennom domenet. Testen
gjennom proxyen ble kjørt fra LAN; denne ruten kan bruke hairpin NAT. Innloggingssiden
er i tillegg bekreftet utenfra med 200-svar fra Østerrike, Spania og Sverige.
Uinnlogget video og WebSocket ga 401 fra eksterne noder i Ungarn, Moldova,
Nederland og Tyrkia. Ingen innloggingsinformasjon ble sendt til testtjenesten.
Reell innlogget video- og styreforsinkelse fra mobilnett gjenstår å måle.

Etter overgang til vanlig strømforsyning 2026-10-07 er begge Pi-er tilbake.
Innlogging, video, WebSocket, ekte LiDAR-data og kartposisjon er kontrollert
gjennom domenet fra LAN. Målt median WebSocket-rundtur var 25,3 ms, maks. 60,9 ms.
Samtidig mottak av begge videostrømmer ga 13,2 og 6,3 fps i denne prøven;
kameraprosessene produserte fortsatt ca. 20 fps. Dette skiller faktisk mottak
gjennom nettverket fra kameraenes opptaksrate. Videoalder er ennå ikke målt.

LiDAR-ens USB-kabel står i Pi 4. En egen HTTP-tjeneste på privat port 8801
krever `ROBOTCAR_TOKEN`; uautorisert forespørsel er kontrollert og gir 401.
Pi 5 henter siste skanning med en ny forespørselsidentifikator og avviser feil
svar, gamle sekvensnumre og målinger eldre enn 650 ms inklusive rundtur.
En kontrollert stans av denne tjenesten gjorde kartposisjonen ukjent; oppstart
ga ferske skanninger og målt gjenlokalisering igjen.

Motortjenesten er med hensikt stoppet og sperret mens bilen står i strømkabler.
Nettsiden viser derfor motorforbindelsen som frakoblet i denne driftsformen.

Ikke videresend Pi 4 sine porter 5001/8801 eller Pi 5 sine interne sensorporter
8800/8810 til Internett. Sensorportene lytter bare på 127.0.0.1. Ikke publiser
8080 som ukryptert erstatning for HTTPS; kamera og kontroll krever kryptert
innlogging når trafikken går utenfor lokalnettet.

Etter DNS/proxy-oppsett skal følgende kontrolleres fra et eksternt nett:

1. Gyldig sertifikat på `https://robotcar.nygardene.no`.
2. Uinnlogget video, kart og WebSocket avvises.
3. Begge kameravisninger og WebSocket-ping fungerer gjennom proxyen.
4. Mål videoalder og kommandoforsinkelse. Test at nettbrudd stopper en kort
   bevegelse med en person ved bilen.
5. Bekreft at privat kamerafeed og rå motortjeneste ikke kan nås direkte.

`python3 scripts/check_gateway.py` kontrollerer
innlogging, avvisning av uautorisert/feil-origin trafikk, begge videostrømmer
og WebSocket-rundtur. Skriptet leser den lokale passordfilen, skriver bare
måleverdier og sender ingen aktiverings- eller kjørekommandoer. Kjør det fra
et annet nett for reell måling utenfra; en test via offentlig IP fra LAN kan
bruke ruterens hairpin NAT og bekrefter ikke mobilnettets forsinkelse.

Reserver de to Pi-adressene i ruteren, slik at interne forbindelser ikke peker
på feil enhet etter DHCP-endringer.
