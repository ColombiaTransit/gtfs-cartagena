# Transcaribe (Cartagena) – onderzoeksnotities (8 nov 2026)

## Systeem
- SITM Transcaribe, beheerder TransCaribe S.A.; in bedrijf sinds 17 nov 2015 (eerste maanden gratis).
- Concessionarissen: Sotramac, Transambiental, plus eigen operador (Cartagena Complementaria Social de Indias).
- Corridor (solobús) Av. Pedro de Heredia, ~10,5 km, Patio Portal – La Bodeguita (centrum). 17 estaciones de parada (25 vagones) + estación de transferencia Santa Lucía + Patio Portal.
- Bekende stations: Madre Bernarda (El Gallo), La Castellana, Los Ejecutivos, Cuatro Vientos, María Auxiliadora, Bazurto, Las Delicias, La Popa, El Prado, Chambacú, Centro, La Bodeguita.
- Nov 2025: 25 routes (4 troncales, 6 pretroncales, 11 alimentadoras, 4 complementarias), dekking ~60% van de stad.

## Routecodes (uit nieuwsberichten)
- Troncal: T100E, T101, T102 Portal–Crespo (via Av. Santander), T103 (Bocagrande).
- Pretroncal: X101–X106 (X102 Portal–Bosque–Centro; X103 El Rodeo–…–Bodeguita; X106 met verlenging naar Gobernación).
- Alimentador: A101, A102, A107, A108, A111, A114, A117 e.a.
- Complementaria: C001 Ciudadela 2000–Manga, C017, C018 Bodeguita–Torices (circulair, sinds 6 aug 2024), C017 Bodeguita–Zona Norte (sinds 12 feb 2024). C016 is Portal–Terminal de Transportes; "C106" en "X016" in nieuwsbericht 6077 zijn tikfouten voor C017 en X106.
- Alimentador A118 Portal–Ciudadela de la Paz sinds 27 okt 2025 (25e route), dagelijks; haltes in nieuwsbericht 7309.
- 2025: route Ciudadela La Paz. Gepland: Castillogrande–Laguito, Parque Heredia, Mamonal.
- Overstap: gratis binnen 90 minuten tussen routes in dezelfde richting, met hetzelfde betaalmiddel (Transcaribe, "Todo lo que debes saber para pagar tu pasaje en TransCaribe con tu tarjeta VISA", 2026; geen maximum genoemd). In 2020: "cuatro transbordos permitidos en el mismo sentido hasta en 90 minutos" (bericht 1096). In de feed: `fare_transfer_rules.txt`.
- Overstappen tussen routes zonder extra kosten (o.a. bij Bodeguita en Parque de la Marina).

## Dienstregeling (algemeen)
- Werkdag: troncal/pretroncal 05:00–21:00; alimentadoras tot 22:30.
- Zaterdag: troncal/pretroncal 05:30–20:30; alimentadoras 05:00–22:00 (C001 tot 21:30).
- Zon-/feestdag: troncal/pretroncal 06:00–20:00; alimentadoras vanaf 05:00/05:30 tot ~21:30.
- Frequenties per route: zie `data/headways_news.csv` (met bron per regel). Alleen oude cijfers: A102 (jan 2022, per tijdvak), A101 (2019), X102 (2018), wijzigingen van nov 2021 (A101, A107, A114, A117, X105, X106, T102) en C017 (2024, 20 min, 4 padrones). Recente headways zijn niet gepubliceerd; in 2024 reed het systeem 60–90% van de geplande ritten (bericht 6087). Ontwerpnorm: 2 min minimaal, max 8 min spits, 15 min dal.
- Feestdagen en omleidingen: zie `data/service_changes_news.csv` (31 dec 2024 t/m nov 2026). Patroon op feestdagen: dagtype zaterdag of zondag; A111, C017, C018 en de X106-verlenging rijden dan niet, op zondagdagtype ook A102 en T100E niet; T100E op zaterdagdagtype tot 13:00. Langlopende omleidingen zonder aangekondigd einde: X103 (sinds 25 nov 2025 en 3 aug 2026, Av. del Consulado) en X104 (sinds 27 jan 2026, Pedro Romero).

## Tarieven 2026
- Algemeen 3.900 COP vanaf 23 jan 2026 (Decreto 017 van 15 jan 2026); 2025: 3.400.
- Tarifa diferencial 2.900 (studenten, ouderen M60+/V55+, beperking) sinds 19 mei 2026, gepersonaliseerde kaart.
- Alleen kaart (geen contant).
- Traditionele bussen (TPC, niet in deze feed): vlak tarief 4.000 (Decreto 0016 van 2026).

## Vloot
- 55 nieuwe bussen uit China (busetón, padrón, articulado), in 2026 geleverd; doel 75. Bussen met consolesysteem voor vlootlocatie (mogelijk later basis voor realtime).
- Nieuwe routes aangekondigd → routedata kan snel verouderen.

## Databronnen
- Open data Cartagena (CC-BY, halfjaarlijks bijgewerkt, laatst 9 dec 2025):
  - *Paradero_Transcaribe 2025.xlsx* (resource 886f50a8-88f0-4e07-9b71-f5bbe4ae7daf). Verwachte velden volgens de scraper: Codigo_Rutas, Rutas, Tipo, Descripcion, Sentido, Horario_{Lunes-Viernes,Sabado,Domingo-Festivo}_Salida{1,2}, Nota, Fecha_Activacion.
  - *Rutas_Transcaribe 2025.xlsx* (resource ab94769a-5f6b-41ad-a5ca-3a4ed8812edf).
  - Niet bereikbaar vanuit de Claude-werkomgeving; ophalen via de GitHub Action.
- Moovit: troncales 8 routes / 47 haltes; pretroncales 12 routes / 181 haltes (ter controle).
- Academisch: Vergel-Tovar et al. 2022, "Mapping the transit network of greater Cartagena with mobile phones" (J. Transport Geography 105): statische GTFS van formeel + informeel net (Mapatón 2019: 28 conventionele busroutes, 26 despachos).
- Geen officiële GTFS gevonden in de Mobility Database.

## Open vragen
- Bevat de paradero-dataset coördinaten en haltevolgorde?
- Is de GTFS van het UTB-onderzoek beschikbaar?
- Frequenties per route; haltelijsten van alimentadoras/complementarias.
- ~~C016 of C106 voor Bodeguita–Zona Norte?~~ C017 (zie boven).
- C016 (Portal–Terminal, alleen spits) is waarschijnlijk opgeheven bij de start van A118 (27 okt 2025): C016 staat tot Semana Santa 2025 in de lijsten van routes die op feestdagen niet rijden, in nov 2025 en nov 2026 niet meer, terwijl C017 en C018 er wel in staan. A118 rijdt vrijwel dezelfde haltes. Niet bevestigd.

## Stations: vagón per route (bericht 6209, 15 okt 2024)
- Las Delicias: vagón A X102 en X105, vagón B X103 en X106.
- Villa Olímpica: vagón A X101 en T102, vagón B T101. X106 stopt er alleen bij grote evenementen.
- Los Ángeles: T102 en sinds 15 okt 2024 ook T103.
- Chambacú: T101, T102, T103, X101, X104 (bericht 8375, mei 2026); tweede vagón in aanbouw.

## C017-traject
De officiële kaart (`raw/web/C017-min.png`) bevestigt bericht 5309: heen door Crespo (Global Center t/m Ferretería Crespo 70), terug door de tunnel van Crespo. De OSM-relatie heeft het omgekeerd. T102 rijdt sinds 25 nov 2024 juist heen door de tunnel (bericht 6277).

## App-API (Mi Bus Transcaribe, 25 nov 2026)
Zie `docs/mibus-transcaribe-api.md`. De app gebruikt de API van M2M Control (klant 1343). Zonder inloggen: alle lijnen met varianten (`allLines`), alle haltes (`allPoints`), per variant de haltes in volgorde met positie langs de route (`bustop`) en de geplande vertrektijden (`departure`, per dag). Getest met A102: 102 resp. 108 vertrekken per richting, 7-12 min.
Besluit: eenmalig een statische feed uit de API bouwen; niet dagelijks verversen, geen realtime voorlopig. Licentie geregeld op 2026-11-26; de feed staat als GitHub-release (`latest` + gedateerd).

