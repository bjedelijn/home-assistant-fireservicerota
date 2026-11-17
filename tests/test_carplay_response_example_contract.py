"""Guard against accidental unsafe writes in a CarPlay example."""

from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "CarPlay-Per-Station-Incident-Response.yaml"


def test_per_station_example_requires_unambiguous_incident_and_station():
    source = EXAMPLE.read_text(encoding="utf-8")
    for guard in (
        "meldingen | count == 1",
        "laatste_id | string == actuele_id | string",
        "state_attr(response_switch, 'station_id')",
        "post_ok | bool",
        "incident_active",
        "not (geldig | bool)",
        "stop:",
    ):
        assert guard in source


def test_per_station_example_has_both_post_actions_and_no_raw_api_calls():
    source = EXAMPLE.read_text(encoding="utf-8")
    for name in (
        "brandweer_carplay_gramsbergen_opkomen:",
        "brandweer_carplay_gramsbergen_afwijzen:",
        "brandweer_carplay_hardenberg_opkomen:",
        "brandweer_carplay_hardenberg_afwijzen:",
    ):
        assert name in source
    assert "switch.turn_on" in source
    assert "switch.turn_off" in source
    assert "incidents/" not in source
    assert "POST " not in source


def test_example_uses_placeholder_entity_ids_and_warns_about_real_write():
    source = EXAMPLE.read_text(encoding="utf-8")
    assert "VERVANG_MET_ECHTE_GRAMSBERGEN_RESPONSE_SWITCH" in source
    assert "VERVANG_MET_ECHTE_HARDENBERG_RESPONSE_SWITCH" in source
    assert "DO NOT LOAD INTO PRODUCTION" in source
    assert "Controleer de bevestiging in BrandweerRooster" in source
