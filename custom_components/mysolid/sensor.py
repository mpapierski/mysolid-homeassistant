"""Sensor platform for MySolid."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MySolidRuntimeData
from .entity import MySolidCoordinatorEntity
from .models import PropertySnapshot


@dataclass(frozen=True, slots=True, kw_only=True)
class MySolidSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PropertySnapshot], str | int | None]


SENSORS: tuple[MySolidSensorDescription, ...] = (
    MySolidSensorDescription(
        key="active_alarm_count",
        name="Active alarms",
        value_fn=lambda snapshot: snapshot.active_alarm_count,
    ),
    MySolidSensorDescription(
        key="authorized_user_count",
        name="Authorized users",
        value_fn=lambda snapshot: snapshot.authorized_user_count,
    ),
    MySolidSensorDescription(
        key="last_alarm",
        name="Last alarm",
        value_fn=lambda snapshot: snapshot.last_alarm_summary,
    ),
    MySolidSensorDescription(
        key="schedule_summary",
        name="Schedule",
        value_fn=lambda snapshot: snapshot.schedule_summary,
    ),
    MySolidSensorDescription(
        key="suspension_summary",
        name="Suspension",
        value_fn=lambda snapshot: snapshot.suspension_summary,
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
            for description in SENSORS:
                key = (property_id, description.key)
                if key in known:
                    continue
                known.add(key)
                new_entities.append(MySolidPropertySensor(runtime, property_id, description))
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(runtime.coordinator.async_add_listener(_sync_entities))


class MySolidPropertySensor(MySolidCoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(
        self,
        runtime: MySolidRuntimeData,
        property_id: int,
        description: MySolidSensorDescription,
    ) -> None:
        super().__init__(runtime, property_id, f"sensor_{description.key}")
        self.entity_description = description
        self._attr_name = description.name

    @property
    def native_value(self) -> str | int | None:
        return self.entity_description.value_fn(self.property_snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        if self.entity_description.key == "last_alarm" and self.property_snapshot.active_alarms:
            return dict(self.property_snapshot.active_alarms[0])
        return {}
