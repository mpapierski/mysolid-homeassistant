"""Diagnostics tests for MySolid."""

from __future__ import annotations

from homeassistant.components.diagnostics import REDACTED

from custom_components.mysolid.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redact_sensitive_fields(
    hass,
    patch_runtime,
    mock_entry,
) -> None:
    """Diagnostics should redact credentials and push tokens."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_entry)

    assert diagnostics["entry"]["password"] == REDACTED
    assert diagnostics["stored_state"]["session"]["firebase_token"] == REDACTED
    assert (
        diagnostics["stored_state"]["push_credentials"]["registration_token"] == REDACTED
    )
    details = diagnostics["snapshot"]["properties"][101644565]["details"]
    assert details["externalId"] == "ABCD1234"
