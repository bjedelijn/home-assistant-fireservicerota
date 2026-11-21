# Aanpassing brandweer-paraat bij PR #23

Dit is een **wijzigingsvoorstel**, geen te installeren tweede package en geen wijziging aan de bestaande configuratie. Gemaakt op basis van het door de gebruiker aangeleverde huidige pakket `brandweer_paraat.yaml` versie **1.9 Assist beta.3** (FireServiceRota Extended **1.3.4-beta.2**) en `brandweer.yaml` **V2.2.9**.

## Waarom een expliciete voertuigfunctie?

Het huidige script `script.brandweer_voertuig_vervangen` verstuurt `station_id`, `original_vehicle_number` en `vehicle_number` naar FireServiceRota. Het script kent zelf nog geen voertuigfunctie. PR #23 kan alleen een afwijking voor eenzelfde **post + functie** veilig beoordelen als `vehicle_function` expliciet bij de vervanging is vastgelegd.

Voorstel: voeg binnen het bestaande `input_select:` in `brandweer_paraat.yaml` één helper toe:

```yaml
  brandweer_voertuig_functie:
    name: Brandweer functie vervangend voertuig
    icon: mdi:fire-truck
    options:
      - TS
      - TS-BT
      - WTS
      - WTG
      - RV
      - NBT
      - DB
      - Overig
```

Voeg in de `variables`-stap van het bestaande `script.brandweer_voertuig_vervangen` toe:

```yaml
          voertuig_functie: "{{ states('input_select.brandweer_voertuig_functie') | trim }}"
```

Voeg in de bestaande actie `fireservicerota.set_replacement_vehicle` toe:

```yaml
          vehicle_function: "{{ voertuig_functie if voertuig_functie != 'Overig' else '' }}"
```

Hiermee blijft handmatig instellen en opheffen van vervangingen werken. De automatische controle slaat vervangingen zonder expliciete functie over. De lijst met functies is een **voorbeeld**, geen door BrandweerRooster geverifieerde enumeratie: vóór automatische activatie moeten echte BWR-functiewaarden en velden gevalideerd worden. Vooral `TS` versus `TS-BT` mag niet stilzwijgend als gelijk worden behandeld.

## Actuele nachtvoorwaarden (brandweer.yaml V2.2.9)

- 07:00–23:00: normale voormelding kan op dezelfde audio-wachtrij als een incident, mits P2000-capcode vooraf expliciet is geselecteerd.
- 23:00–07:00: alleen als **het actieve Gramsbergen-voertuig** (van `sensor.brandweer_gramsbergen_actief_voertuig`) in `P2000-event.units` aanwezig is, `binary_sensor.dienst_gramsbergen` aan is en `binary_sensor.niet_storen` uit is.
- `script.brandweer_centrale_tts_wachtrij_v2_2` routeert vanaf 19:30 naar tablet en de via eigen helpers ingeschakelde slaapkamers, met volume 0,35 (avond) / 0,25 (nacht). De slaapkamerschakelaars zijn `input_boolean.brandweer_nachtmelding_slaapkamer_j_b` en `input_boolean.brandweer_nachtmelding_slaapkamer_julian`.
- De **definitieve BWR-automatisering** V2.2.9 gebruikt een nieuw-voertuig-deduplicatie en een betrouwbare tijdsgrens van zes uur. Een losse P2000-voormelding vervangt dit nadrukkelijk niet.

Een los, optioneel voormeldingsvoorbeeld staat in [p2000_prealert_tts_ha.yaml](p2000_prealert_tts_ha.yaml). De huidige werkende `brandweer.yaml` blijft ongewijzigd.

## Stille waarschuwingen

De aangeleverde `brandweer.yaml` gebruikt `telegram_bot.send_message` en de HA mobiele app-notify voor persoonlijke pushes. In PR #23 kan de nieuwe melding zonder TTS worden gericht aan:
- `notify.mobile_app_...` voor gewone HA-push;
- een `notify.telegram...` entiteit **of** een `telegram_bot` configuratie-ID voor de bestaande Telegram Bot-integratie.

Vul de Telegram configuratie-ID alleen lokaal in via de opties. **Neem geen eigen bot-ID, toegangscode, P2000-sleutel of alarmcode over in publieke GitHub-voorbeelden.** De afwijkingsfunctie staat standaard uit.

## Beta-voorwaarden

De gebruiker hoeft zijn beide pakketten **nu niet** te vervangen. Eerst de nieuwe GitHub-tests groen krijgen, daadwerkelijke BWR-`dispatched_vehicles`-gegevens vaststellen, vervolgens de opties gecontroleerd inschakelen. Tot die tijd staan de nieuwe functies standaard uit en PR #23 blijft Draft.
