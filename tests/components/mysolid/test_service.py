"""Service tests for MySolid."""

from __future__ import annotations

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import ServiceCall
from homeassistant.helpers import entity_registry as er

from custom_components.mysolid import services as mysolid_services
from custom_components.mysolid.const import DOMAIN, entity_unique_id

from .conftest import PROPERTY_ID


async def test_alarm_control_panel_write_invokes_runtime(
    hass,
    patch_runtime,
    mock_entry,
) -> None:
    """Disarming from the alarm entity should call the runtime relay write."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    entry_key = mock_entry.unique_id or mock_entry.entry_id
    entity_registry = er.async_get(hass)
    alarm_entity = entity_registry.async_get_entity_id(
        "alarm_control_panel",
        DOMAIN,
        entity_unique_id(entry_key, PROPERTY_ID, "alarm::1111::1"),
    )

    await hass.services.async_call(
        "alarm_control_panel",
        "alarm_disarm",
        {ATTR_ENTITY_ID: alarm_entity, "code": "1234"},
        blocking=True,
    )

    assert patch_runtime.calls[-1] == (
        "execute_relay",
        {
            "property_id": PROPERTY_ID,
            "transmitter_id": 1111,
            "relay_number": 1,
            "state": "DISARM",
            "pin": "1234",
        },
    )


async def test_create_suspension_service_invokes_runtime(
    hass,
    patch_runtime,
    mock_entry,
) -> None:
    """The custom suspension handler should resolve the property from the entity."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    entry_key = mock_entry.unique_id or mock_entry.entry_id
    entity_registry = er.async_get(hass)
    alarm_entity = entity_registry.async_get_entity_id(
        "alarm_control_panel",
        DOMAIN,
        entity_unique_id(entry_key, PROPERTY_ID, "alarm::1111::1"),
    )

    await mysolid_services._async_handle_create_suspension(
        hass,
        ServiceCall(
            hass,
            DOMAIN,
            "create_suspension",
            {
                ATTR_ENTITY_ID: alarm_entity,
                "suspend_from": "2026-03-17T12:00:00+00:00",
                "suspend_until": "2026-03-17T18:00:00+00:00",
            },
        ),
    )

    assert patch_runtime.calls[-1] == (
        "create_suspension",
        {
            "property_id": PROPERTY_ID,
            "suspend_from": "2026-03-17T12:00:00+00:00",
            "suspend_until": "2026-03-17T18:00:00+00:00",
        },
    )


async def test_refresh_handler_targets_entry(
    hass,
    patch_runtime,
    mock_entry,
) -> None:
    """The refresh handler should resolve the requested config entry."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    await mysolid_services._async_handle_refresh(
        hass,
        ServiceCall(
            hass,
            DOMAIN,
            "refresh",
            {"entry_id": mock_entry.entry_id},
        ),
    )

    patch_runtime.coordinator.async_request_refresh.assert_awaited_once()
