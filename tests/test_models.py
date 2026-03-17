from __future__ import annotations

from datetime import UTC, datetime

from custom_components.mysolid.models import PropertyDetailsResponse, parse_datetime


def test_parse_datetime_accepts_millisecond_epoch() -> None:
    parsed = parse_datetime(1_763_028_896_000)

    assert parsed == datetime.fromtimestamp(1_763_028_896, tz=UTC)


def test_parse_datetime_accepts_numeric_string_epoch() -> None:
    parsed = parse_datetime("1763028896000")

    assert parsed == datetime.fromtimestamp(1_763_028_896, tz=UTC)


def test_property_details_response_accepts_null_collections() -> None:
    response = PropertyDetailsResponse.from_api(
        {
            "clientId": 123,
            "propertyDetails": [
                {
                    "id": 456,
                    "name": "Home",
                    "externalId": "ABC123",
                    "armed": False,
                    "cameras": None,
                },
                {
                    "id": 789,
                    "name": "Office",
                    "externalId": "DEF456",
                    "armed": True,
                    "cameras": [
                        {
                            "serialNumber": "cam-1",
                            "channels": None,
                        }
                    ],
                },
            ],
        }
    )

    assert response.client_id == 123
    assert len(response.properties) == 2
    assert response.properties[0].cameras == ()
    assert len(response.properties[1].cameras) == 1
    assert response.properties[1].cameras[0].channels == ()
