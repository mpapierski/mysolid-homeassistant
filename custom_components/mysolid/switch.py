"""Switch entities for non-arming MySolid relays."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
                if not relay.is_switch:
                    continue
                if relay.unique_key in known:
                    continue
                known.add(relay.unique_key)
                new_entities.append(MySolidRelaySwitch(runtime, property_id, relay))
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(runtime.coordinator.async_add_listener(_sync_entities))


class MySolidRelaySwitch(MySolidCoordinatorEntity, SwitchEntity):
    _attr_should_poll = False

    def __init__(
        self,
        runtime: MySolidRuntimeData,
        property_id: int,
        relay: RelaySnapshot,
    ) -> None:
        suffix = f"switch::{relay.transmitter_id}::{relay.relay_number}"
        super().__init__(runtime, property_id, suffix)
        self._transmitter_id = relay.transmitter_id
        self._relay_number = relay.relay_number
        self._attr_name = relay.label or f"Relay {relay.relay_number}"

    @property
    def relay(self) -> RelaySnapshot:
        return self.runtime.get_relay_snapshot(
            self.property_id,
            self._required_transmitter_id(),
            self._required_relay_number(),
        )

    @property
    def is_on(self) -> bool:
        if self.relay.change_status == "WAITING" and self.relay.requested_state in {"ON", "OFF"}:
            return self.relay.requested_state == "ON"
        return self.relay.state == "ON"

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

    async def async_turn_on(self, **kwargs) -> None:
        self._ensure_write_allowed()
        await self.runtime.async_execute_relay(
            property_id=self.property_id,
            transmitter_id=self._required_transmitter_id(),
            relay_number=self._required_relay_number(),
            state="ON",
        )

    async def async_turn_off(self, **kwargs) -> None:
        self._ensure_write_allowed()
        await self.runtime.async_execute_relay(
            property_id=self.property_id,
            transmitter_id=self._required_transmitter_id(),
            relay_number=self._required_relay_number(),
            state="OFF",
        )

    def _ensure_write_allowed(self) -> None:
        if self.relay.relay_pin_confirmation:
            raise HomeAssistantError(
                "This relay requires a PIN. Use the mysolid.execute_relay service instead."
            )

    def _required_transmitter_id(self) -> int:
        if self._transmitter_id is None:
            raise HomeAssistantError("Relay is missing transmitter metadata")
        return self._transmitter_id

    def _required_relay_number(self) -> int:
        if self._relay_number is None:
            raise HomeAssistantError("Relay is missing number metadata")
        return self._relay_number
