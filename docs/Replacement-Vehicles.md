# Tijdelijk vervangend voertuig (ontwikkelfunctie)

Een post kan tijdelijk met meerdere andere voertuigen rijden. Iedere koppeling benoemt het oorspronkelijke en het vervangende nummer. De meldkamer alarmeert
het **werkelijke** voertuignummer via P2000. FireServiceRota past dat nummer
nooit aan, maar kan per eigen post vastleggen welk voertuig tijdelijk voor
die post rijdt.

Bijvoorbeeld: de post heeft normaal een ander voertuig, maar een P2000-melding
bevat `04-1034`. Na een expliciete lokale koppeling krijgt de P2000-verrijking
`operational_station_name` met de gekozen post.

## Handmatige Home Assistant-acties

Deze acties zijn beschikbaar in **1.3.4-beta.2**; **niet in stable 1.3.3**. Beta.2 vereist twee voertuignummers bij het instellen en het originele nummer bij het opheffen.
Gebruik voor `station_id` de ID van een eigen actieve post uit de integratie.

```yaml
action: fireservicerota.set_replacement_vehicle
data:
  station_id: 123
  original_vehicle_number: "04-2333"
  vehicle_number: "04-1034"
```

Om **alleen deze ene koppeling** te beëindigen (andere koppelingen van dezelfde post blijven actief):

```yaml
action: fireservicerota.clear_replacement_vehicle
data:
  station_id: 123
  original_vehicle_number: "04-2333"
```

Actieve vervangers uitlezen (actie met antwoord):

```yaml
action: fireservicerota.get_replacement_vehicles
response_variable: replacement_result
```

Het opnieuw instellen van dezelfde vervanger verandert het begindatum/tijdstip
niet. Een nieuwe vervanger sluit alleen de vorige koppeling van hetzelfde oorspronkelijke voertuig af; andere voertuigen blijven intact. De integratie weigert dezelfde vervanger bij een ander oorspronkelijk voertuig (ook bij een andere post) met de foutmelding `Replacement is already assigned to another vehicle`. De mapping wordt
bewaard in Home Assistant storage en blijft bij een herstart beschikbaar.

De actieve koppelingen zijn ook zichtbaar onder het attribuut
`replacement_vehicles` van `sensor.p2000_status` als P2000-verrijking is ingeschakeld.
Na instellen of opheffen wordt deze status direct bijgewerkt.

## Voorbeeld: twee voertuigen op één post

Voer de volgende twee acties afzonderlijk uit (fictieve IDs/nummers):

```yaml
action: fireservicerota.set_replacement_vehicle
data:
  station_id: 123
  original_vehicle_number: "04-0001"
  vehicle_number: "04-1001"
```

```yaml
action: fireservicerota.set_replacement_vehicle
data:
  station_id: 123
  original_vehicle_number: "04-0002"
  vehicle_number: "04-1002"
```

Opheffen van alleen `04-0001` laat de tweede vervanging actief.

### Uitlezen in Home Assistant

```jinja2
{% set records = state_attr('sensor.p2000_status', 'replacement_vehicles') or [] %}
{% for row in records %}
{{ row.station_name }}: {{ row.original_vehicle_number }} -> {{ row.vehicle_number }}
{% else %}
Geen actieve vervangingen
{% endfor %}
```

Het attribuut is beschikbaar als de P2000-statussensor is ingesteld. De actie `get_replacement_vehicles` kan ook zonder die sensor worden gebruikt.

## Interpretatie van P2000

- `p2000_enrichment.messages` blijft de oorspronkelijke meldkamerdata bevatten.
- `unit_details[].station_name` blijft de originele afleiding uit P2000
  of de Brandbase-cache, als die bestaat.
- `unit_details[].operational_station_name` geeft de tijdelijk gekozen
  operationele post weer bij een expliciet bijpassend voertuignummer.
- `unit_details[].original_vehicle_number` vermeldt het originele voertuig (alleen bij een geldige lokale mapping).
- `unit_details[].replacement_vehicle` toont de lokale toewijzing met
  start- en eindmoment en bron `local_station_override`.
- `vehicles[].operational_station_name` biedt dezelfde extra context voor
  dashboards.
- `units` vermeldt het **werkelijke** P2000-voertuignummer. Het normale
  nummer wordt niet als fictief uitgerukt voertuig toegevoegd.

Koppelingen zijn **tijdgebonden**: een P2000-gebeurtenis buiten de actieve
periode mag achteraf niet de nieuw ingestelde post krijgen. Er wordt geen
eigen station gekoppeld als de melding het voertuig niet bevat of geen
betrouwbare gebeurtenistijd heeft.

## Beperkingen

- Alleen voor eigen, actieve station memberships.
- Er kunnen meerdere actieve vervangers per post worden ingesteld, een per oorspronkelijk voertuig. Een vervanger mag niet tegelijkertijd aan twee oorspronkelijke voertuigen gekoppeld zijn.
- Dit is aanvullende lokale interpretatie, geen wijziging in de
  meldkamerregistratie of de BrandweerRooster API.
- Koppeling werkt op P2000-berichten die door de bestaande
  incidentcorrelatie aan een BrandweerRooster-melding zijn verbonden.
  De vervangingsinstelling creëert geen nieuwe incidentmatch op zichzelf.
- Nog valideren op live P2000-berichten, herstarts en meerdere posten vóór release.

Zie ook `docs/examples/Temporary-Replacement-Vehicle-Package.yaml`.

## Upgrade vanaf beta.1

Beta.1 kende geen oorspronkelijk voertuignummer. Dat is niet veilig te raden: actieve oude koppelingen worden bij de eerste start beëindigd, historische gegevens blijven bewaard. Stel de vervangingen na de upgrade opnieuw in met zowel het originele nummer als het vervangende nummer. Bijvoorbeeld: bij post 194 kunnen 04-2350 -> 04-1050 en 04-2360 -> 04-1060 tegelijk actief zijn.

## Automatiseringen: nachtfilters en voertuigidentiteit

Een nachtelijke melding voor **één specifiek oorspronkelijk voertuig** moet niet worden geopend door een willekeurige andere vervanging van dezelfde post. Selecteer de actieve mapping op `original_vehicle_number`, niet alleen op `station_id`.

Dit *voorbeeld* toont uitsluitend de selectielogica. Het stuurt geen TTS, verlichting of alarmsysteem aan. De station-ID's en nummers zijn fictief:

```jinja2
{% set active = state_attr('sensor.p2000_status', 'replacement_vehicles') or [] %}
{% set matches = active
  | selectattr('station_id', 'eq', 123)
  | selectattr('original_vehicle_number', 'eq', '040001')
  | list %}
{% set selected = matches[0].vehicle_number if matches else '040001' %}
{% set p2000 = state_attr('sensor.incidents', 'p2000_enrichment') or {} %}
{% set confirmed = p2000.get('units', []) or [] %}
{{ selected in confirmed }}
```

Toon de daadwerkelijke voertuigidentiteit uit P2000; vervang het uitgerukte voertuignummer niet in de oorspronkelijke incidenttekst. Voeg je bestaande voorwaarden voor paraatheid, Niet storen, nachtvenster en deduplicatie toe in de eigen HA-automatisering. Deze voorwaarden worden niet door het voertuigbeheer ingesteld.

## Compact dashboard

Houd voertuigbeheer los van een specifieke post: één compact Home-dashboardchip en, indien gewenst, één kleine knop in het algemene incidentvenster openen **dezelfde** voertuigbeheer-pop-up. Plaats het formulier alleen in die pop-up, zodat de normale paraatstatuskaart niet hoger wordt.

Zie de [geanonimiseerde dashboardfragmenten](Dashboard-Examples.md) en het [multi-post YAML-voorbeeld](examples/Temporary-Replacement-Vehicle-Package.yaml). De werkelijke dashboardkaarten en lokale packages behoren tot de Home Assistant-configuratie, niet tot de integratie zelf.

## Validatie vóór stable

- Toevoegen, wijzigen, afzonderlijk verwijderen en dubbele vervanger blokkeren: getest via HA-actions/dashboard.
- Actieve mappings zichtbaar via `sensor.p2000_status`: getest.
- CarPlay/TTS-roosteruitspraak en een daadwerkelijke P2000-gebeurtenis met de vervanger: nog end-to-end te bevestigen.
- Laat stable `1.3.3` ongemoeid totdat de aanvullende testen zijn afgerond.
