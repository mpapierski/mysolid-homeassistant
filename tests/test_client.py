from __future__ import annotations

import json

import pytest

from custom_components.mysolid.api import MySolidClient
from custom_components.mysolid.models import AccessToken


class FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._text = payload if isinstance(payload, str) else json.dumps(payload)

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_login_updates_session() -> None:
    fake_session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "value": "token-123",
                    "expiration": "2026-03-16T12:34:56Z",
                },
            )
        ]
    )
    client = MySolidClient(session=fake_session)

    session = await client.login("user@example.com", "secret")

    assert session.email == "user@example.com"
    assert session.access_token is not None
    assert session.access_token.value == "token-123"
    sent = fake_session.requests[0]
    assert sent["method"] == "POST"
    assert sent["url"].endswith("/api/authorization")
    assert sent["json"] == {
        "email": "user@example.com",
        "password": "secret",
        "deviceId": client.session.device_id,
        "deviceName": client.session.device_name,
    }


@pytest.mark.asyncio
async def test_get_property_details_parses_typed_response() -> None:
    fake_session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "clientId": 123,
                    "propertyDetails": [
                        {
                            "id": 456,
                            "name": "Home",
                            "externalId": "ABC123",
                            "address": {
                                "state": "MAZOWIECKIE",
                                "code": "00-001",
                                "city": "Warszawa",
                                "street": "Przykladowa",
                                "number": "1",
                            },
                            "armed": True,
                            "convoysEnabled": True,
                            "camerasEnabled": False,
                            "cameras": [],
                        }
                    ],
                },
            )
        ]
    )
    client = MySolidClient(
        email="user@example.com",
        access_token=AccessToken("token-123"),
        session=fake_session,
    )

    response = await client.get_property_details()

    assert response.client_id == 123
    assert len(response.properties) == 1
    assert response.properties[0].id == 456
    assert response.properties[0].armed is True
    assert response.properties[0].address is not None
    assert response.properties[0].address.city == "Warszawa"


@pytest.mark.asyncio
async def test_authenticated_requests_include_mobile_headers() -> None:
    fake_session = FakeSession([FakeResponse(200, ["CAMERAS", "AUTHORIZED_USERS"])])
    client = MySolidClient(
        email="user@example.com",
        access_token=AccessToken("token-123"),
        device_id="ANDROID_ID#deadbeefdeadbeef",
        device_name="ha-host",
        session=fake_session,
    )

    permissions = await client.get_permissions()

    assert permissions == {"CAMERAS", "AUTHORIZED_USERS"}
    headers = fake_session.requests[0]["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "token-123"
    assert headers["UserEmail"] == "user@example.com"
    assert headers["CurrentAppPhoneDeviceId"] == "ANDROID_ID#deadbeefdeadbeef"
