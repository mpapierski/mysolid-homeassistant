"""Alarm control panels for MySolid arm/disarm relays."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MySolidRuntimeData
from .entity import MySolidCoordinatorEntity
from .models import RelaySnapshot


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: MySolidRuntimeData = entry.runtime_data
    known: set[tuple[int, int | None, int | None]] = set()

    @callback
    def _sync_entities() -> None:
        new_entities = []
        snapshot = runtime.coordinator.data
        if snapshot is None:
            return
        for property_id, property_snapshot in snapshot.properties.items():
            for relay in property_snapshot.relays:
                if not relay.is_alarm_panel:
                    continue
                if relay.unique_key in known:
                    continue
                known.add(relay.unique_key)
                new_entities.append(MySolidAlarmPanel(runtime, property_id, relay))
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(runtime.coordinator.async_add_listener(_sync_entities))


class MySolidAlarmPanel(MySolidCoordinatorEntity, AlarmControlPanelEntity):
    _attr_should_poll = False

    def __init__(
        self,
        runtime: MySolidRuntimeData,
        property_id: int,
        relay: RelaySnapshot,
    ) -> None:
        suffix = f"alarm::{relay.transmitter_id}::{relay.relay_number}"
        super().__init__(runtime, property_id, suffix)
        self._transmitter_id = relay.transmitter_id
        self._relay_number = relay.relay_number
        self._attr_name = relay.label or f"Alarm {relay.relay_number}"

    @property
    def relay(self) -> RelaySnapshot:
        if self._transmitter_id is None or self._relay_number is None:
            raise HomeAssistantError("Relay is missing transmitter metadata")
        return self.runtime.get_relay_snapshot(
            self.property_id,
            self._transmitter_id,
            self._relay_number,
        )

    @property
    def alarm_state(self) -> AlarmControlPanelState:
        relay = self.relay
        if relay.change_status == "WAITING":
            if relay.requested_state == "DISARM":
                return AlarmControlPanelState.DISARMING
            if relay.requested_state in {"ARM", "PARTIAL_ARM"}:
                return AlarmControlPanelState.ARMING
        if relay.state == "DISARM":
            return AlarmControlPanelState.DISARMED
        if relay.state == "PARTIAL_ARM":
            return AlarmControlPanelState.ARMED_HOME
        if relay.state == "ARM":
            return AlarmControlPanelState.ARMED_AWAY
        return AlarmControlPanelState.UNKNOWN

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        features = AlarmControlPanelEntityFeature.ARM_AWAY
        if self.relay.supports_partial_arm:
            features |= AlarmControlPanelEntityFeature.ARM_HOME
        return features

    @property
    def code_format(self) -> CodeFormat | None:
        if self.relay.relay_pin_confirmation:
            return CodeFormat.NUMBER
        return None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        relay = self.relay
        return {
            "transmitter_id": relay.transmitter_id,
            "relay_number": relay.relay_number,
            "requested_state": relay.requested_state,
            "change_status": relay.change_status,
            "relay_pin_confirmation": relay.relay_pin_confirmation,
        }

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self.runtime.async_execute_relay(
            property_id=self.property_id,
            transmitter_id=self._required_transmitter_id(),
            relay_number=self._required_relay_number(),
            state="DISARM",
            pin=code,
        )

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self.runtime.async_execute_relay(
            property_id=self.property_id,
            transmitter_id=self._required_transmitter_id(),
            relay_number=self._required_relay_number(),
            state="ARM",
            pin=code,
        )

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        if not self.relay.supports_partial_arm:
            raise HomeAssistantError("This relay does not support partial arm")
        await self.runtime.async_execute_relay(
            property_id=self.property_id,
            transmitter_id=self._required_transmitter_id(),
            relay_number=self._required_relay_number(),
            state="PARTIAL_ARM",
            pin=code,
        )

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        raise HomeAssistantError("Trigger is not supported by the MySolid API")

    def _required_transmitter_id(self) -> int:
        if self._transmitter_id is None:
            raise HomeAssistantError("Relay is missing transmitter metadata")
        return self._transmitter_id

    def _required_relay_number(self) -> int:
        if self._relay_number is None:
            raise HomeAssistantError("Relay is missing number metadata")
        return self._relay_number
