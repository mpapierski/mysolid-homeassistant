"""Fixtures for the MySolid integration tests."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.camera import Camera as HaCamera
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.mysolid as mysolid_integration
from custom_components.mysolid import camera as camera_platform
from custom_components.mysolid.const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    DOMAIN,
    REGION_PL,
)
from custom_components.mysolid.models import (
    AccessToken,
    Address,
    Camera,
    CameraChannel,
    MySolidSnapshot,
    PropertyDetails,
    PropertySnapshot,
    RelaySnapshot,
    Session,
)
from custom_components.mysolid.push import FirebaseInstallation, PushCredentials
from custom_components.mysolid.storage import StoredState

HOST = "https://mysolid.solidsecurity.pl/"
EMAIL = "user@example.com"
PASSWORD = "secret"
DEVICE_ID = "ANDROID_ID#0123456789abcdef"
DEVICE_NAME = "Home Assistant"
PROPERTY_ID = 101644565
TRANSMITTER_ID = 1111
RELAY_NUMBER = 1
SWITCH_RELAY_NUMBER = 2


def build_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"MySolid ({EMAIL})",
        unique_id=f"{HOST.lower()}|{EMAIL}",
        data={
            "host": HOST,
            CONF_REGION: REGION_PL,
            CONF_EMAIL: EMAIL,
            CONF_PASSWORD: PASSWORD,
            CONF_DEVICE_ID: DEVICE_ID,
            CONF_DEVICE_NAME: DEVICE_NAME,
            "push_enabled": True,
            "poll_interval_seconds": 60,
            "push_reconnect_seconds": 30,
        },
    )


def build_snapshot(
    *,
    armed: bool = False,
    include_alarm_relay: bool = True,
    include_switch_relay: bool = True,
    include_active_alarm: bool = True,
) -> MySolidSnapshot:
    raw_camera = {
        "serialNumber": "CAM-1",
        "address": "192.168.1.10",
        "username": "camera-user",
        "password": "camera-pass",
        "rstpPort": "554",
        "protocol": "BCSVIEW",
        "channels": [{"name": "Front gate", "number": 1, "ptz": False}],
    }
    property_details = PropertyDetails(
        id=PROPERTY_ID,
        name="Home",
        external_id="ABCD1234",
        address=Address(
            city="Warsaw",
            street="Example",
            number="1",
            code="00-001",
        ),
        armed=armed,
        convoys_enabled=True,
        cameras_enabled=True,
        cameras=(
            Camera(
                serial_number="CAM-1",
                address="192.168.1.10",
                username="camera-user",
                password="camera-pass",
                rtsp_port="554",
                protocol="BCSVIEW",
                channels=(CameraChannel(name="Front gate", number=1, ptz=False),),
            ),
        ),
        raw={
            "id": PROPERTY_ID,
            "name": "Home",
            "externalId": "ABCD1234",
            "address": {
                "city": "Warsaw",
                "street": "Example",
                "number": "1",
                "code": "00-001",
            },
            "armed": armed,
            "convoysEnabled": True,
            "camerasEnabled": True,
            "cameras": [raw_camera],
        },
    )
    relays: list[RelaySnapshot] = []
    if include_alarm_relay:
        relays.append(
            RelaySnapshot(
                account_id=PROPERTY_ID,
                transmitter_id=TRANSMITTER_ID,
                relay_number=RELAY_NUMBER,
                label="Alarm",
                state="ARM" if armed else "DISARM",
                requested_state="ARM" if armed else "DISARM",
                change_status="SUCCESS",
                state_set="ARM3",
                relay_pin_confirmation=True,
            )
        )
    if include_switch_relay:
        relays.append(
            RelaySnapshot(
                account_id=PROPERTY_ID,
                transmitter_id=TRANSMITTER_ID,
                relay_number=SWITCH_RELAY_NUMBER,
                label="Gate",
                state="ON",
                requested_state="ON",
                change_status="SUCCESS",
                state_set="ON_OFF",
                relay_pin_confirmation=False,
            )
        )
    property_snapshot = PropertySnapshot(
        details=property_details,
        relays=tuple(relays),
        active_alarms=(
            (
                {
                    "eventId": 444444,
                    "group": "ALARM",
                    "label": "Intrusion",
                },
            )
            if include_active_alarm
            else ()
        ),
        authorized_users=(
            {
                "id": 777,
                "name": "Jan",
            },
        ),
        schedule={"schedule": {"ranges": [], "specialRanges": []}},
        suspensions=(
            {
                "eventSuspensionId": 123,
                "archived": False,
            },
        ),
    )
    return MySolidSnapshot(
        client_id=123456,
        permissions=frozenset({"AUTHORIZED_USERS", "EVENT_SUSPENSION", "CAMERAS"}),
        properties={PROPERTY_ID: property_snapshot},
        push_connected=True,
        last_push_title="Alarm updated",
    )


class FakeStore:
    def __init__(self) -> None:
        self.saved_state = StoredState(
            session=Session(
                host=HOST,
                email=EMAIL,
                device_id=DEVICE_ID,
                device_name=DEVICE_NAME,
                access_token=AccessToken("access-token"),
                firebase_token="firebase-token",
            ),
            push_credentials=PushCredentials(
                android_id=1234,
                security_token=5678,
                registration_token="registration-token",
                installation=FirebaseInstallation(
                    fid="fid",
                    refresh_token="refresh-token",
                    auth_token="auth-token",
                    auth_expires_in="3600s",
                ),
            ),
            persistent_ids=("one", "two"),
        )
        self.removed = False

    async def async_load(self):
        return self.saved_state

    async def async_save(self, state):
        self.saved_state = state

    async def async_remove(self):
        self.removed = True


class FakeClient:
    def __init__(self) -> None:
        self.host = HOST


class FakeRuntimeData:
    def __init__(self, hass, entry: MockConfigEntry, snapshot: MySolidSnapshot) -> None:
        self.hass = hass
        self.entry = entry
        self.client = FakeClient()
        self.store = FakeStore()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._snapshot = snapshot
        self.coordinator = DataUpdateCoordinator(
            hass,
            logging.getLogger(__name__),
            name="mysolid-test",
            config_entry=entry,
            update_method=self._async_update_data,
        )
        self.coordinator.async_request_refresh = AsyncMock()

    async def _async_update_data(self) -> MySolidSnapshot:
        return self._snapshot

    async def async_initialize(self) -> None:
        self.coordinator.async_set_updated_data(self._snapshot)

    async def async_shutdown(self) -> None:
        return None

    def get_property_snapshot(self, property_id: int) -> PropertySnapshot:
        return self._snapshot.properties[property_id]

    def get_relay_snapshot(
        self,
        property_id: int,
        transmitter_id: int,
        relay_number: int,
    ) -> RelaySnapshot:
        for relay in self.get_property_snapshot(property_id).relays:
            if relay.transmitter_id == transmitter_id and relay.relay_number == relay_number:
                return relay
        raise KeyError((property_id, transmitter_id, relay_number))

    async def async_execute_relay(self, **kwargs: Any) -> None:
        self.calls.append(("execute_relay", kwargs))

    async def async_create_suspension(self, **kwargs: Any) -> None:
        self.calls.append(("create_suspension", kwargs))


@pytest.fixture
def runtime_fixture(hass, monkeypatch):
    runtime: FakeRuntimeData | None = None

    def _factory(snapshot: MySolidSnapshot | None = None) -> FakeRuntimeData:
        nonlocal runtime
        runtime = FakeRuntimeData(hass, build_entry(), snapshot or build_snapshot())
        return runtime

    return _factory


@pytest.fixture
def patch_runtime(hass, monkeypatch):
    snapshot = build_snapshot()
    runtime = FakeRuntimeData(hass, build_entry(), snapshot)

    def _build_runtime(_hass, entry):
        runtime.entry = entry
        return runtime

    monkeypatch.setattr("custom_components.mysolid.build_runtime", _build_runtime)
    return runtime


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    return build_entry()


@pytest.fixture
def config_flow_login(monkeypatch):
    login = AsyncMock()
    monkeypatch.setattr("custom_components.mysolid.config_flow.generate_device_id", lambda: DEVICE_ID)
    monkeypatch.setattr("custom_components.mysolid.config_flow.default_device_name", lambda: DEVICE_NAME)
    monkeypatch.setattr("custom_components.mysolid.config_flow.MySolidClient.login", login)
    return login


@pytest.fixture(autouse=True)
def patch_supported_platforms(monkeypatch):
    monkeypatch.setattr(
        mysolid_integration,
        "PLATFORMS",
        ["alarm_control_panel", "camera", "sensor", "switch"],
    )

    original_camera_init = camera_platform.MySolidCameraEntity.__init__

    def _patched_camera_init(self, *args, **kwargs):
        original_camera_init(self, *args, **kwargs)
        HaCamera.__init__(self)

    monkeypatch.setattr(camera_platform.MySolidCameraEntity, "__init__", _patched_camera_init)
