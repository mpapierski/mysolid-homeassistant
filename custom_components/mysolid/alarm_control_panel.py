"""Alarm control panels for MySolid properties."""

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
    known: set[int] = set()

    @callback
    def _sync_entities() -> None:
        new_entities = []
        snapshot = runtime.coordinator.data
        if snapshot is None:
            return
        for property_id in snapshot.properties:
            if property_id in known:
                continue
            known.add(property_id)
            new_entities.append(MySolidAlarmPanel(runtime, property_id))
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
    ) -> None:
        super().__init__(runtime, property_id, "alarm")
        self._attr_name = "Alarm"

    @property
    def alarm_relays(self) -> tuple[RelaySnapshot, ...]:
        return tuple(
            relay for relay in self.property_snapshot.relays if relay.is_alarm_panel
        )

    @property
    def relay(self) -> RelaySnapshot | None:
        relays = self.alarm_relays
        if len(relays) == 1:
            return relays[0]
        return None

    @property
    def alarm_state(self) -> AlarmControlPanelState:
        if self.property_snapshot.has_active_alarm:
            return AlarmControlPanelState.TRIGGERED

        relay = self.relay
        if relay is not None:
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

        if self.property_snapshot.details.armed is False:
            return AlarmControlPanelState.DISARMED
        if self.property_snapshot.details.armed is True:
            return AlarmControlPanelState.ARMED_AWAY
        return AlarmControlPanelState.UNKNOWN

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        relay = self.relay
        if relay is None:
            return AlarmControlPanelEntityFeature(0)

        features = AlarmControlPanelEntityFeature.ARM_AWAY
        if relay.supports_partial_arm:
            features |= AlarmControlPanelEntityFeature.ARM_HOME
        return features

    @property
    def code_format(self) -> CodeFormat | None:
        relay = self.relay
        if relay is not None and relay.relay_pin_confirmation:
            return CodeFormat.NUMBER
        return None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attributes: dict[str, object] = {
            "property_id": self.property_id,
            "armed": self.property_snapshot.details.armed,
            "active_alarm_count": self.property_snapshot.active_alarm_count,
            "alarm_relay_count": len(self.alarm_relays),
            "writable": self.relay is not None,
        }
        relay = self.relay
        if relay is None:
            return attributes
        attributes.update(
            {
            "transmitter_id": relay.transmitter_id,
            "relay_number": relay.relay_number,
            "requested_state": relay.requested_state,
            "change_status": relay.change_status,
            "relay_pin_confirmation": relay.relay_pin_confirmation,
            }
        )
        return attributes

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        relay = self._require_writable_relay()
        await self.runtime.async_execute_relay(
            property_id=self.property_id,
            transmitter_id=self._required_transmitter_id(relay),
            relay_number=self._required_relay_number(relay),
            state="DISARM",
            pin=code,
        )

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        relay = self._require_writable_relay()
        await self.runtime.async_execute_relay(
            property_id=self.property_id,
            transmitter_id=self._required_transmitter_id(relay),
            relay_number=self._required_relay_number(relay),
            state="ARM",
            pin=code,
        )

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        relay = self._require_writable_relay()
        if not relay.supports_partial_arm:
            raise HomeAssistantError("This relay does not support partial arm")
        await self.runtime.async_execute_relay(
            property_id=self.property_id,
            transmitter_id=self._required_transmitter_id(relay),
            relay_number=self._required_relay_number(relay),
            state="PARTIAL_ARM",
            pin=code,
        )

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        raise HomeAssistantError("Trigger is not supported by the MySolid API")

    def _require_writable_relay(self) -> RelaySnapshot:
        relay = self.relay
        if relay is not None:
            return relay
        if not self.alarm_relays:
            raise HomeAssistantError(
                "This property does not expose arm/disarm relay control in MySolid."
            )
        raise HomeAssistantError(
            "This property exposes multiple arm/disarm relays, so write control is ambiguous."
        )

    def _required_transmitter_id(self, relay: RelaySnapshot) -> int:
        if relay.transmitter_id is None:
            raise HomeAssistantError("Relay is missing transmitter metadata")
        return relay.transmitter_id

    def _required_relay_number(self, relay: RelaySnapshot) -> int:
        if relay.relay_number is None:
            raise HomeAssistantError("Relay is missing number metadata")
        return relay.relay_number
