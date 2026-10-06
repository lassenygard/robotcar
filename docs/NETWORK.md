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

Ved siste kontroll kl. 22:07 falt Pi 5 ut igjen, mens Pi 4 fortsatte å svare.
SSH, HTTP og ping til Pi 5 feilet fra flere maskiner på LAN. Nettsiden kan
ikke levere innlogging eller video mens Pi 5 er utilgjengelig; den tidligere
beståtte testen må gjentas etter at forbindelsen er tilbake.

Ikke videresend Pi 4 sin motorport 5001 eller Pi 5 sine interne sensorporter
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
