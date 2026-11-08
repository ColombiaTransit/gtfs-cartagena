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
- Complementaria: C001 Ciudadela 2000–Manga, C017, C018 Bodeguita–Torices (circulair, sinds 6 aug 2024), C106 Bodeguita–Zona Norte (ook als C016 genoemd – nagaan).
- 2025: route Ciudadela La Paz. Gepland: Castillogrande–Laguito, Parque Heredia, Mamonal.
- Overstappen tussen routes zonder extra kosten (o.a. bij Bodeguita en Parque de la Marina).

## Dienstregeling (algemeen)
- Werkdag: troncal/pretroncal 05:00–21:00; alimentadoras tot 22:30.
- Zaterdag: troncal/pretroncal 05:30–20:30; alimentadoras 05:00–22:00 (C001 tot 21:30).
- Zon-/feestdag: troncal/pretroncal 06:00–20:00; alimentadoras vanaf 05:00/05:30 tot ~21:30.
- Frequenties per route: nog niet gevonden; de paradero-dataset heeft mogelijk vertrektijden (zie hieronder).

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
- C016 of C106 voor Bodeguita–Zona Norte?
