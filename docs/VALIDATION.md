# Verifikasjon 2026-10-06

## Testet på fysisk bil

| Område | Resultat |
|---|---|
| SSH | Pi 4 på 22; Pi 5 på 2222; innlogging fungerer |
| Frontkamera | imx219/0 peker mot kjøkkenøyens mørke fronter; 640×480, ca. 20 fps |
| Bakkamera | imx708_wide/1; opp-ned-visning korrigert; ca. 20 fps |
| Synsfelt | Standard 640×480-sensormodus beskar bildet; hele sensorutsnittet er nå brukt før nedskalering |
| Hailo | Hailo-8 firmware 4.20.0, eksisterende YOLOv5-modell; typisk ca. 30 ms per inferens |
| Styring | Fram, bak, venstre og høyre rotasjon har synlig bevegelse i kamerabildene |
| Deadman | Hver fysisk testpuls hadde 0,18 s lease; påfølgende status viste null utgang og `lease_expired` |
| Respons | Nettleser-ping på LAN 17–33 ms; én målt Pi 5→Pi 4-rundtur 10,6 ms |
| Web | Desktop 1440 px og mobil 390 px; levende video begge veier, ingen JavaScript-feil, ingen horisontal overflow |
| Tilgang | Uinnlogget video/kart/WS gir 401, annen Origin på WS gir 403, kartsti med `../` avvises |
| Autonomi | Forespørsel om automatisk kartlegging avvises i gjeldende testmodus |

Totalt åtte fysiske pulser à 0,18 s ble sendt, adskilt av reelle stopp og pauser.
Det er ikke gjennomført langvarig kjøring. Ingen tur eller vaktrunde står aktiv.
Motorretningene er korrigert ved bytting av sidegrupper og invertering av de
tidligere `*_right`-utgangene. Bildemålingene etter korreksjon viste:

- Fram: skala ca. 1,009; bak: ca. 0,992 — bildet vokser/minker som forventet.
- Venstrerotasjon: omtrent +35 px horisontal forskyvning.
- Høyrerotasjon: omtrent −38 px horisontal forskyvning.

Dette bekrefter hovedretningene, ikke presis hastighet, perfekt rettlinjet
kjøring eller kalibrert avstand. Retningskontrollen brukte 225–322 matchede
bildetrekk; ingen kamerabilder er lagt i det offentlige repoet.

## Automatiske tester

Kjør `python3 -m unittest discover -s tests -v`.

Testene dekker blant annet tapt heartbeat, uforlengbar bevegelsesgrense,
pause før ny aktivering, kommando-replay, ikke-endelige tall, sperret autonomi,
LiDAR-pakkeformat og enheter, ICP mot kjent bevegelse, avvisning av ukjent/
blokkert rute, kartlagring uten å godkjenne gammel posisjon, visuell
posisjonshypotese bekreftet av LiDAR, tvetydige romretninger og hindringsstopp.

## Ikke ferdig verifisert

1. **RPLiDAR:** USB-adapteren finnes, men sensoren returnerer ingen bytes. Derfor
   finnes ikke et nytt, faktisk leilighetskart fra denne installasjonen.
2. **Autonomi:** go-to, utforsking, gjenlokalisering i leiligheten og vaktrunder
   er implementert, men ikke kjørt fysisk. Begge motor-/navigasjonsflagger
   forblir av. LiDAR-offset og sikkerhetsradius gjenstår å kalibrere.
3. **Strøm:** kernel-loggen inneholder gjentatte undervoltage-hendelser. Senere
   måling var `throttled=0x50000`, som viser tidligere hendelser uten aktivt
   spenningsvarsel akkurat ved avlesningen. Stabil forsyning må bekreftes under last.
4. **Nettadresse:** robotcar.nygardene.no mangler DNS (NXDOMAIN). HTTPS/proxy og
   ekstern video-/styringslatens kan ikke godkjennes før ruten er opprettet.
5. **GitHub-publisering:** repository finnes og kan leses, men forsøk på å
   opprette arbeidsgrenen via GitHub-koblingen ga 403, «Resource not accessible
   by integration». Ingen vellykket push er derfor dokumentert ennå.

Programvaretestene erstatter ikke disse fysiske og eksterne kontrollene.
