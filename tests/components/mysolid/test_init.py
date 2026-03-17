"""Integration setup tests for MySolid."""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import MagicMock

from homeassistant.components.alarm_control_panel import AlarmControlPanelState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.mysolid.const import DOMAIN, entity_unique_id
from custom_components.mysolid.coordinator import MySolidRuntimeData
from custom_components.mysolid.storage import MySolidStateStore

from .conftest import PROPERTY_ID, build_snapshot


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
        entity_unique_id(entry_key, PROPERTY_ID, "alarm"),
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
    active_alarms_entity = entity_registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        entity_unique_id(entry_key, PROPERTY_ID, "sensor_active_alarm_count"),
    )

    assert hass.states.get(alarm_entity).state == AlarmControlPanelState.TRIGGERED
    assert hass.states.get(switch_entity).state == "on"
    assert camera_entity is not None
    assert active_alarms_entity == "sensor.abcd1234_active_alarms"
    assert entity_registry.async_get(camera_entity).original_name == "Front gate"

    device_registry = dr.async_get(hass)
    device = next(
        device
        for device in device_registry.devices.values()
        if any(identifier[0] == DOMAIN for identifier in device.identifiers)
    )
    assert device.name == "ABCD1234"
    assert device.model == (
        "Address: Example, 1, 00-001, Warsaw | "
        "External ID: ABCD1234 | Name: Home"
    )


async def test_setup_entry_creates_property_alarm_panel_without_relays(
    hass,
    runtime_fixture,
    mock_entry,
    monkeypatch,
) -> None:
    """A property alarm entity should exist even when MySolid exposes no alarm relay."""
    runtime = runtime_fixture(
        build_snapshot(
            armed=True,
            include_alarm_relay=False,
            include_active_alarm=False,
        )
    )

    def _build_runtime(_hass, entry):
        runtime.entry = entry
        return runtime

    monkeypatch.setattr("custom_components.mysolid.build_runtime", _build_runtime)
    mock_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    entry_key = mock_entry.unique_id or mock_entry.entry_id
    entity_registry = er.async_get(hass)
    alarm_entity = entity_registry.async_get_entity_id(
        "alarm_control_panel",
        DOMAIN,
        entity_unique_id(entry_key, PROPERTY_ID, "alarm"),
    )

    assert alarm_entity is not None
    assert hass.states.get(alarm_entity).state == AlarmControlPanelState.ARMED_AWAY


def test_platform_modules_import() -> None:
    """Platform modules should import cleanly."""
    importlib.import_module("custom_components.mysolid.binary_sensor")
    importlib.import_module("custom_components.mysolid.sensor")


async def test_push_loop_uses_config_entry_background_task(
    hass,
    mock_entry,
) -> None:
    """Push startup should not block bootstrap."""
    runtime = MySolidRuntimeData(
        hass=hass,
        entry=mock_entry,
        client=MagicMock(),
        store=MagicMock(spec=MySolidStateStore),
    )
    calls: list[tuple[object, str, bool]] = []

    def _async_create_background_task(hass_arg, target, name, eager_start=True):
        calls.append((hass_arg, name, eager_start))
        target.close()
        return hass.loop.create_task(asyncio.sleep(0))

    mock_entry.async_create_background_task = _async_create_background_task

    runtime.async_start_push()
    await hass.async_block_till_done()

    assert calls == [(hass, f"{DOMAIN}_push_{mock_entry.entry_id}", True)]
