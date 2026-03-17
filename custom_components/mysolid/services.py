"""Service registration for MySolid."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    ATTR_ACTIVE_FROM,
    ATTR_ACTIVE_TO,
    ATTR_ALARM_TYPE,
    ATTR_AMBER_ID,
    ATTR_AUTHORIZED_USER_ID,
    ATTR_COMMENT,
    ATTR_DURATION_MILLISECONDS,
    ATTR_EMAIL_VALUE,
    ATTR_ENTRY_ID,
    ATTR_EVENT_ID,
    ATTR_EVENT_SUSPENSION_ID,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_NAME,
    ATTR_NUMBER,
    ATTR_ORDERED_IDS,
    ATTR_PARTITION_NUMBER,
    ATTR_PHONES_LIST,
    ATTR_PIN,
    ATTR_PROPERTY_ID,
    ATTR_RANGES,
    ATTR_RELAY_NUMBER,
    ATTR_ROLE_ID,
    ATTR_SCHEDULE_AFTER,
    ATTR_SCHEDULE_BEFORE,
    ATTR_SOON_TO_EXPIRE,
    ATTR_STATE,
    ATTR_SURNAME,
    ATTR_SUSPEND_FROM,
    ATTR_SUSPEND_UNTIL,
    ATTR_TARGET,
    ATTR_TEMPORARY,
    ATTR_TRANSMITTER_ID,
    DOMAIN,
    SERVICE_CANCEL_ALARM,
    SERVICE_CANCEL_AMBER,
    SERVICE_CONFIRM_ALARM,
    SERVICE_CREATE_AUTHORIZED_USER,
    SERVICE_CREATE_SUSPENSION,
    SERVICE_DELETE_AUTHORIZED_USER,
    SERVICE_DELETE_SPECIAL_SCHEDULE,
    SERVICE_DELETE_SUSPENSION,
    SERVICE_EXECUTE_RELAY,
    SERVICE_REFRESH,
    SERVICE_REORDER_AUTHORIZED_USERS,
    SERVICE_REPORT_ALARM,
    SERVICE_REPORT_AMBER,
    SERVICE_RESET_AUTHORIZED_USER_PASSWORD,
    SERVICE_SET_SPECIAL_SCHEDULE,
    SERVICE_UPDATE_AUTHORIZED_USER,
    SERVICE_UPDATE_SCHEDULE_RANGE,
)
from .coordinator import MySolidRuntimeData
from .exceptions import MySolidApiError

TARGET_FIELDS = {
    vol.Optional(ATTR_ENTRY_ID): cv.string,
    vol.Optional(ATTR_PROPERTY_ID): vol.Coerce(int),
}

ENTITY_TARGET_SCHEMA = vol.Schema(TARGET_FIELDS, extra=vol.ALLOW_EXTRA)
RELAY_SERVICE_SCHEMA = vol.Schema(
    {
        **TARGET_FIELDS,
        vol.Required(ATTR_TRANSMITTER_ID): vol.Coerce(int),
        vol.Required(ATTR_RELAY_NUMBER): vol.Coerce(int),
        vol.Required(ATTR_STATE): cv.string,
        vol.Optional(ATTR_PIN): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

REGISTERED_SERVICES = (
    SERVICE_REFRESH,
    SERVICE_REPORT_ALARM,
    SERVICE_CANCEL_ALARM,
    SERVICE_CONFIRM_ALARM,
    SERVICE_REPORT_AMBER,
    SERVICE_CANCEL_AMBER,
    SERVICE_EXECUTE_RELAY,
    SERVICE_CREATE_SUSPENSION,
    SERVICE_DELETE_SUSPENSION,
    SERVICE_UPDATE_SCHEDULE_RANGE,
    SERVICE_SET_SPECIAL_SCHEDULE,
    SERVICE_DELETE_SPECIAL_SCHEDULE,
    SERVICE_CREATE_AUTHORIZED_USER,
    SERVICE_UPDATE_AUTHORIZED_USER,
    SERVICE_DELETE_AUTHORIZED_USER,
    SERVICE_RESET_AUTHORIZED_USER_PASSWORD,
    SERVICE_REORDER_AUTHORIZED_USERS,
)


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        partial(_async_handle_refresh, hass),
        schema=ENTITY_TARGET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REPORT_ALARM,
        partial(_async_handle_report_alarm, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Optional(ATTR_ALARM_TYPE, default="ALARM"): cv.string,
                vol.Optional(ATTR_LATITUDE): vol.Coerce(float),
                vol.Optional(ATTR_LONGITUDE): vol.Coerce(float),
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_ALARM,
        partial(_async_handle_cancel_alarm, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Required(ATTR_EVENT_ID): vol.Coerce(int),
                vol.Optional(ATTR_PIN): cv.string,
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CONFIRM_ALARM,
        partial(_async_handle_confirm_alarm, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Required("event_bundle_id"): vol.Coerce(int),
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REPORT_AMBER,
        partial(_async_handle_report_amber, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Required(ATTR_DURATION_MILLISECONDS): vol.Coerce(int),
                vol.Optional(ATTR_ALARM_TYPE, default="ALARM"): cv.string,
                vol.Optional(ATTR_LATITUDE): vol.Coerce(float),
                vol.Optional(ATTR_LONGITUDE): vol.Coerce(float),
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_AMBER,
        partial(_async_handle_cancel_amber, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Required(ATTR_AMBER_ID): cv.string,
                vol.Optional(ATTR_PIN): cv.string,
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_RELAY,
        partial(_async_handle_execute_relay, hass),
        schema=RELAY_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_SUSPENSION,
        partial(_async_handle_create_suspension, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Required(ATTR_SUSPEND_FROM): cv.string,
                vol.Required(ATTR_SUSPEND_UNTIL): cv.string,
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_SUSPENSION,
        partial(_async_handle_delete_suspension, hass),
        schema=vol.Schema(
            {**TARGET_FIELDS, vol.Required(ATTR_EVENT_SUSPENSION_ID): vol.Coerce(int)},
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_SCHEDULE_RANGE,
        partial(_async_handle_update_schedule_range, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Required(ATTR_TARGET): cv.string,
                vol.Required(ATTR_TRANSMITTER_ID): vol.Coerce(int),
                vol.Required(ATTR_PARTITION_NUMBER): vol.Coerce(int),
                vol.Required(ATTR_SCHEDULE_BEFORE): dict,
                vol.Required(ATTR_SCHEDULE_AFTER): dict,
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SPECIAL_SCHEDULE,
        partial(_async_handle_set_special_schedule, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Required(ATTR_TARGET): cv.string,
                vol.Required(ATTR_TRANSMITTER_ID): vol.Coerce(int),
                vol.Required(ATTR_PARTITION_NUMBER): vol.Coerce(int),
                vol.Required(ATTR_RANGES): list,
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_SPECIAL_SCHEDULE,
        partial(_async_handle_delete_special_schedule, hass),
        schema=vol.Schema(
            {**TARGET_FIELDS, vol.Required("schedule_id"): vol.Coerce(int)},
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_AUTHORIZED_USER,
        partial(_async_handle_create_authorized_user, hass),
        schema=_authorized_user_schema(update=False),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_AUTHORIZED_USER,
        partial(_async_handle_update_authorized_user, hass),
        schema=_authorized_user_schema(update=True),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_AUTHORIZED_USER,
        partial(_async_handle_delete_authorized_user, hass),
        schema=vol.Schema(
            {**TARGET_FIELDS, vol.Required(ATTR_AUTHORIZED_USER_ID): vol.Coerce(int)},
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_AUTHORIZED_USER_PASSWORD,
        partial(_async_handle_reset_authorized_user_password, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Required(ATTR_AUTHORIZED_USER_ID): vol.Coerce(int),
                vol.Required(ATTR_PIN): cv.string,
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REORDER_AUTHORIZED_USERS,
        partial(_async_handle_reorder_authorized_users, hass),
        schema=vol.Schema(
            {
                **TARGET_FIELDS,
                vol.Required(ATTR_ORDERED_IDS): [vol.Coerce(int)],
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )

def async_unregister_services(hass: HomeAssistant) -> None:
    for service in REGISTERED_SERVICES:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


def _authorized_user_schema(*, update: bool) -> vol.Schema:
    schema: dict[Any, Any] = {
        **TARGET_FIELDS,
        vol.Required(ATTR_ROLE_ID): vol.Coerce(int),
        vol.Required(ATTR_NAME): cv.string,
        vol.Required(ATTR_SURNAME): cv.string,
        vol.Optional(ATTR_NUMBER): cv.string,
        vol.Optional(ATTR_COMMENT): cv.string,
        vol.Optional(ATTR_PHONES_LIST, default=[]): list,
        vol.Optional(ATTR_EMAIL_VALUE): cv.string,
        vol.Optional(ATTR_TEMPORARY, default=False): bool,
        vol.Optional(ATTR_ACTIVE_FROM): cv.string,
        vol.Optional(ATTR_ACTIVE_TO): cv.string,
        vol.Optional(ATTR_SOON_TO_EXPIRE, default=0): vol.Coerce(int),
        vol.Optional(ATTR_PIN): cv.string,
    }
    if update:
        schema[vol.Required(ATTR_AUTHORIZED_USER_ID)] = vol.Coerce(int)
    return vol.Schema(schema, extra=vol.ALLOW_EXTRA)


async def _async_handle_refresh(hass: HomeAssistant, call: ServiceCall) -> None:
    runtimes = _resolve_runtimes_from_call(hass, call)
    if not runtimes:
        runtimes = list(hass.data.get(DOMAIN, {}).values())
    for runtime in runtimes:
        await runtime.coordinator.async_request_refresh()


async def _async_handle_report_alarm(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime, property_id = _resolve_runtime_and_property(hass, call)
    await _run_api_call(
        runtime.async_report_alarm(
            property_id=property_id,
            alarm_type=str(call.data.get(ATTR_ALARM_TYPE, "ALARM")),
            latitude=call.data.get(ATTR_LATITUDE),
            longitude=call.data.get(ATTR_LONGITUDE),
        )
    )


async def _async_handle_cancel_alarm(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = _resolve_runtime(hass, call)
    await _run_api_call(
        runtime.async_cancel_alarm(
            event_id=int(call.data[ATTR_EVENT_ID]),
            pin=call.data.get(ATTR_PIN),
        )
    )


async def _async_handle_confirm_alarm(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = _resolve_runtime(hass, call)
    await _run_api_call(
        runtime.async_confirm_alarm(
            event_bundle_id=int(call.data["event_bundle_id"]),
        )
    )


async def _async_handle_report_amber(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime, property_id = _resolve_runtime_and_property(hass, call)
    await _run_api_call(
        runtime.async_report_amber(
            property_id=property_id,
            duration_milliseconds=int(call.data[ATTR_DURATION_MILLISECONDS]),
            alarm_type=str(call.data.get(ATTR_ALARM_TYPE, "ALARM")),
            latitude=call.data.get(ATTR_LATITUDE),
            longitude=call.data.get(ATTR_LONGITUDE),
        )
    )


async def _async_handle_cancel_amber(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = _resolve_runtime(hass, call)
    await _run_api_call(
        runtime.async_cancel_amber(
            amber_id=str(call.data[ATTR_AMBER_ID]),
            pin=call.data.get(ATTR_PIN),
        )
    )


async def _async_handle_execute_relay(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime, property_id = _resolve_runtime_and_property(hass, call)
    await _run_api_call(
        runtime.async_execute_relay(
            property_id=property_id,
            transmitter_id=int(call.data[ATTR_TRANSMITTER_ID]),
            relay_number=int(call.data[ATTR_RELAY_NUMBER]),
            state=str(call.data[ATTR_STATE]),
            pin=call.data.get(ATTR_PIN),
        )
    )


async def _async_handle_create_suspension(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime, property_id = _resolve_runtime_and_property(hass, call)
    await _run_api_call(
        runtime.async_create_suspension(
            property_id=property_id,
            suspend_from=str(call.data[ATTR_SUSPEND_FROM]),
            suspend_until=str(call.data[ATTR_SUSPEND_UNTIL]),
        )
    )


async def _async_handle_delete_suspension(hass: HomeAssistant, call: ServiceCall) -> None:
    runtime = _resolve_runtime(hass, call)
    await _run_api_call(
        runtime.async_delete_suspension(
            event_suspension_id=int(call.data[ATTR_EVENT_SUSPENSION_ID])
        )
    )


async def _async_handle_update_schedule_range(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    runtime, property_id = _resolve_runtime_and_property(hass, call)
    await _run_api_call(
        runtime.async_update_schedule_range(
            property_id=property_id,
            target=str(call.data[ATTR_TARGET]),
            transmitter_id=int(call.data[ATTR_TRANSMITTER_ID]),
            partition_number=int(call.data[ATTR_PARTITION_NUMBER]),
            schedule_before=dict(call.data[ATTR_SCHEDULE_BEFORE]),
            schedule_after=dict(call.data[ATTR_SCHEDULE_AFTER]),
        )
    )


async def _async_handle_set_special_schedule(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    runtime, property_id = _resolve_runtime_and_property(hass, call)
    await _run_api_call(
        runtime.async_set_special_schedule(
            property_id=property_id,
            target=str(call.data[ATTR_TARGET]),
            transmitter_id=int(call.data[ATTR_TRANSMITTER_ID]),
            partition_number=int(call.data[ATTR_PARTITION_NUMBER]),
            ranges=[dict(item) for item in call.data[ATTR_RANGES]],
        )
    )


async def _async_handle_delete_special_schedule(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    runtime = _resolve_runtime(hass, call)
    await _run_api_call(
        runtime.async_delete_special_schedule(schedule_id=int(call.data["schedule_id"]))
    )


async def _async_handle_create_authorized_user(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    runtime, property_id = _resolve_runtime_and_property(hass, call)
    await _run_api_call(
        runtime.async_create_authorized_user(
            property_id=property_id,
            role_id=int(call.data[ATTR_ROLE_ID]),
            name=str(call.data[ATTR_NAME]),
            surname=str(call.data[ATTR_SURNAME]),
            number=call.data.get(ATTR_NUMBER),
            comment=call.data.get(ATTR_COMMENT),
            phones_list=_normalize_mapping_list(call.data.get(ATTR_PHONES_LIST, [])),
            email_value=call.data.get(ATTR_EMAIL_VALUE),
            temporary=bool(call.data.get(ATTR_TEMPORARY, False)),
            active_from=call.data.get(ATTR_ACTIVE_FROM),
            active_to=call.data.get(ATTR_ACTIVE_TO),
            soon_to_expire=int(call.data.get(ATTR_SOON_TO_EXPIRE, 0)),
            pin=call.data.get(ATTR_PIN),
        )
    )


async def _async_handle_update_authorized_user(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    runtime, property_id = _resolve_runtime_and_property(hass, call)
    await _run_api_call(
        runtime.async_update_authorized_user(
            property_id=property_id,
            authorized_user_id=int(call.data[ATTR_AUTHORIZED_USER_ID]),
            role_id=int(call.data[ATTR_ROLE_ID]),
            name=str(call.data[ATTR_NAME]),
            surname=str(call.data[ATTR_SURNAME]),
            number=call.data.get(ATTR_NUMBER),
            comment=call.data.get(ATTR_COMMENT),
            phones_list=_normalize_mapping_list(call.data.get(ATTR_PHONES_LIST, [])),
            email_value=call.data.get(ATTR_EMAIL_VALUE),
            temporary=bool(call.data.get(ATTR_TEMPORARY, False)),
            active_from=call.data.get(ATTR_ACTIVE_FROM),
            active_to=call.data.get(ATTR_ACTIVE_TO),
            soon_to_expire=int(call.data.get(ATTR_SOON_TO_EXPIRE, 0)),
            pin=call.data.get(ATTR_PIN),
        )
    )


async def _async_handle_delete_authorized_user(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    runtime = _resolve_runtime(hass, call)
    await _run_api_call(
        runtime.async_delete_authorized_user(
            authorized_user_id=int(call.data[ATTR_AUTHORIZED_USER_ID])
        )
    )


async def _async_handle_reset_authorized_user_password(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    runtime = _resolve_runtime(hass, call)
    await _run_api_call(
        runtime.async_reset_authorized_user_password(
            authorized_user_id=int(call.data[ATTR_AUTHORIZED_USER_ID]),
            pin=str(call.data[ATTR_PIN]),
        )
    )


async def _async_handle_reorder_authorized_users(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    runtime, property_id = _resolve_runtime_and_property(hass, call)
    await _run_api_call(
        runtime.async_reorder_authorized_users(
            property_id=property_id,
            ordered_ids=[int(item) for item in call.data[ATTR_ORDERED_IDS]],
        )
    )


def _resolve_runtime_and_property(
    hass: HomeAssistant,
    call: ServiceCall,
) -> tuple[MySolidRuntimeData, int]:
    runtime = _resolve_runtime(hass, call)
    property_id = call.data.get(ATTR_PROPERTY_ID)
    if property_id is not None:
        return runtime, int(property_id)

    target = _resolve_target_from_call(hass, call)
    if target is None:
        raise HomeAssistantError("This action requires a property target")
    return target


def _resolve_runtime(hass: HomeAssistant, call: ServiceCall) -> MySolidRuntimeData:
    if ATTR_ENTRY_ID in call.data:
        entry_id = str(call.data[ATTR_ENTRY_ID])
        runtime = hass.data.get(DOMAIN, {}).get(entry_id)
        if runtime is None:
            raise HomeAssistantError("The selected MySolid entry is not available")
        return runtime

    target = _resolve_target_from_call(hass, call)
    if target is not None:
        return target[0]

    entries = list(hass.data.get(DOMAIN, {}).values())
    if len(entries) == 1:
        return entries[0]
    raise HomeAssistantError(
        "Specify entry_id or target one MySolid property device/entity"
    )


def _resolve_runtimes_from_call(
    hass: HomeAssistant,
    call: ServiceCall,
) -> list[MySolidRuntimeData]:
    if ATTR_ENTRY_ID in call.data:
        return [_resolve_runtime(hass, call)]
    target = _resolve_target_from_call(hass, call)
    if target is not None:
        return [target[0]]
    return []


def _resolve_target_from_call(
    hass: HomeAssistant,
    call: ServiceCall,
) -> tuple[MySolidRuntimeData, int] | None:
    device_ids = _normalize_list(call.data.get(ATTR_DEVICE_ID))
    if not device_ids:
        entity_ids = _normalize_list(call.data.get(ATTR_ENTITY_ID))
        if entity_ids:
            entity_registry = er.async_get(hass)
            for entity_id in entity_ids:
                if (
                    entity_entry := entity_registry.async_get(entity_id)
                ) and entity_entry.device_id:
                    device_ids.append(entity_entry.device_id)

    if not device_ids:
        return None
    if len(device_ids) != 1:
        raise HomeAssistantError("Exactly one MySolid property target is required")

    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_ids[0])
    if device is None:
        raise HomeAssistantError("The selected device is no longer available")

    for domain, value in device.identifiers:
        if domain != DOMAIN or not value.startswith("property::"):
            continue
        _, entry_unique_id, property_id = value.split("::", 2)
        runtime = _runtime_by_unique_id(hass, entry_unique_id)
        return runtime, int(property_id)

    raise HomeAssistantError("The selected target is not a MySolid property")


def _runtime_by_unique_id(hass: HomeAssistant, unique_id: str) -> MySolidRuntimeData:
    for runtime in hass.data.get(DOMAIN, {}).values():
        if runtime.entry.unique_id == unique_id:
            return runtime
    raise HomeAssistantError("The selected MySolid property is no longer available")


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return []


def _normalize_mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


async def _run_api_call(awaitable) -> None:
    try:
        await awaitable
    except MySolidApiError as err:
        raise HomeAssistantError(str(err)) from err
