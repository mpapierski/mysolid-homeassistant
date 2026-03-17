"""Shared entity helpers for the MySolid integration."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, entity_unique_id, property_identifier
from .coordinator import MySolidRuntimeData
from .models import PropertySnapshot

MANUFACTURER = "Solid Security"
MODEL_PROPERTY = "MySolid Property"


def _entry_key(runtime: MySolidRuntimeData) -> str:
    return runtime.entry.unique_id or runtime.entry.entry_id


def build_property_device_info(
    runtime: MySolidRuntimeData,
    property_snapshot: PropertySnapshot,
) -> DeviceInfo:
    property_id = property_snapshot.details.id
    assert property_id is not None
    return DeviceInfo(
        identifiers={(DOMAIN, property_identifier(_entry_key(runtime), property_id))},
        manufacturer=MANUFACTURER,
        model=MODEL_PROPERTY,
        name=property_snapshot.details.name or f"MySolid {property_id}",
        serial_number=property_snapshot.details.external_id or str(property_id),
        configuration_url=runtime.client.host,
    )


class MySolidEntityMixin:
    _attr_has_entity_name = True

    def __init__(
        self,
        runtime: MySolidRuntimeData,
        property_id: int,
        suffix: str,
    ) -> None:
        self.runtime = runtime
        self.property_id = property_id
        self._attr_unique_id = entity_unique_id(
            _entry_key(runtime),
            property_id,
            suffix,
        )

    @property
    def property_snapshot(self) -> PropertySnapshot:
        return self.runtime.get_property_snapshot(self.property_id)

    @property
    def device_info(self) -> DeviceInfo:
        return build_property_device_info(self.runtime, self.property_snapshot)


class MySolidCoordinatorEntity(MySolidEntityMixin, CoordinatorEntity):
    def __init__(
        self,
        runtime: MySolidRuntimeData,
        property_id: int,
        suffix: str,
    ) -> None:
        MySolidEntityMixin.__init__(self, runtime, property_id, suffix)
        CoordinatorEntity.__init__(self, runtime.coordinator)
