"""Coordinator and runtime state for the MySolid integration."""

from __future__ import annotations

import asyncio
import logging
import ssl
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.importlib import async_import_module
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MySolidClient, default_device_name
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_PUSH_ENABLED,
    CONF_PUSH_RECONNECT_SECONDS,
    DOMAIN,
)
from .exceptions import MySolidApiError, MySolidAuthError
from .models import MySolidSnapshot, PropertyDetails, PropertySnapshot, RelaySnapshot
from .storage import MySolidStateStore, StoredState

LOGGER = logging.getLogger(__name__)


class MySolidCoordinator(DataUpdateCoordinator[MySolidSnapshot]):
    """Coordinator that owns the normalized MySolid account state."""

    def __init__(self, hass: HomeAssistant, runtime: MySolidRuntimeData) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{runtime.entry.entry_id}",
            update_interval=timedelta(seconds=runtime.poll_interval_seconds),
        )
        self.runtime = runtime

    async def _async_update_data(self) -> MySolidSnapshot:
        return await self.runtime.async_fetch_snapshot()


class MySolidRuntimeData:
    """Shared runtime state for one MySolid config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: MySolidClient,
        store: MySolidStateStore,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.store = store
        self.coordinator = MySolidCoordinator(hass, self)
        self.stored_state: StoredState | None = None
        self._auth_lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._push_task: asyncio.Task[None] | None = None
        self._push_ssl_context: ssl.SSLContext | None = None
        self._stopped = False

    @property
    def email(self) -> str:
        return str(self.entry.data[CONF_EMAIL])

    @property
    def password(self) -> str:
        return str(self.entry.data[CONF_PASSWORD])

    @property
    def poll_interval_seconds(self) -> int:
        return int(
            self.entry.options.get(
                CONF_POLL_INTERVAL_SECONDS,
                self.entry.data.get(CONF_POLL_INTERVAL_SECONDS, 60),
            )
        )

    @property
    def push_enabled(self) -> bool:
        return bool(
            self.entry.options.get(
                CONF_PUSH_ENABLED,
                self.entry.data.get(CONF_PUSH_ENABLED, True),
            )
        )

    @property
    def push_reconnect_seconds(self) -> int:
        return int(
            self.entry.options.get(
                CONF_PUSH_RECONNECT_SECONDS,
                self.entry.data.get(CONF_PUSH_RECONNECT_SECONDS, 30),
            )
        )

    async def async_initialize(self) -> None:
        self.stored_state = await self.store.async_load()
        if self.stored_state is not None:
            self.client.configure_session(
                email=self.stored_state.session.email,
                access_token=self.stored_state.session.access_token,
                device_id=self.stored_state.session.device_id,
                device_name=self.stored_state.session.device_name,
                firebase_token=self.stored_state.session.firebase_token,
            )

        if not self.client.device_id:
            self.client.configure_session(
                device_id=str(self.entry.data[CONF_DEVICE_ID]),
                device_name=str(self.entry.data[CONF_DEVICE_NAME]),
            )

        if not self.client.is_authenticated or (
            self.client.access_token is not None and self.client.access_token.is_expired
        ):
            await self.async_login(force=True)
        else:
            await self._async_save_state()

        await self.coordinator.async_config_entry_first_refresh()
        if self.push_enabled:
            self.async_start_push()

    async def async_shutdown(self) -> None:
        self._stopped = True
        if self._push_task is not None:
            self._push_task.cancel()
            await asyncio.gather(self._push_task, return_exceptions=True)
            self._push_task = None
        await self.client.close()

    async def async_login(self, *, force: bool = False) -> None:
        async with self._auth_lock:
            if (
                not force
                and self.client.is_authenticated
                and self.client.access_token is not None
                and not self.client.access_token.is_expired
            ):
                return

            await self.client.login(
                self.email,
                self.password,
                device_id=self.client.device_id or str(self.entry.data[CONF_DEVICE_ID]),
                device_name=self.client.device_name
                or str(self.entry.data[CONF_DEVICE_NAME]),
                firebase_token=self.client.firebase_token,
            )
            await self._async_save_state()

    async def async_fetch_snapshot(self) -> MySolidSnapshot:
        async with self._refresh_lock:
            try:
                return await self._async_build_snapshot()
            except MySolidAuthError:
                await self.async_login(force=True)
                return await self._async_build_snapshot()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise UpdateFailed(str(err)) from err
            except MySolidApiError as err:
                raise UpdateFailed(str(err)) from err

    async def _async_build_snapshot(self) -> MySolidSnapshot:
        previous = self.coordinator.data if self.coordinator.data is not None else MySolidSnapshot()
        property_response, permissions, active_alarms = await asyncio.gather(
            self.client.get_property_details(),
            self.client.get_permissions(),
            self._async_optional_call(self.client.list_alarms, default=[]),
        )

        alarms_by_property: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for alarm in active_alarms:
            property_id = _extract_property_id(alarm.get("propertyDetails"))
            if property_id is not None:
                alarms_by_property[property_id].append(alarm)

        bundles = await asyncio.gather(
            *[
                self._async_fetch_property_bundle(
                    details,
                    permissions=frozenset(permissions),
                    active_alarms=tuple(alarms_by_property.get(details.id or -1, [])),
                )
                for details in property_response.properties
            ]
        )

        properties = {
            bundle.details.id: bundle
            for bundle in bundles
            if bundle.details.id is not None
        }
        return MySolidSnapshot(
            client_id=property_response.client_id,
            permissions=frozenset(permissions),
            properties=properties,
            push_connected=previous.push_connected,
            push_error=previous.push_error,
            last_push_title=previous.last_push_title,
            last_push_body=previous.last_push_body,
            last_push_payload=previous.last_push_payload,
            last_push_at=previous.last_push_at,
        )

    async def _async_fetch_property_bundle(
        self,
        details: PropertyDetails,
        *,
        permissions: frozenset[str],
        active_alarms: tuple[dict[str, Any], ...],
    ) -> PropertySnapshot:
        assert details.id is not None
        relays_task = self._async_optional_call(
            self.client.get_relays,
            details.id,
            default=[],
        )
        authorized_users_task = self._async_optional_call(
            self.client.get_authorized_users,
            details.id,
            default=[],
            enabled="AUTHORIZED_USERS" in permissions,
        )
        schedule_task = self._async_optional_call(
            self.client.get_schedule,
            details.id,
            default=None,
        )
        suspensions_task = self._async_optional_call(
            self.client.get_suspensions,
            details.external_id,
            default=[],
            enabled=bool(details.external_id) and "EVENT_SUSPENSION" in permissions,
        )
        relays, authorized_users, schedule, suspensions = await asyncio.gather(
            relays_task,
            authorized_users_task,
            schedule_task,
            suspensions_task,
        )
        return PropertySnapshot(
            details=details,
            relays=tuple(RelaySnapshot.from_api(details.id, item) for item in relays),
            active_alarms=active_alarms,
            authorized_users=tuple(dict(item) for item in authorized_users),
            schedule=dict(schedule) if isinstance(schedule, dict) else None,
            suspensions=tuple(dict(item) for item in suspensions),
        )

    async def _async_optional_call(
        self,
        func,
        *args: Any,
        default: Any,
        enabled: bool = True,
    ) -> Any:
        if not enabled:
            return default
        try:
            return await func(*args)
        except MySolidApiError as err:
            if err.status in {403, 404}:
                LOGGER.debug("Optional MySolid API call failed: %s", err)
                return default
            raise

    async def _async_save_state(self) -> None:
        state = StoredState(
            session=self.client.session,
            push_credentials=self.stored_state.push_credentials if self.stored_state else None,
            persistent_ids=self.stored_state.persistent_ids if self.stored_state else (),
        )
        self.stored_state = state
        await self.store.async_save(state)

    async def _async_save_push_state(
        self,
        *,
        push_credentials=None,
        persistent_ids: tuple[str, ...] | None = None,
    ) -> None:
        state = StoredState(
            session=self.client.session,
            push_credentials=push_credentials
            if push_credentials is not None
            else (self.stored_state.push_credentials if self.stored_state else None),
            persistent_ids=persistent_ids
            if persistent_ids is not None
            else (self.stored_state.persistent_ids if self.stored_state else ()),
        )
        self.stored_state = state
        await self.store.async_save(state)

    @callback
    def async_start_push(self) -> None:
        if self._push_task is not None or self._stopped:
            return
        self._push_task = self.hass.async_create_task(
            self._async_push_loop(),
            name=f"{DOMAIN}_push_{self.entry.entry_id}",
        )

    async def _async_push_loop(self) -> None:
        push_module = await async_import_module(self.hass, "custom_components.mysolid.push")
        listener_class = push_module.MySolidPushListener
        push_error = push_module.PushError
        bootstrap_push_credentials = push_module.bootstrap_push_credentials
        delay = self.push_reconnect_seconds
        while not self._stopped:
            listener = None
            credentials = self.stored_state.push_credentials if self.stored_state else None
            try:
                await self.async_login()
                if credentials is None:
                    credentials = await bootstrap_push_credentials(
                        session=async_get_clientsession(self.hass)
                    )
                if self.client.firebase_token != credentials.registration_token:
                    await self.client.update_firebase_token(credentials.registration_token)
                await self._async_save_push_state(push_credentials=credentials)
                access_token = self.client.access_token
                if access_token is None:
                    raise MySolidAuthError(401, "Missing access token")
                if self._push_ssl_context is None:
                    self._push_ssl_context = await self.hass.async_add_executor_job(
                        ssl.create_default_context
                    )
                listener = listener_class(
                    credentials,
                    access_token=access_token.value,
                    persistent_ids=self.stored_state.persistent_ids if self.stored_state else (),
                    ssl_context=self._push_ssl_context,
                )
                async with listener:
                    self.async_set_push_status(connected=True, error=None)
                    delay = self.push_reconnect_seconds
                    async for message in listener:
                        await self._async_save_push_state(
                            push_credentials=credentials,
                            persistent_ids=tuple(listener.persistent_ids),
                        )
                        self.async_handle_push_message(message)
            except asyncio.CancelledError:
                if listener is not None:
                    await self._async_save_push_state(
                        push_credentials=credentials,
                        persistent_ids=tuple(listener.persistent_ids),
                    )
                raise
            except (
                push_error,
                OSError,
                ConnectionError,
                asyncio.IncompleteReadError,
                aiohttp.ClientError,
                MySolidApiError,
            ) as err:
                LOGGER.warning("MySolid push loop failed: %s", err)
                if listener is not None:
                    await self._async_save_push_state(
                        push_credentials=credentials,
                        persistent_ids=tuple(listener.persistent_ids),
                    )
                if isinstance(err, MySolidAuthError):
                    await self.async_login(force=True)
                self.async_set_push_status(connected=False, error=str(err))
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300)

    @callback
    def async_set_push_status(self, *, connected: bool, error: str | None) -> None:
        snapshot = self.coordinator.data or MySolidSnapshot()
        updated = snapshot.clone()
        updated.push_connected = connected
        updated.push_error = error
        self.coordinator.async_set_updated_data(updated)

    @callback
    def async_handle_push_message(self, message) -> None:
        snapshot = self.coordinator.data or MySolidSnapshot()
        updated = snapshot.clone()
        updated.push_connected = True
        updated.push_error = None
        updated.last_push_title = message.title
        updated.last_push_body = message.body
        updated.last_push_payload = (
            dict(message.decrypted_json)
            if message.decrypted_json is not None
            else dict(message.app_data)
        )
        updated.last_push_at = datetime.now(tz=UTC)

        payload = message.decrypted_json or {}
        handled = False
        for item in payload.get("propertiesDetails", []):
            property_id = _extract_property_id(item)
            if property_id is None or property_id not in updated.properties:
                continue
            property_snapshot = updated.properties[property_id]
            updated.properties[property_id] = property_snapshot.replace_details(
                property_snapshot.details.updated_from_push(item)
            )
            handled = True

        for item in payload.get("propertyDetails", []):
            property_id = _extract_property_id(item)
            if property_id is None or property_id not in updated.properties:
                continue
            property_snapshot = updated.properties[property_id]
            updated.properties[property_id] = property_snapshot.replace_details(
                property_snapshot.details.updated_from_push(item)
            )
            handled = True

        for item in payload.get("rearmingDetailsList", []):
            if not isinstance(item, dict):
                continue
            raw_property = item.get("propertyDetails")
            property_id = _extract_property_id(raw_property)
            if property_id is None or property_id not in updated.properties:
                continue
            property_snapshot = updated.properties[property_id]
            merged = dict(raw_property) if isinstance(raw_property, dict) else {}
            if "armed" in item:
                merged["armed"] = item.get("armed")
            updated.properties[property_id] = property_snapshot.replace_details(
                property_snapshot.details.updated_from_push(merged)
            )
            handled = True

        self.coordinator.async_set_updated_data(updated)

        if not handled or _push_requires_refresh(payload, message.click_action):
            self.hass.async_create_task(self.coordinator.async_request_refresh())

    def get_property_snapshot(self, property_id: int) -> PropertySnapshot:
        if self.coordinator.data is None or property_id not in self.coordinator.data.properties:
            raise KeyError(property_id)
        return self.coordinator.data.properties[property_id]

    def get_relay_snapshot(
        self,
        property_id: int,
        transmitter_id: int,
        relay_number: int,
    ) -> RelaySnapshot:
        snapshot = self.get_property_snapshot(property_id)
        for relay in snapshot.relays:
            if relay.transmitter_id == transmitter_id and relay.relay_number == relay_number:
                return relay
        raise KeyError((property_id, transmitter_id, relay_number))

    async def async_execute_relay(
        self,
        *,
        property_id: int,
        transmitter_id: int,
        relay_number: int,
        state: str,
        pin: str | None = None,
    ) -> None:
        relay = self.get_relay_snapshot(property_id, transmitter_id, relay_number)
        payload: dict[str, Any] = {
            "account": {"accountId": property_id},
            "transmitterId": transmitter_id,
            "relayNumber": relay_number,
            "state": state,
            "label": relay.label,
        }
        if relay.icon_name is not None:
            payload["iconName"] = relay.icon_name
        if relay.icon_name_off is not None:
            payload["iconNameOff"] = relay.icon_name_off
        if pin:
            payload["pin"] = pin
        await self.client.update_relay_state(payload)
        await self.coordinator.async_request_refresh()

    async def async_report_alarm(
        self,
        *,
        property_id: int,
        alarm_type: str,
        latitude: float | None,
        longitude: float | None,
    ) -> None:
        location = None
        if latitude is not None and longitude is not None:
            location = {"lat": latitude, "lon": longitude}
        await self.client.report_alarm(
            property_id=property_id,
            location=location,
            alarm_type=alarm_type,
        )
        await self.coordinator.async_request_refresh()

    async def async_cancel_alarm(self, *, event_id: int, pin: str | None) -> None:
        await self.client.cancel_alarm(event_id, pin=pin)
        await self.coordinator.async_request_refresh()

    async def async_confirm_alarm(self, *, event_bundle_id: int) -> None:
        await self.client.confirm_alarm_received(event_bundle_id)

    async def async_report_amber(
        self,
        *,
        property_id: int,
        duration_milliseconds: int,
        alarm_type: str,
        latitude: float | None,
        longitude: float | None,
    ) -> None:
        location = None
        if latitude is not None and longitude is not None:
            location = {"lat": latitude, "lon": longitude}
        await self.client.report_amber(
            property_id=property_id,
            duration_milliseconds=duration_milliseconds,
            location=location,
            alarm_type=alarm_type,
        )
        await self.coordinator.async_request_refresh()

    async def async_cancel_amber(self, *, amber_id: str, pin: str | None) -> None:
        await self.client.cancel_amber(amber_id, pin=pin)
        await self.coordinator.async_request_refresh()

    async def async_create_suspension(
        self,
        *,
        property_id: int,
        suspend_from: str,
        suspend_until: str,
    ) -> None:
        property_snapshot = self.get_property_snapshot(property_id)
        await self.client.add_suspension(
            {
                "suspendFrom": suspend_from,
                "suspendUntil": suspend_until,
                "externalPropertyId": property_snapshot.details.external_id,
                "accountExternalId": str(property_id),
            }
        )
        await self.coordinator.async_request_refresh()

    async def async_delete_suspension(self, *, event_suspension_id: int) -> None:
        await self.client.delete_suspension(event_suspension_id)
        await self.coordinator.async_request_refresh()

    async def async_update_schedule_range(
        self,
        *,
        property_id: int,
        target: str,
        transmitter_id: int,
        partition_number: int,
        schedule_before: dict[str, Any],
        schedule_after: dict[str, Any],
    ) -> None:
        await self.client.update_schedule_range(
            {
                "target": target,
                "accountId": property_id,
                "transmitterId": transmitter_id,
                "partitionNumber": partition_number,
                "scheduleBefore": schedule_before,
                "scheduleAfter": schedule_after,
            }
        )
        await self.coordinator.async_request_refresh()

    async def async_set_special_schedule(
        self,
        *,
        property_id: int,
        target: str,
        transmitter_id: int,
        partition_number: int,
        ranges: list[dict[str, Any]],
    ) -> None:
        await self.client.set_special_schedule(
            {
                "target": target,
                "accountId": property_id,
                "transmitterId": transmitter_id,
                "partitionNumber": partition_number,
                "ranges": ranges,
            }
        )
        await self.coordinator.async_request_refresh()

    async def async_delete_special_schedule(self, *, schedule_id: int) -> None:
        await self.client.delete_special_schedule(schedule_id)
        await self.coordinator.async_request_refresh()

    async def async_create_authorized_user(
        self,
        *,
        property_id: int,
        role_id: int,
        name: str,
        surname: str,
        number: str | None,
        comment: str | None,
        phones_list: list[dict[str, Any]],
        email_value: str | None,
        temporary: bool,
        active_from: str | None,
        active_to: str | None,
        soon_to_expire: int,
        pin: str | None,
    ) -> None:
        payload = {
            "accountId": property_id,
            "roleId": role_id,
            "name": name,
            "surname": surname,
            "number": number,
            "comment": comment,
            "phonesList": phones_list,
            "email": email_value,
            "temporary": temporary,
            "activeFrom": active_from,
            "activeTo": active_to,
            "soonToExpire": soon_to_expire,
        }
        if pin:
            payload["pin"] = pin
        await self.client.register_authorized_user(payload)
        await self.coordinator.async_request_refresh()

    async def async_update_authorized_user(
        self,
        *,
        property_id: int,
        authorized_user_id: int,
        role_id: int,
        name: str,
        surname: str,
        number: str | None,
        comment: str | None,
        phones_list: list[dict[str, Any]],
        email_value: str | None,
        temporary: bool,
        active_from: str | None,
        active_to: str | None,
        soon_to_expire: int,
        pin: str | None,
    ) -> None:
        payload = {
            "id": authorized_user_id,
            "accountId": property_id,
            "roleId": role_id,
            "name": name,
            "surname": surname,
            "number": number,
            "comment": comment,
            "phonesList": phones_list,
            "email": email_value,
            "temporary": temporary,
            "activeFrom": active_from,
            "activeTo": active_to,
            "soonToExpire": soon_to_expire,
        }
        if pin:
            payload["pin"] = pin
        await self.client.edit_authorized_user(payload)
        await self.coordinator.async_request_refresh()

    async def async_delete_authorized_user(self, *, authorized_user_id: int) -> None:
        await self.client.delete_authorized_user(authorized_user_id)
        await self.coordinator.async_request_refresh()

    async def async_reset_authorized_user_password(
        self,
        *,
        authorized_user_id: int,
        pin: str,
    ) -> None:
        await self.client.reset_password_for_authorized_user(
            authorized_user_id,
            pin=pin,
        )
        await self.coordinator.async_request_refresh()

    async def async_reorder_authorized_users(
        self,
        *,
        property_id: int,
        ordered_ids: list[int],
    ) -> None:
        await self.client.update_authorized_users_order(property_id, ordered_ids)
        await self.coordinator.async_request_refresh()


def build_runtime(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> MySolidRuntimeData:
    session = async_get_clientsession(hass)
    client = MySolidClient(
        host=str(entry.data["host"]),
        email=str(entry.data[CONF_EMAIL]),
        device_id=str(entry.data[CONF_DEVICE_ID]),
        device_name=str(entry.data.get(CONF_DEVICE_NAME, default_device_name())),
        session=session,
    )
    return MySolidRuntimeData(
        hass=hass,
        entry=entry,
        client=client,
        store=MySolidStateStore(hass, entry.entry_id),
    )


def _extract_property_id(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    try:
        if payload.get("id") is None:
            return None
        return int(payload["id"])
    except (TypeError, ValueError):
        return None


def _push_requires_refresh(payload: dict[str, Any], click_action: str | None) -> bool:
    if "alarmEvent" in payload or "mobileRelayExecute" in payload:
        return True
    if click_action and click_action.endswith("ACTION_SESSION_EXPIRED"):
        return True
    return False
