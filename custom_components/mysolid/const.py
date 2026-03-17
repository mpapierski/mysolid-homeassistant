from __future__ import annotations

from typing import Final

from .constants import CZECH_HOST, POLISH_HOST

DOMAIN = "mysolid"

PLATFORMS: Final = [
    "alarm_control_panel",
    "binary_sensor",
    "camera",
    "sensor",
    "switch",
]

CONF_REGION = "region"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_PUSH_ENABLED = "push_enabled"
CONF_POLL_INTERVAL_SECONDS = "poll_interval_seconds"
CONF_PUSH_RECONNECT_SECONDS = "push_reconnect_seconds"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"

REGION_CUSTOM = "custom"
REGION_PL = "pl"
REGION_CS = "cs"
REGION_HOSTS: Final[dict[str, str]] = {
    REGION_PL: POLISH_HOST,
    REGION_CS: CZECH_HOST,
}

DEFAULT_REGION = REGION_PL
DEFAULT_PUSH_ENABLED = True
DEFAULT_POLL_INTERVAL_SECONDS = 60
DEFAULT_PUSH_RECONNECT_SECONDS = 30
MIN_POLL_INTERVAL_SECONDS = 15
MAX_POLL_INTERVAL_SECONDS = 900
MIN_PUSH_RECONNECT_SECONDS = 5
MAX_PUSH_RECONNECT_SECONDS = 300

ATTR_ENTRY_ID = "entry_id"
ATTR_PROPERTY_ID = "property_id"
ATTR_TRANSMITTER_ID = "transmitter_id"
ATTR_RELAY_NUMBER = "relay_number"
ATTR_STATE = "state"
ATTR_PIN = "pin"
ATTR_EVENT_ID = "event_id"
ATTR_AMBER_ID = "amber_id"
ATTR_ALARM_TYPE = "alarm_type"
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_DURATION_MILLISECONDS = "duration_milliseconds"
ATTR_TARGET = "target"
ATTR_PARTITION_NUMBER = "partition_number"
ATTR_SCHEDULE_BEFORE = "schedule_before"
ATTR_SCHEDULE_AFTER = "schedule_after"
ATTR_RANGES = "ranges"
ATTR_SUSPEND_FROM = "suspend_from"
ATTR_SUSPEND_UNTIL = "suspend_until"
ATTR_EVENT_SUSPENSION_ID = "event_suspension_id"
ATTR_AUTHORIZED_USER_ID = "authorized_user_id"
ATTR_ORDERED_IDS = "ordered_ids"
ATTR_ROLE_ID = "role_id"
ATTR_NAME = "name"
ATTR_SURNAME = "surname"
ATTR_NUMBER = "number"
ATTR_COMMENT = "comment"
ATTR_PHONES_LIST = "phones_list"
ATTR_EMAIL_VALUE = "email_value"
ATTR_TEMPORARY = "temporary"
ATTR_ACTIVE_FROM = "active_from"
ATTR_ACTIVE_TO = "active_to"
ATTR_SOON_TO_EXPIRE = "soon_to_expire"

SERVICE_REFRESH = "refresh"
SERVICE_REPORT_ALARM = "report_alarm"
SERVICE_CANCEL_ALARM = "cancel_alarm"
SERVICE_CONFIRM_ALARM = "confirm_alarm"
SERVICE_REPORT_AMBER = "report_amber"
SERVICE_CANCEL_AMBER = "cancel_amber"
SERVICE_EXECUTE_RELAY = "execute_relay"
SERVICE_CREATE_SUSPENSION = "create_suspension"
SERVICE_DELETE_SUSPENSION = "delete_suspension"
SERVICE_UPDATE_SCHEDULE_RANGE = "update_schedule_range"
SERVICE_SET_SPECIAL_SCHEDULE = "set_special_schedule"
SERVICE_DELETE_SPECIAL_SCHEDULE = "delete_special_schedule"
SERVICE_CREATE_AUTHORIZED_USER = "create_authorized_user"
SERVICE_UPDATE_AUTHORIZED_USER = "update_authorized_user"
SERVICE_DELETE_AUTHORIZED_USER = "delete_authorized_user"
SERVICE_RESET_AUTHORIZED_USER_PASSWORD = "reset_authorized_user_password"
SERVICE_REORDER_AUTHORIZED_USERS = "reorder_authorized_users"

ALARM_STATES_ARMED = {"ARM", "PARTIAL_ARM"}
ALARM_STATES_DISARMED = {"DISARM"}
STATE_SET_WITH_PARTIAL_ARM = "ARM3"


def normalize_host(host: str) -> str:
    normalized = host.strip()
    if not normalized:
        return normalized
    return normalized if normalized.endswith("/") else f"{normalized}/"


def resolve_host(region: str, host: str | None) -> str:
    if region == REGION_CUSTOM:
        if not host:
            raise ValueError("A custom region requires a host.")
        return normalize_host(host)
    return normalize_host(REGION_HOSTS[region])


def config_entry_unique_id(host: str, email: str) -> str:
    return f"{normalize_host(host).lower()}|{email.strip().lower()}"


def property_identifier(entry_unique_id: str, property_id: int | str) -> str:
    return f"property::{entry_unique_id}::{property_id}"


def entity_unique_id(
    entry_unique_id: str,
    property_id: int | str,
    suffix: str,
) -> str:
    return f"{entry_unique_id}::{property_id}::{suffix}"
