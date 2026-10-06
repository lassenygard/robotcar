# robotcar.nygardene.no

Per 2026-10-06 svarer offentlig DNS **NXDOMAIN** for robotcar.nygardene.no.
Rotdomenet nygardene.no peker til 84.48.104.79. Autoritativ DNS bruker hyp.net /
Domeneshop. DNS-/reverse-proxy-tilgang er ikke tilgjengelig for dette arbeidet
ennå, så robotpanelet er kun verifisert på lokalnettet.

Den planlagte ruten er:

```
Nettleser -- HTTPS/WSS --> eksisterende edge/reverse proxy
                           -- privat LAN --> 192.168.4.44:8080
                                              -- token --> 192.168.4.43:5001
```

Opprett DNS-oppføringen mot den eksisterende offentlige edge-adressen og bruk
`deploy/robotcar.nginx.conf` i den eksisterende HTTPS-proxyen med gyldig TLS.
Konfigurasjonen skal tilpasses den faktiske edge-verten og sertifikatene, ikke
legges over en eksisterende standardserver. WebSocket må støttes og buffering
må være av for videostrømmen. Innlogging håndteres av robotappen.

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

Reserver de to Pi-adressene i ruteren, slik at interne forbindelser ikke peker
på feil enhet etter DHCP-endringer.
