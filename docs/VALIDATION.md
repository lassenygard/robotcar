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

32 tester består lokalt, på Pi 4 og på Pi 5 med
`python3 -m unittest discover -s tests -v`. Hele testsettet ble kjørt før
installasjon av versjon `7ed2d7482842970a07fdd05fd0ee7dc473a7518f` på begge Pi-er.

Testene dekker blant annet tapt heartbeat, uforlengbar bevegelsesgrense,
pause før ny aktivering, kommando-replay, ikke-endelige tall, sperret autonomi,
LiDAR-pakkeformat og enheter, ICP mot kjent bevegelse, avvisning av ukjent/
blokkert rute, kartlagring uten å godkjenne gammel posisjon, visuell
posisjonshypotese bekreftet av LiDAR, tvetydige romretninger og hindringsstopp.

Nettverkstestene bruker lokale, simulerte motorer uten GPIO. De
kontrollerer at en avbrutt motorkommando lukker forbindelsen før neste kommando,
at et svar med feil sekvensnummer avvises, at to samtidige nettlesere ikke kan
overta hverandres kontroll, og at frakobling stopper motorene. De dekker også
utløpte kommandobilletter, et dødt kamera med gammel statusfil og ugyldige
JSON-forespørsler. WebSocket-oppryddingen fullfører stopp selv om nettserveren
kansellerer forespørselen ved nettbrudd. Gyldig og utløpt innlogging skilles også
for nettleserens gjenoppkobling.

Feilinjeksjon under installasjon bekrefter at ufullstendige eller skadde
programfiler ikke aktiveres, og at forrige versjon kan beholdes/gjenopprettes.
Feil under lagringssynkronisering bevarer forrige kart; ugyldig oppløsning eller
posisjon avvises. En skadet aktiv kartfil blokkerer kartbruk inntil operatøren
velger et annet kart eller eksplisitt starter et nytt. Filen slettes ikke.

Etter oppdatering på Pi 4 var målt tilstand `startup_disarmed`, venstre/høyre
utgang 0, autonomi av og kontinuerlig grense 2,5 s. Ingen nye fysiske kjørepulser
ble brukt i denne verifiseringen.

## Gjenoppretting etter batteribyttet

Begge maskiner svarte igjen på SSH. Den gamle Pi 5-installasjonen inneholdt
tomme Python-filer og nullbytes etter at strømmen forsvant under kopiering.
Den ble arkivert privat før gjenoppretting. Konfigurasjon og Hailo-modell var
intakte; modellens SHA-256 er kontrollert mot den opprinnelige verdien.

Tjenestene kjører nå fra versjonerte mapper under `/opt/robotcar/releases` med
kontrollsum-manifest og atomisk bytte av `/opt/robotcar/current`. Begge Pi-er
har samme runtime-versjon og bestått manifestkontroll. Kameraer, AI, kart- og
webtjeneste kjører igjen; LiDAR-tjenesten melder fortsatt sensorfeil.
Ingen nye kjørepulser er sendt etter batteribyttet.

`scripts/check_gateway.py` har bekreftet innlogging, gyldige JPEG-bilder fra
begge kameraer og WebSocket gjennom HTTPS-domenet. Første måling etter
gjenopprettingen ga ca. 20 fps og median 33 ms rundtur (maks. 91 ms). Denne
innloggede testen ble kjørt fra lokalnettet og kan bruke hairpin NAT.
Innloggingssiden er i tillegg kontrollert utenfra fra Østerrike, Spania og
Sverige: alle svarte 200. Separate kontroller uten innlogging ga 401 på video
og WebSocket fra fire andre eksterne noder. Eksterne testtjenester har aldri
fått innloggingsinformasjon eller kamerabilder.

**Siste tilgjengelighet, kl. 22:07 lokal tid:** Pi 5 ble igjen utilgjengelig
etter at installasjonen og manifestkontrollen av `7ed2d74` var fullført.
Den påfølgende gjennomgangen av video stoppet med timeout. SSH og port 8080
ga timeout fra arbeidsmaskinen; ping feilet også fra Pi 4 og edge. Pi 4 var
fortsatt tilgjengelig med aktiv motortjeneste og `throttled=0x50005`. Dette
bekrefter et nytt bortfall av Pi 5, men fastslår ikke årsaken. Den tidligere
beståtte videotesten er derfor ikke dokumentasjon på stabil drift over tid.

Kameraenes faktiske bilder er kontrollert privat. Oppdatert gjenoppkobling i
nettleseren er syntakskontrollert, men ikke visuelt prøvd på nytt: nettleser-
automatiseringen var utilgjengelig i denne økten. Den tidligere desktop- og
mobilkontrollen i tabellen gjelder grensesnittet før denne endringen.

## Ikke ferdig verifisert

1. **RPLiDAR:** USB-adapteren finnes, men sensoren returnerer ingen bytes. Derfor
   finnes ikke et nytt, faktisk leilighetskart fra denne installasjonen.
   Etter lading ble dette også bekreftet med SLAMTECs offisielle SDK 2.1.0:
   `getDeviceInfo` ga `80008002` (timeout) ved 115200, 256000 og 460800 baud,
   også med kameraer og AI midlertidig stanset. USB-porten kan åpnes.
2. **Autonomi:** go-to, utforsking, gjenlokalisering i leiligheten og vaktrunder
   er implementert, men ikke kjørt fysisk. Begge motor-/navigasjonsflagger
   forblir av. LiDAR-offset og sikkerhetsradius gjenstår å kalibrere.
3. **Strøm:** begge Pi-er rapporterte `throttled=0x50005` etter at batteriet var
   ladet: aktiv lav spenning og struping samt historiske hendelser. Pi 5 vekslet
   mellom dette og `0x50000`. Kernel-loggen viser gjentatte spenningsfall i
   gjeldende oppstart. Lading har derfor ikke løst den målte forsyningsfeilen;
   spenningsomformer, kabler og forsyning under last må kontrolleres.
4. **Ekstern kjøring:** HTTPS og innloggingssiden er bekreftet utenfra.
   Innlogget video og WebSocket er bekreftet via domenet fra LAN. Faktisk
   videoalder og styreforsinkelse fra mobilnett gjenstår å måle; kjøring og
   stopp ved nettbrudd må prøves med person ved bilen. Pi 5 må tilbake og
   forbindelsen må holde seg stabil før dette kan fullføres.
5. **GitHub-publisering:** repository finnes og kan leses, men forsøk på å
   opprette arbeidsgrenen via GitHub-koblingen ga 403, «Resource not accessible
   by integration». Installasjonslisten mangler appinstallasjon for
   `lassenygard`, som eier repoet. Ingen vellykket push er derfor dokumentert ennå.

Programvaretestene erstatter ikke disse fysiske og eksterne kontrollene.
