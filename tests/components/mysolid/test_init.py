"""Integration setup tests for MySolid."""

from __future__ import annotations

import importlib

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.mysolid.const import DOMAIN, entity_unique_id

from .conftest import PROPERTY_ID


async def test_setup_entry_creates_entities_and_device(
    hass,
    patch_runtime,
    mock_entry,
) -> None:
    """Setting up the entry should create property entities and devices."""
    mock_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entry_key = mock_entry.unique_id or mock_entry.entry_id

    alarm_entity = entity_registry.async_get_entity_id(
        "alarm_control_panel",
        DOMAIN,
        entity_unique_id(entry_key, PROPERTY_ID, "alarm::1111::1"),
    )
    switch_entity = entity_registry.async_get_entity_id(
        "switch",
        DOMAIN,
        entity_unique_id(entry_key, PROPERTY_ID, "switch::1111::2"),
    )
    camera_entity = entity_registry.async_get_entity_id(
        "camera",
        DOMAIN,
        entity_unique_id(entry_key, PROPERTY_ID, "camera::0::0"),
    )

    assert hass.states.get(alarm_entity).state == "disarmed"
    assert hass.states.get(switch_entity).state == "on"
    assert camera_entity is not None
    assert entity_registry.async_get(camera_entity).original_name == "Front gate"

    device_registry = dr.async_get(hass)
    device = next(
        device
        for device in device_registry.devices.values()
        if any(identifier[0] == DOMAIN for identifier in device.identifiers)
    )
    assert device.name == "Home"


def test_platform_modules_import() -> None:
    """Platform modules should import cleanly."""
    importlib.import_module("custom_components.mysolid.binary_sensor")
    importlib.import_module("custom_components.mysolid.sensor")
