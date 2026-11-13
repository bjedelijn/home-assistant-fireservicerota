"""Anonymous human-readable labels; no real dispatch or personnel data."""

from custom_components.fireservicerota.fairness_vehicle_display import describe_task_vehicle


def mapping(station=194, task=7674, number="042330"):
    return {
        "station_id": station, "task_id": task, "vehicle_number": number,
        "source": "verified_current_station_task_vehicle",
        "verified_current": True,
        "unique_task_vehicle_association": True,
    }


def describe(**kwargs):
    return describe_task_vehicle(
        station_id=194, task_id=7674, task_name="TS", **kwargs,
    )


def test_no_verified_mapping_uses_task_name_without_guessing():
    actual = describe()
    assert actual["display_label"] == "TS"
    assert actual["display_vehicle_number"] is None
    assert actual["display_status"] == "task_only_vehicle_unverified"


def test_verified_mapping_creates_readable_label():
    actual = describe(verified_mapping=mapping())
    assert actual["display_label"] == "TS 04-2330"
    assert actual["original_vehicle_number"] == "04-2330"
    assert not actual["replacement_applied"]


def test_replacement_is_shown_but_original_retained():
    actual = describe(
        verified_mapping=mapping(),
        active_replacements=[{
            "station_id": 194, "original_vehicle_number": "042330",
            "vehicle_number": "041037", "end_time": None,
        }],
    )
    assert actual["display_label"] == "TS 04-1037"
    assert actual["original_vehicle_number"] == "04-2330"
    assert actual["replacement_applied"] is True


def test_other_station_replacement_cannot_leak():
    actual = describe(
        verified_mapping=mapping(),
        active_replacements=[{
            "station_id": 3853, "original_vehicle_number": "042330",
            "vehicle_number": "041037", "end_time": None,
        }],
    )
    assert actual["display_label"] == "TS 04-2330"


def test_cross_station_mapping_refused():
    actual = describe(verified_mapping=mapping(station=3853))
    assert actual["display_label"] == "TS"
    assert not actual["vehicle_mapping_verified"]


def test_cross_task_mapping_refused():
    actual = describe(verified_mapping=mapping(task=7001))
    assert actual["display_label"] == "TS"


def test_p2000_filter_only_mapping_refused():
    m = mapping()
    m["source"] = "p2000_required_message_term"
    actual = describe(verified_mapping=m)
    assert actual["display_label"] == "TS"


def test_unverified_or_nonunique_mapping_refused():
    m = mapping()
    m["unique_task_vehicle_association"] = False
    assert describe(verified_mapping=m)["display_label"] == "TS"
    m["unique_task_vehicle_association"] = True
    m["verified_current"] = False
    assert describe(verified_mapping=m)["display_label"] == "TS"


def test_conflicting_active_replacements_fail_closed():
    actual = describe(
        verified_mapping=mapping(),
        active_replacements=[
            {"station_id": 194, "original_vehicle_number": "042330",
             "vehicle_number": "041037", "end_time": None},
            {"station_id": 194, "original_vehicle_number": "042330",
             "vehicle_number": "041038", "end_time": None},
        ],
    )
    assert actual["display_label"] == "TS"
    assert actual["display_status"] == "ambiguous_active_replacement"


def test_ended_replacement_not_applied():
    actual = describe(
        verified_mapping=mapping(),
        active_replacements=[{
            "station_id": 194, "original_vehicle_number": "042330",
            "vehicle_number": "041037", "end_time": "2026-11-11T12:00:00+01:00",
        }],
    )
    assert actual["display_label"] == "TS 04-2330"


def test_malformed_vehicle_does_not_display_number():
    m = mapping(number="1234")
    assert describe(verified_mapping=m)["display_label"] == "TS"


def test_task_label_keeps_task_specific_name():
    actual = describe_task_vehicle(
        station_id=194, task_id=7001, task_name="WTS",
        verified_mapping=None,
    )
    assert actual["display_label"] == "WTS"
