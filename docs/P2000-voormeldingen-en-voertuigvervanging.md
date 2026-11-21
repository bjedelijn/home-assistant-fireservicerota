# P2000-voormeldingen en voertuigvervanging (Draft PR #23)

Deze branch bouwt voort op Draft PR #22. **Nog niet mergen of als productie-beta installeren** voordat de realtime BrandweerRooster-veldstructuur en de bestaande HA-nachtautomatiseringen zijn getest.

## Optionele P2000-voormelding

- De Extended-opties bevatten `p2000_prealert_enabled` (standaard uit) en `p2000_prealert_capcodes` (zevencijferige post-/persoonlijke capcodes, komma-gescheiden).
- Een recente P2000-melding met exact ingestelde capcode publiceert het HA-event `fireservicerota_p2000_prealert` met `status: unconfirmed` en `personal_dispatch_confirmed: false`.
- Er wordt geen persoonlijke inzet aangenomen en **geen** TTS, Telegram of HA-push vanuit dit event automatisch verzonden.
- Als BrandweerRooster al eerder een *herkenbaar hetzelfde incident* heeft geleverd, wordt de P2000-voormelding overgeslagen. Per provider-event-ID bestaat deduplicatie tijdens de lopende sessie; daarnaast worden vrijwel gelijktijdige identieke teksten van verschillende bronnen maximaal 90 seconden samengevoegd. Dit raakt nooit de definitieve BWR-alarmering.

### Nachtelijke spraak

Een **niet automatisch geïnstalleerd** YAML-voorbeeld staat in [`docs/examples/p2000_prealert_tts_ha.yaml`](examples/p2000_prealert_tts_ha.yaml). Het volgt de bestaande lokale Brandweer V2.2.7-beta-regels: 07:00–23:00 normaal, 23:00–07:00 uitsluitend als het actuele Gramsbergen-voertuig letterlijk in de P2000-tekst staat, `binary_sensor.dienst_gramsbergen` aan is en `binary_sensor.niet_storen` uit is. De centrale `script.brandweer_centrale_tts_wachtrij_v2_2` verzorgt vervolgens dezelfde speakers en nachtvolumes. De slaapkamerhelpers blijven werkzaam via dat script.

**Dit voorbeeld is niet geïnstalleerd, niet end-to-end getest en heeft nog geen persistente deduplicatie over herstarts.** Gebruik het niet als productie-alarmering; laat de bestaande definitieve BrandweerRooster-oproep ongemoeid.

## Voertuigvervanging

In `fireservicerota.set_replacement_vehicle` is `vehicle_function` optioneel toegevoegd (bijvoorbeeld `TS`, `TS-BT` of `WTS`). Bestaande vervangingen zonder functie blijven geldig; voor een automatische vergelijking wordt geen functie gegokt. De historische opslag legt `end_reason` en `end_incident_id` vast wanneer er na bevestiging automatisch is opgeheven.

De monitor `bwr_vehicle_monitor.ReplacementVehicleMonitor` volgt **alleen** live BrandweerRooster-WebSocket-updates met expliciete en geverifieerde voertuiggegevens van de juiste post/functie. Historische REST-reads, `task_ids`, `resolved_tasks` en vrijetekst-nummers zijn hiervoor onvoldoende. Op dit moment verwacht de monitor een nog **niet aan de echte BWR API getoetste** structuur `dispatched_vehicles` met `confirmed: true`, `station_id`, `vehicle_number` en `vehicle_function`. Zonder deze aantoonbare gegevens doet de monitor **niets**, ook als de opties aanstaan.

Beslissingen bij een unieke actieve vervanging voor dezelfde post/functie:

| BWR daadwerkelijk voertuig | Gecorreleerde P2000 | Actie |
| --- | --- | --- |
| Ingestelde vervanger | Willekeurig | Geen afwijking |
| Oorspronkelijk | Alleen oorspronkelijk, recent | Automatisch opheffen, alleen indien ingeschakeld |
| Oorspronkelijk | Vervanger of beide vermeld | Behouden; geen automatische opheffing |
| Oorspronkelijk | Geen bevestiging binnen 120 s | Stille waarschuwing indien ingeschakeld; behouden |
| Derde voertuig | Willekeurig | Stille waarschuwing indien ingeschakeld; behouden |
| Onbekend / oud / andere post / meerdere vergelijkbare voertuigen | Willekeurig | Geen automatische actie |

Bij opheffen wordt de exacte actieve vervanger inclusief starttijd gecontroleerd. Een intussen handmatig gewijzigde vervanging kan daardoor niet door oude informatie worden opgeheven.

### Stille notificaties

- `replacement_alerts_enabled` is standaard uit.
- `replacement_alert_channel` kiest Telegram, Home Assistant-push of beide.
- Voor geselecteerde kanalen is een geldige `notify.*`-entiteit verplicht.
- Telegram Bot wordt via `telegram_bot.send_message` met `disable_notification: true` verstuurd. Mobiele Home Assistant-push gebruikt `notify.send_message` met iOS `interruption-level: passive`. Er wordt geen sirene, TTS of media player geactiveerd.
- Per incident, post, oorspronkelijk voertuig en afwijkingsreden wordt een waarschuwing in het lopende proces gededupliceerd.
- Bij een derde of onbekend voertuig wordt **nooit** automatisch een nieuwe vervanging ingesteld.

## Diagnose van echte BrandweerRooster-voertuigvelden

Er is een read-only HA-service toegevoegd: **`fireservicerota.get_incident_vehicle_evidence`**. Die leest het nieuwste bekende incident (of een opgegeven `incident_id`) en retourneert alleen paden van voertuigachtige velden en exacte zes-cijferige nummers. Namen, telefoons, adressen, ruwe P2000-tekst en tokens worden niet meegestuurd.

Gebruik in Ontwikkelaarstools → Acties:

```yaml
action: fireservicerota.get_incident_vehicle_evidence
data: {}
```

Het antwoord bevat `incident_id`, `rest` en `websocket`. Binnen `rest` en (indien het laatst ontvangen incident-ID gelijk is) `websocket` staan de diagnostische `vehicle_fields` en `fields_found`. **Een gevonden nummer is nog geen bewijs van een werkelijk ingezette eenheid.** We moeten de gevonden paden en de BWR-semantiek eerst tegen echte incidenten valideren voor de automatische controle geactiveerd kan worden.

## Validatie vóór release

1. Betrouwbaar BWR-voertuigveld inclusief post en functie vaststellen via diagnostiek; daadwerkelijke WebSocket-gegevens testen, zo nodig monitor-schema aanpassen.
2. P2000-correlation valideren voor zowel vervanger als origineel, inclusief herhaalde en onvolledige updates.
3. Tests draaien voor rolconflicten, dubbele incidenten, gewijzigde vervangingen, tijdvenster, herstart en ontbrekende P2000-data.
4. De huidige Home Assistant-automatiseringen `brandweer.yaml` / `brandweer_paraat.yaml` nalopen en hun exacte spraak- en nachtvoorwaarden hergebruiken in de eventuele voormeldings-automatisering.
5. GitHub CI, HACS, Hassfest, CodeQL en tests groen; daarna eerst gecontroleerde beta.

**PR #23 blijft Draft.** De bestaande GitHub Actions-workflows valideren uitsluitend pull requests naar `extended`. Daarom toont deze gestapelde PR tegen de P2000-featurebranch nog geen eigen CI-runs. Zodra PR #22 gemerged en PR #23 naar `extended` gericht kan worden, moeten de normale CI-, HACS-, Hassfest- en CodeQL-controles opnieuw draaien.

## CI van gestapelde branch

Omdat PR #23 nog op de P2000-featurebranch is gebaseerd, zijn de PR-triggered checks voor deze PR niet zichtbaar. De push-triggers voor de **feature/replacement-reconciliation-prealerts** branch zijn daarom tijdelijk aan de GitHub Actions-workflows toegevoegd. De GitHub-koppeling kan enkel pull-request-triggered runs per SHA ophalen; hierdoor kunnen push-runs nog niet zelfstandig via die route worden bevestigd. Deze extra push-triggers moeten na samenvoegen worden verwijderd.
