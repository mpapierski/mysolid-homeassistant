"""Binary sensors for MySolid."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MySolidRuntimeData
from .entity import MySolidCoordinatorEntity
from .models import PropertySnapshot


@dataclass(frozen=True, slots=True, kw_only=True)
class MySolidBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[MySolidRuntimeData, PropertySnapshot], bool]


BINARY_SENSORS: tuple[MySolidBinarySensorDescription, ...] = (
    MySolidBinarySensorDescription(
        key="active_alarm",
        name="Active alarm",
        value_fn=lambda runtime, snapshot: snapshot.has_active_alarm,
        device_class=BinarySensorDeviceClass.SAFETY,
    ),
    MySolidBinarySensorDescription(
        key="event_suspension",
        name="Event suspension",
        value_fn=lambda runtime, snapshot: snapshot.suspension_active,
    ),
    MySolidBinarySensorDescription(
        key="cameras_enabled",
        name="Cameras enabled",
        value_fn=lambda runtime, snapshot: bool(snapshot.details.cameras_enabled),
    ),
    MySolidBinarySensorDescription(
        key="convoys_enabled",
        name="Convoys enabled",
        value_fn=lambda runtime, snapshot: bool(snapshot.details.convoys_enabled),
    ),
    MySolidBinarySensorDescription(
        key="push_connected",
        name="Push connected",
        value_fn=lambda runtime, snapshot: bool(
            runtime.coordinator.data and runtime.coordinator.data.push_connected
        ),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: MySolidRuntimeData = entry.runtime_data
    known: set[tuple[int, str]] = set()

    @callback
    def _sync_entities() -> None:
        new_entities = []
        snapshot = runtime.coordinator.data
        if snapshot is None:
            return
        for property_id in snapshot.properties:
            for description in BINARY_SENSORS:
                key = (property_id, description.key)
                if key in known:
                    continue
                known.add(key)
                new_entities.append(
                    MySolidPropertyBinarySensor(runtime, property_id, description)
                )
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(runtime.coordinator.async_add_listener(_sync_entities))


class MySolidPropertyBinarySensor(MySolidCoordinatorEntity, BinarySensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        runtime: MySolidRuntimeData,
        property_id: int,
        description: MySolidBinarySensorDescription,
    ) -> None:
        super().__init__(runtime, property_id, f"binary_sensor_{description.key}")
        self.entity_description = description
        self._attr_name = description.name
        self._attr_device_class = description.device_class

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.runtime, self.property_snapshot)
