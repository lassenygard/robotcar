# Verifikasjon 2026-10-07

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
| LiDAR | USB på Pi 4, vanlig SCAN ved 115200 baud, ca. 7 omdreininger/s |
| Forsyning | Begge på vanlig strøm, `throttled=0x0`; Pi 5 ca. 5,00 V |
| Motorsperre | Motortjenesten er inaktiv og kan ikke starte mens sperrefilen finnes |

Før overgangen til vanlig strøm ble totalt åtte fysiske pulser à 0,18 s sendt,
adskilt av reelle stopp og pauser. Ingen hjulpulser er sendt under kabeltilkobling.
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

56 tester dekker gjeldende kildekode med
`python3 -m unittest discover -s tests -v`. Testene kjøres lokalt og på hver Pi
før en ny versjon aktiveres. Installert kildeversjon står i
`/opt/robotcar/current/REVISION`; alle installerte filer har kontrollsummer.

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

Kameratestene bruker ekte underprosesser med simulerte bilder. En låst prosess
som ignorerer SIGTERM blir drept og erstattet mens det andre kameraets prosess
fortsetter med samme prosess-ID og nye bilder. De dekker også ufullstendige,
gamle og ugyldige bildepakker, 503 ved manglende kamera, avslutning av en åpen
strøm når bilder stopper, systemd-varsling og sensorvalg når kameranummeret
endres. Kamerafeil avviser kjørekommandoer også før siste bilde blir gammelt.

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
webtjeneste ble gjenopprettet. LiDAR virker nå etter flytting av USB til Pi 4.
Ingen nye kjørepulser er sendt etter batteribyttet.

`scripts/check_gateway.py` har bekreftet innlogging, gyldige JPEG-bilder fra
begge kameraer og WebSocket gjennom HTTPS-domenet. Første måling etter
gjenopprettingen ga ca. 20 fps og median 33 ms rundtur (maks. 91 ms). Denne
innloggede testen ble kjørt fra lokalnettet og kan bruke hairpin NAT.
Innloggingssiden er i tillegg kontrollert utenfra fra Østerrike, Spania og
Sverige: alle svarte 200. Separate kontroller uten innlogging ga 401 på video
og WebSocket fra fire andre eksterne noder. Eksterne testtjenester har aldri
fått innloggingsinformasjon eller kamerabilder.

**Gjeldende tilgjengelighet:** etter overgang til vanlig strøm natt til 7. oktober
svarer begge Pi-er og viser `throttled=0x0`. Den gamle batterifristen er
kontrollert deaktivert på begge. Motorsperren er vedvarende gjennom omstart
og installasjon. Ingen automatisk kjøretur er aktiv.

## LiDAR og kart med bilen stillestående

Pi 5 sin serielle USB-forbindelse var fortsatt ustabil med normal forsyning.
En direkte USB-prøve ga 98 komplette omdreininger og 12 105 gyldige avstander.
Etter at brukeren flyttet USB-kabelen til Pi 4, ga ordinær seriell lesing
97 komplette omdreininger med minst 60 returer hver, totalt 11 880 gyldige
avstander fra 0,818 til 5,234 m på 15 sekunder. Helsekoden var 0 (normal).
Pi 4 leser nå kontinuerlig; Pi 5 mottar rundt 7 skanninger/s. En observert
rundtur for skanneforespørselen var 11,7 ms, målingsalder ca. 0,1–0,2 s.

Kartet `stue-stasjonar-20261007` ble bygget fra den faste plasseringen, lagret
og lastet inn igjen. Gammel posisjon var først uttrykkelig ukjent. Deretter
fant LiDAR og kameratrekk posisjonen igjen: den navngitte referansen
«Kjøkkenøyen sett fra stuegulvet» hadde 179 geometrisk konsistente bildetrekk,
og LiDAR-matching ga ca. 0,975 i implementasjonens treffandel. Dette er en
matchingverdi, ikke en kalibrert sannsynlighet for korrekt posisjon.

En kontrollert stans av `robotcar@lidarfeed` på Pi 4 ga tom skanning med
feilmelding på Pi 5 og `localized=false`. Da feeden startet igjen, kom ferske
skanninger tilbake og posisjonen ble målt på nytt. Testen brukte ingen
hjulkommandoer. Enhetstester dekker også frosne sekvensnumre, nettverksalder,
feil forespørselsidentifikator, ugyldige målepunkter og avvisning uten token.
Ved bytte av kart ryddes gamle visuelle treff og observasjonstider.

Etter siste installasjon ga 30 påfølgende prøver ingen LiDAR-feil og målt
posisjon i alle prøvene. Median var 7,1 skanninger/s, minst 106 returer per
skanning, største målte alder 229 ms og median/maks. rundtur 15,8/20,0 ms.
Begge kameraene produserte 20 fps. Denne prøven er en kort driftskontroll,
ikke en verifikasjon av batteridrift eller kontinuerlig drift gjennom natten.

Fem foreslåtte kartmål omtrent 0,5 m fra bilen ble prøvd uten kjøresignaler.
Planleggeren avviste dem: ukjent kartareal finnes ca. 0,206 m fra posisjonen,
innenfor gjeldende sikkerhetsradius på 0,32 m. Nærmeste registrerte hindring
var ca. 0,85 m unna. Kartdekning, sensorplassering og faktisk bilgeometri må
avklares før en rute fra denne posisjonen kan godkjennes.

Det lagrede kartet dekker bare synlige deler av rommet fra ett sted.
Gjenlokalisering er bekreftet fra samme sted og retning, ikke etter flytting
eller en fysisk rotasjon. LiDAR-vinkel −105 grader er fremdeles ikke kalibrert.
Ingen kamerabilder, rå skannedata eller leilighetskart legges i GitHub.

Ny HTTPS-kontroll med fungerende LiDAR ga innlogging, begge videostrømmer,
WebSocket og `localized=true`. Median rundtur var 25,3 ms (maks. 60,9 ms).
Samtidig videomottak var 13,2/6,3 fps foran/bak, mens begge kameraprosessene
fortsatt produserte ca. 20 fps. Dette ble målt via domenet fra LAN; verken
videoalder eller faktisk kjøring fra mobilnett er bekreftet av prøven.

Den separate HTTPS-verten var midlertidig utilgjengelig under sluttkontrollen
og startet på nytt omkring kl. 00:47. Nginx kom tilbake med gyldig
konfigurasjon. Ingen omstart av denne verten ble bestilt av robotcar-arbeidet;
årsaken er ikke fastslått. Selve robot-Pi-ene fortsatte å levere sensordata.

Kameraenes faktiske bilder er kontrollert privat. Oppdatert gjenoppkobling i
nettleseren er syntakskontrollert, men ikke visuelt prøvd på nytt: nettleser-
automatiseringen var utilgjengelig i denne økten. Den tidligere desktop- og
mobilkontrollen i tabellen gjelder grensesnittet før denne endringen.

## Kamerafeil senere 7. oktober

Bakkameraet sluttet å oppdatere kl. 08:21 ifølge libcamera-loggen. Den gamle
tjenesten fortsatte å rapportere 20 fps uten feil, selv om bildet var over
tre timer gammelt. Nettgatewayen korrigerte visningen ut fra bildealderen,
men kameraet ble ikke gjenopprettet automatisk. Omstart av kameratjenesten
ga nye driver-timeouter uten bilder fra bakkameraet.

Etter en kontrollert omstart av Pi 5 kl. 12:30 ble ingen av sensorene funnet.
Kjerneloggen viste `SDA stuck at low` og feil ved lesing av sensor-ID for
både imx219 og imx708. Omlasting av begge sensordriverne ga samme resultat.
`throttled=0x0`; dette fastslår ikke årsaken til kamerafeilen. Full frakobling
av strøm og fysisk kontroll av kamerakablene gjenstår fordi brukeren ikke
har tilgang til bilen akkurat nå. Pi-ene står fortsatt på, og ingen
hjulkommandoer er sendt. De tidligere videomålingene ovenfor er historiske.

Koden har nå separate fangstprosesser med tidsgrenser og gradvis lengre
pause ved gjentatt feil. Et kamera med gamle bilder viser 0 fps og feil;
strømmer lukkes og nye forespørsler avvises. En watchdog dekker selve
HTTP-serveren og overvåkingen av fangstprosessene. Test med simulerte bilder
erstatter ikke ny kontroll av begge faktiske kameraer etter fysisk utbedring.

Kamerareparasjonen ble først installert som
`7bf722ab8e5880da4ee0f347db8fdf65340ce9a2` og manifestkontrollert på begge
Pi-er. Alle de daværende 52 testene bestod på begge, inkludert
de ekte underprosessene med simulerte bilder. Under en avgrenset prøve på
Pi 5 ble kameratjenestens hovedprosess stanset med SIGSTOP. Systemd oppdaget
låsen, avsluttet prosessgruppen og startet tjenesten igjen; fersk status var
tilbake etter 11,71 s og omstartstelleren økte fra 0 til 1. Kameraene var
fortsatt utilgjengelige på maskinvarenivå etter denne prøven.

Ny innlogget HTTPS-prøve fra LAN ga 503 for begge manglende videostrømmer,
gyldig kartbilde og fungerende WebSocket. Median/maks. rundtur var 17,7/25,8 ms.
Uinnlogget video, kart og WebSocket ble fortsatt avvist. LiDAR leverte rundt
6,9 skanninger/s, og posisjonen ble gjenkjent i det lagrede stasjonære kartet
etter Pi 5-omstarten uten nye kamerabilder. Dette er fortsatt ikke validering
etter fysisk flytting. Motorene var sperret, autonomi og kalibreringsflagg
var av, begge batteritimere var deaktivert og begge Pi-er viste `throttled=0x0`.

## Ikke ferdig verifisert

Videogatewayen henter nå et nytt stillbilde først etter at forrige bilde er
sendt. Fire nye tester viser at en blokkert mottaker ikke utløser forhåndshenting,
at neste henting hopper til nyeste bilde, at skriving har en tidsgrense og at
gamle/manglende bilder avvises før en strøm åpnes. HTTP-testen kontrollerer
også videresending av bildets sekvensnummer og fangsttid. Dette er simulert
nettverkslast; endelig forsinkelse gjennom Internett må fremdeles måles.

Videoforbedringen er installert som
`edc4f36b334b83221b9d4a87937205db4958c5e3` på begge Pi-er, med verifiserte
manifester og 56 beståtte tester på hver. Kameraenes maskinvarefeil består.

`scripts/check_gateway.py` bruker nå WebSocket-tidsstempler til å anslå en
øvre bildealdersgrense med rapportert klokkeusikkerhet. Målingen starter når
kamerafangsten returnerer og slutter ved mottatt JPEG. Sensorens eksponering
og nettleserens skjermvisning inngår ikke. Målingen krever fungerende kameraer.

0. **Kameraer:** begge sensorer må bli oppdaget igjen, deretter må uavhengig
   fangst og begge videostrømmer prøves med virkelige bilder.

1. **Geometri og full kartlegging:** LiDAR-vinkel, bilens sikkerhetsradius og
   eventuelle faste skygger må kalibreres. Kartet fra én plassering er ikke
   et kart over hele leiligheten. Avstander må sammenlignes med fysiske mål.
2. **Autonomi:** go-to, utforsking, gjenlokalisering etter flytting/rotasjon og
   vaktrunder er implementert, men ikke kjørt fysisk. Begge autonomiflagg og
   kalibreringsflagget forblir av. Motorene er i tillegg sperret under kabling.
3. **Batteriforsyning:** vanlig strøm gir nå normal Pi-forsyning. Tidligere
   batteridrift ga aktiv lav spenning og struping; Pi 5 målte ca. 4,72–4,80 V,
   avhengig av last. Omformer, kabler og forsyning under last må kontrolleres
   før stabil mobil drift kan bekreftes. Ingen batteriprosent er tilgjengelig.
4. **Ekstern kjøring:** HTTPS og innloggingssiden er bekreftet utenfra.
   Innlogget video, WebSocket og kart er bekreftet via domenet fra LAN. Faktisk
   videoalder og styreforsinkelse fra mobilnett gjenstår å måle; kjøring og
   stopp ved nettbrudd må prøves med person ved bilen og uten strømkabler.
5. **GitHub-publisering:** repository finnes og kan leses, men forsøk på å
   opprette arbeidsgrenen via GitHub-koblingen ga 403, «Resource not accessible
   by integration». Installasjonslisten mangler appinstallasjon for
   `lassenygard`, som eier repoet. Ingen vellykket push er dokumentert ennå.

Programvaretestene erstatter ikke disse fysiske og eksterne kontrollene.
