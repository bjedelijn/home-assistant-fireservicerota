# P2000-voormeldingen en voertuigvervanging (ontwikkeling)

## Status
Deze branch bouwt voort op de p2000.page WebSocket-Draft PR #22.
De twee onderstaande onderdelen zijn **nog niet geschikt voor een productierelease** zolang de integratietests met BrandweerRooster en de lokale Home Assistant-automatiseringen ontbreken.

## Optionele P2000-voormelding
In de Extended-opties:
- Schakel **P2000-voormeldingen** in (standaard uit).
- Vul de relevante **zevencijferige post- of persoonlijke capcodes** in, komma-gescheiden.
- Bij een verse, passende P2000-melding maakt de integratie het Home Assistant-event `fireservicerota_p2000_prealert` aan, met `source`, `external_id`, `event_time`, `received_at`, `message`, `priority`, `capcodes`, `status: unconfirmed`, `personal_dispatch_confirmed: false`.

De integratie verstuurt **geen Telegram, push of spraak** uit dit event. Hiervoor moet eerst een Home Assistant-automatisering worden gemaakt die exact dezelfde nachtvoorwaarden, paraatheidscontrole en Niet-storenregels als de bestaande BrandweerRooster-automatisering gebruikt. Een P2000-voormelding is **nooit** een bevestigde persoonlijke oproep. De definitieve BrandweerRooster-alarmering mag nooit worden onderdrukt.

De events zijn gededupliceerd per P2000 bron-ID in het lopende proces. Er is nog geen duurzame prealert-deduplicatie over herstarts of betrouwbare incidentbrede onderdrukking wanneer BrandweerRooster eerder was. **Daarom nog geen automatische nacht-TTS configureren.**

## Voertuigvervangingen
Nieuwe pure functie: `replacement_reconciliation.evaluate_replacement`.

Invoergegevens:
- Actieve vervanging per post: oorspronkelijk en vervanger
- Actueel, expliciet **geverifieerd BrandweerRooster-voertuig** voor dezelfde post/functie; geen taaklabel of standaardvoertuig
- Live incident-ID en eventtijd ná start van de vervanging
- Eventueel een aantoonbaar gecorreleerde P2000-melding met voertuignummers

Beslissingen:
- BrandweerRooster noemt de ingestelde vervanger: `ignore`.
- BrandweerRooster noemt het oorspronkelijke voertuig én gekoppeld recent P2000 bevestigt dat nummer: `clear` (advies, nog **geen** mutatie).
- BrandweerRooster noemt een derde voertuig: `notify` (advies, nog **geen** notificatie).
- BrandweerRooster/P2000 spreken elkaar tegen of bewijs ontbreekt: `notify`, vervanging behouden.
- Historische/ongeldige gegevens worden genegeerd.

**Nog niet gekoppeld aan een realtime BrandweerRooster-voertuigveld.** De huidige `task_ids` / `resolved_tasks` bewijzen niet zelfstandig welk voertuig daadwerkelijk rijdt. Eerst moeten we uit een live BWR-incident vaststellen welk betrouwbaar veld post, functie en werkelijk voertuig koppelt. Tot die tijd nooit automatisch een vervanging opheffen.

## Volgende vereiste stappen
1. Live BWR-voorbeeld analyseren op voertuig-identiteit, post en taak/functie, zonder persoonsgegevens of tokens in logs.
2. Realtime incidentmatcher aansluiten, P2000-correlation en tolerantie van tijdvensters valideren.
3. Stille afwijkingsnotificatie met configureerbaar Telegram-/HA-pushkanaal en per incident deduplicatie realiseren.
4. Een geverifieerde `clear` pas dan via `ReplacementVehicleStore.async_clear` uitvoeren, met auditbron en incident-ID.
5. Bestaande nachtelijke BrandweerRooster-TTS-condities **hergebruiken** voor optionele voormeldingen, testen voor dag/nacht, niet paraat, niet storen, vervangen voertuig.
6. End-to-end tests uitvoeren en pas dan beta vrijgeven.
