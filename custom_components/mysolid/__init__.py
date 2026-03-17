"""MySolid Home Assistant integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def build_runtime(hass: HomeAssistant, entry: ConfigEntry):
    from .coordinator import build_runtime as _build_runtime

    return _build_runtime(hass, entry)


async def async_setup(hass: HomeAssistant, config: Mapping[str, Any]) -> bool:
    from .services import async_register_services

    hass.data.setdefault(DOMAIN, {})
    await async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = build_runtime(hass, entry)
    await runtime.async_initialize()
    entry.runtime_data = runtime
    hass.data[DOMAIN][entry.entry_id] = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .services import async_unregister_services

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    runtime = hass.data[DOMAIN].pop(entry.entry_id)
    await runtime.async_shutdown()
    if not hass.data[DOMAIN]:
        async_unregister_services(hass)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    from .storage import MySolidStateStore

    await MySolidStateStore(hass, entry.entry_id).async_remove()
