from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any


def _parse_unix_timestamp(value: float) -> datetime | None:
    try:
        if abs(value) >= 100_000_000_000:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return _parse_unix_timestamp(float(value))
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return _parse_unix_timestamp(float(stripped))
    except ValueError:
        pass
    normalized = stripped.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _mapping_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


@dataclass(slots=True, frozen=True)
class AccessToken:
    value: str
    expiration: datetime | None = None

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> AccessToken:
        return cls(
            value=str(payload.get("value", "")),
            expiration=parse_datetime(payload.get("expiration")),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AccessToken:
        return cls(
            value=str(payload.get("value", "")),
            expiration=parse_datetime(payload.get("expiration")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "expiration": self.expiration.isoformat() if self.expiration else None,
        }

    @property
    def is_expired(self) -> bool:
        return self.expiration is not None and datetime.now(tz=UTC) >= self.expiration


@dataclass(slots=True, frozen=True)
class Address:
    state: str | None = None
    code: str | None = None
    city: str | None = None
    street: str | None = None
    number: str | None = None

    @classmethod
    def from_api(cls, payload: Mapping[str, Any] | None) -> Address | None:
        if not isinstance(payload, Mapping) or not payload:
            return None
        return cls(
            state=payload.get("state"),
            code=payload.get("code"),
            city=payload.get("city"),
            street=payload.get("street"),
            number=payload.get("number"),
        )

    def label(self) -> str | None:
        parts = [self.street, self.number, self.code, self.city]
        rendered = ", ".join(part for part in parts if part)
        return rendered or None


@dataclass(slots=True, frozen=True)
class CameraChannel:
    name: str | None = None
    number: int | None = None
    ptz: bool | None = None

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> CameraChannel:
        return cls(
            name=payload.get("name"),
            number=int(payload["number"]) if payload.get("number") is not None else None,
            ptz=payload.get("ptz"),
        )


@dataclass(slots=True, frozen=True)
class Camera:
    serial_number: str | None = None
    address: str | None = None
    port: str | None = None
    username: str | None = None
    password: str | None = None
    channels: tuple[CameraChannel, ...] = ()
    rtsp_port: str | None = None
    protocol: str | None = None

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Camera:
        channels = tuple(
            CameraChannel.from_api(item)
            for item in _mapping_items(payload.get("channels"))
        )
        return cls(
            serial_number=payload.get("serialNumber"),
            address=payload.get("address"),
            port=payload.get("port"),
            username=payload.get("username"),
            password=payload.get("password"),
            channels=channels,
            rtsp_port=payload.get("rstpPort"),
            protocol=payload.get("protocol"),
        )


@dataclass(slots=True, frozen=True)
class PropertyDetails:
    id: int | None = None
    name: str | None = None
    external_id: str | None = None
    address: Address | None = None
    armed: bool | None = None
    convoys_enabled: bool | None = None
    cameras_enabled: bool | None = None
    cameras: tuple[Camera, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> PropertyDetails:
        return cls(
            id=int(payload["id"]) if payload.get("id") is not None else None,
            name=payload.get("name"),
            external_id=payload.get("externalId"),
            address=Address.from_api(payload.get("address")),
            armed=payload.get("armed"),
            convoys_enabled=payload.get("convoysEnabled"),
            cameras_enabled=payload.get("camerasEnabled"),
            cameras=tuple(
                Camera.from_api(item)
                for item in _mapping_items(payload.get("cameras"))
            ),
            raw=dict(payload),
        )

    def updated_from_push(self, payload: Mapping[str, Any]) -> PropertyDetails:
        merged = dict(self.raw)
        merged.update(payload)
        return PropertyDetails.from_api(merged)


@dataclass(slots=True, frozen=True)
class PropertyDetailsResponse:
    client_id: int | None
    properties: tuple[PropertyDetails, ...]
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> PropertyDetailsResponse:
        return cls(
            client_id=int(payload["clientId"])
            if payload.get("clientId") is not None
            else None,
            properties=tuple(
                PropertyDetails.from_api(item)
                for item in _mapping_items(payload.get("propertyDetails"))
            ),
            raw=dict(payload),
        )


@dataclass(slots=True, frozen=True)
class Session:
    host: str
    email: str | None
    device_id: str
    device_name: str
    access_token: AccessToken | None = None
    firebase_token: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Session:
        raw_access_token = payload.get("access_token")
        access_token = None
        if isinstance(raw_access_token, Mapping):
            access_token = AccessToken.from_dict(raw_access_token)
        return cls(
            host=str(payload.get("host", "")),
            email=payload.get("email"),
            device_id=str(payload.get("device_id", "")),
            device_name=str(payload.get("device_name", "")),
            access_token=access_token,
            firebase_token=payload.get("firebase_token"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "email": self.email,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "access_token": self.access_token.to_dict() if self.access_token else None,
            "firebase_token": self.firebase_token,
        }

    @property
    def is_authenticated(self) -> bool:
        return self.access_token is not None and bool(self.access_token.value)


@dataclass(slots=True, frozen=True)
class RelaySnapshot:
    account_id: int
    transmitter_id: int | None = None
    relay_number: int | None = None
    label: str | None = None
    state: str | None = None
    requested_state: str | None = None
    change_status: str | None = None
    change_status_date: datetime | None = None
    relay_type: str | None = None
    state_set: str | None = None
    waiting_for_event: bool = False
    relay_pin_confirmation: bool = False
    icon_name: str | None = None
    icon_name_off: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, account_id: int, payload: Mapping[str, Any]) -> RelaySnapshot:
        relay_number = payload.get("relayNumber", payload.get("number"))
        relay_type = payload.get("type", payload.get("transmitterRelayType"))
        return cls(
            account_id=account_id,
            transmitter_id=int(payload["transmitterId"])
            if payload.get("transmitterId") is not None
            else None,
            relay_number=int(relay_number) if relay_number is not None else None,
            label=payload.get("label"),
            state=payload.get("state"),
            requested_state=payload.get("requestedState"),
            change_status=payload.get("changeStatus"),
            change_status_date=parse_datetime(payload.get("changeStatusDate")),
            relay_type=relay_type,
            state_set=payload.get("stateSet"),
            waiting_for_event=bool(payload.get("waitingForEvent")),
            relay_pin_confirmation=bool(payload.get("relayPinConfirmation")),
            icon_name=payload.get("iconName"),
            icon_name_off=payload.get("iconNameOff"),
            raw=dict(payload),
        )

    @property
    def unique_key(self) -> tuple[int, int | None, int | None]:
        return (self.account_id, self.transmitter_id, self.relay_number)

    @property
    def is_alarm_panel(self) -> bool:
        if self.state_set in {"ARM2", "ARM3"}:
            return True
        states = {self.state, self.requested_state}
        return any(state in {"ARM", "DISARM", "PARTIAL_ARM"} for state in states)

    @property
    def supports_partial_arm(self) -> bool:
        return self.state_set == "ARM3"

    @property
    def is_switch(self) -> bool:
        if self.is_alarm_panel:
            return False
        if self.state_set == "ON_OFF":
            return True
        states = {self.state, self.requested_state}
        return any(state in {"ON", "OFF"} for state in states)

    def with_updates(self, payload: Mapping[str, Any]) -> RelaySnapshot:
        merged = dict(self.raw)
        merged.update(payload)
        return RelaySnapshot.from_api(self.account_id, merged)


@dataclass(slots=True, frozen=True)
class PropertySnapshot:
    details: PropertyDetails
    relays: tuple[RelaySnapshot, ...] = ()
    active_alarms: tuple[dict[str, Any], ...] = ()
    authorized_users: tuple[dict[str, Any], ...] = ()
    schedule: dict[str, Any] | None = None
    suspensions: tuple[dict[str, Any], ...] = ()

    @property
    def active_alarm_count(self) -> int:
        return len(self.active_alarms)

    @property
    def has_active_alarm(self) -> bool:
        return bool(self.active_alarms)

    @property
    def suspension_active(self) -> bool:
        return any(not bool(item.get("archived")) for item in self.suspensions)

    @property
    def authorized_user_count(self) -> int:
        return len(self.authorized_users)

    @property
    def schedule_summary(self) -> str:
        if not self.schedule:
            return "No schedule"
        root_schedule = self.schedule.get("schedule") if isinstance(self.schedule, Mapping) else None
        if not isinstance(root_schedule, Mapping):
            return "No schedule"
        ranges = root_schedule.get("ranges")
        special_ranges = root_schedule.get("specialRanges")
        count = len(ranges) if isinstance(ranges, Sequence) else 0
        special_count = len(special_ranges) if isinstance(special_ranges, Sequence) else 0
        return f"{count} regular, {special_count} special"

    @property
    def suspension_summary(self) -> str:
        active = sum(1 for item in self.suspensions if not bool(item.get("archived")))
        return f"{active} active"

    @property
    def last_alarm_summary(self) -> str | None:
        if not self.active_alarms:
            return None
        current = self.active_alarms[0]
        group = current.get("group")
        label = current.get("label")
        parts = [part for part in (group, label) if part]
        return " | ".join(str(part) for part in parts) or None

    def replace_details(self, details: PropertyDetails) -> PropertySnapshot:
        return replace(self, details=details)

    def replace_relays(self, relays: tuple[RelaySnapshot, ...]) -> PropertySnapshot:
        return replace(self, relays=relays)

    def replace_alarms(self, alarms: tuple[dict[str, Any], ...]) -> PropertySnapshot:
        return replace(self, active_alarms=alarms)

    def replace_authorized_users(
        self,
        authorized_users: tuple[dict[str, Any], ...],
    ) -> PropertySnapshot:
        return replace(self, authorized_users=authorized_users)

    def replace_schedule(self, schedule: dict[str, Any] | None) -> PropertySnapshot:
        return replace(self, schedule=schedule)

    def replace_suspensions(
        self,
        suspensions: tuple[dict[str, Any], ...],
    ) -> PropertySnapshot:
        return replace(self, suspensions=suspensions)


@dataclass(slots=True)
class MySolidSnapshot:
    client_id: int | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    properties: dict[int, PropertySnapshot] = field(default_factory=dict)
    push_connected: bool = False
    push_error: str | None = None
    last_push_title: str | None = None
    last_push_body: str | None = None
    last_push_payload: dict[str, Any] | None = None
    last_push_at: datetime | None = None

    def clone(self) -> MySolidSnapshot:
        return deepcopy(self)

