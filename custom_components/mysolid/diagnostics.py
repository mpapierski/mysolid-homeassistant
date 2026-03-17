"""Diagnostics for MySolid."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD

TO_REDACT = {
    CONF_PASSWORD,
    "access_token",
    "firebase_token",
    "registration_token",
    "auth_token",
    "refresh_token",
    "security_token",
    "password",
    "username",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    runtime = entry.runtime_data
    stored_state = await runtime.store.async_load()
    snapshot = runtime.coordinator.data
    return async_redact_data(
        {
            "entry": dict(entry.data),
            "options": dict(entry.options),
            "stored_state": stored_state.to_dict() if stored_state else None,
            "snapshot": {
                "client_id": snapshot.client_id if snapshot else None,
                "permissions": sorted(snapshot.permissions) if snapshot else [],
                "push_connected": snapshot.push_connected if snapshot else False,
                "push_error": snapshot.push_error if snapshot else None,
                "properties": {
                    property_id: {
                        "details": {
                            "id": property_snapshot.details.id,
                            "name": property_snapshot.details.name,
                            "externalId": property_snapshot.details.external_id,
                            "armed": property_snapshot.details.armed,
                            "camerasEnabled": property_snapshot.details.cameras_enabled,
                            "convoysEnabled": property_snapshot.details.convoys_enabled,
                        },
                        "relay_count": len(property_snapshot.relays),
                        "active_alarm_count": property_snapshot.active_alarm_count,
                        "authorized_user_count": property_snapshot.authorized_user_count,
                        "suspension_count": len(property_snapshot.suspensions),
                    }
                    for property_id, property_snapshot in (
                        snapshot.properties.items() if snapshot else {}
                    )
                },
            },
        },
        TO_REDACT,
    )
