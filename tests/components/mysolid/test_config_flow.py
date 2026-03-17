"""Config flow coverage for MySolid."""

from __future__ import annotations

from custom_components.mysolid.const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN

from .conftest import DEVICE_ID, DEVICE_NAME, EMAIL, HOST, PASSWORD


async def test_user_flow_creates_entry(hass, config_flow_login) -> None:
    """The user flow should validate credentials and create an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={
            "region": "pl",
            "email": EMAIL,
            "password": PASSWORD,
            "host": "",
        },
    )

    assert result["type"] == "create_entry"
    assert result["title"] == f"MySolid ({EMAIL})"
    assert result["data"]["host"] == HOST
    assert result["data"][CONF_DEVICE_ID] == DEVICE_ID
    assert result["data"][CONF_DEVICE_NAME] == DEVICE_NAME


async def test_user_flow_handles_invalid_auth(hass, config_flow_login) -> None:
    """Authentication failures should stay on the form."""
    from custom_components.mysolid.exceptions import MySolidAuthError

    config_flow_login.side_effect = MySolidAuthError(401, "Authentication failed")

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={
            "region": "pl",
            "email": EMAIL,
            "password": PASSWORD,
            "host": "",
        },
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}
