# Tijdelijk vervangend voertuig (ontwikkelfunctie)

Een post kan tijdelijk met meerdere andere voertuigen rijden. Iedere koppeling benoemt het oorspronkelijke en het vervangende nummer. De meldkamer alarmeert
het **werkelijke** voertuignummer via P2000. FireServiceRota past dat nummer
nooit aan, maar kan per eigen post vastleggen welk voertuig tijdelijk voor
die post rijdt.

Bijvoorbeeld: de post heeft normaal een ander voertuig, maar een P2000-melding
bevat `04-1034`. Na een expliciete lokale koppeling krijgt de P2000-verrijking
`operational_station_name` met de gekozen post.

## Handmatige Home Assistant-acties

Deze acties zijn alleen beschikbaar op de ontwikkelbranch; **niet op 1.3.3**.
Gebruik voor `station_id` de ID van een eigen actieve post uit de integratie.

```yaml
action: fireservicerota.set_replacement_vehicle
data:
  station_id: 123
  original_vehicle_number: "04-2333"
  vehicle_number: "04-1034"
```

Om dezelfde post weer zonder vervanger te laten werken:

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
niet. Een nieuwe vervanger sluit alleen de vorige koppeling van hetzelfde oorspronkelijke voertuig af; andere voertuigen blijven intact. De mapping wordt
bewaard in Home Assistant storage en blijft bij een herstart beschikbaar.

De actieve koppelingen zijn ook zichtbaar onder het attribuut
`replacement_vehicles` van `sensor.p2000_status` als P2000-verrijking is ingeschakeld.
Na instellen of opheffen wordt deze status direct bijgewerkt.

## Interpretatie van P2000

- `p2000_enrichment.messages` blijft de oorspronkelijke meldkamerdata bevatten.
- `unit_details[].station_name` blijft de originele afleiding uit P2000
  of de Brandbase-cache, als die bestaat.
- `unit_details[].operational_station_name` geeft de tijdelijk gekozen
  operationele post weer bij een expliciet bijpassend voertuignummer.
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
